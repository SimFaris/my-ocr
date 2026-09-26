# -*- coding: utf-8 -*-
"""队列测试：跨用户轮转公平性 + 工作线程真实执行。"""

import io

from conftest import wait_until
from fake_umi import FakeUmi

from backend.queue.scheduler import Scheduler
from backend.repositories import items as items_repo
from backend.repositories import jobs as jobs_repo
from backend.repositories import users as users_repo

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 40


def test_scheduler_rotates_between_users(app):
    """同一用户提交一大堆时，不能让其他用户排在后面。

    三个用户各两个任务项，调度顺序必须是 甲→乙→丙→甲→乙→丙。
    """
    db = app.extensions['ocr']['db']
    job_ids = []
    for index in range(3):
        user_id = users_repo.create(db, 'user%d' % index, 'password123')
        job_id = jobs_repo.create(db, user_id, 'job-%d' % index, 'image', {})
        for _ in range(2):
            item_id = items_repo.new_id()
            items_repo.add(db, job_id, 'image', 'upload', 'a.png',
                           'uploads/%s/%s.png' % (job_id, item_id), len(PNG), item_id=item_id)
        items_repo.mark_queued(db, job_id)
        jobs_repo.mark_submitted(db, job_id)
        jobs_repo.refresh_counts(db, job_id)
        # now_iso() 只有秒级精度，同秒创建会并列，这里写死时间戳保证顺序确定
        db.execute('UPDATE job_items SET queued_at = ? WHERE job_id = ?',
                   ('2026-01-01T00:00:%02dZ' % index, job_id))
        job_ids.append(job_id)

    scheduler = Scheduler(db)
    claimed = [scheduler.next_item() for _ in range(6)]
    assert all(item is not None for item in claimed)
    order = [item['job_id'] for item in claimed]
    assert order[:3] == job_ids
    assert order[3:] == job_ids
    assert scheduler.next_item() is None


def test_scheduler_skips_unsubmitted_jobs(app):
    """草稿状态的任务（文件已上传但未提交）不能被调度。"""
    db = app.extensions['ocr']['db']
    user_id = users_repo.create(db, 'draftuser', 'password123')
    job_id = jobs_repo.create(db, user_id, 'draft', 'image', {})
    item_id = items_repo.new_id()
    items_repo.add(db, job_id, 'image', 'upload', 'a.png',
                   'uploads/%s/%s.png' % (job_id, item_id), len(PNG), item_id=item_id)

    assert Scheduler(db).next_item() is None


def test_worker_executes_items_and_writes_text(app_factory, login_on, tmp_path):
    """工作线程跑通整条链路：领取 → 调 Umi → 落文本 → 更新状态。"""
    fake = FakeUmi(image_text='识别出来的文字').start()
    queue = None
    try:
        app = app_factory(umi_port=fake.port, umi_autostart=False,
                          frontend_dist_dir=str(tmp_path / 'no-frontend'))
        api = login_on(app)

        created = api.post('/api/jobs', json={'title': '工作线程验证', 'source_type': 'image'})
        assert created.status_code == 201
        job_id = created.get_json()['data']['job']['id']

        for name in ('甲.png', '乙.png'):
            response = api.post('/api/jobs/%s/items' % job_id,
                                data={'file': (io.BytesIO(PNG), name)},
                                content_type='multipart/form-data')
            assert response.status_code == 201

        assert api.post('/api/jobs/%s/start' % job_id).status_code == 200

        queue = app.extensions['ocr']['queue']
        assert queue.start() is True
        try:
            finished = wait_until(
                lambda: api.get('/api/jobs/%s' % job_id).get_json()['data']['job']['status']
                in ('done', 'partial', 'failed'), timeout=25)
        finally:
            queue.stop()
        assert finished, '任务未在预期时间内完成'

        job = api.get('/api/jobs/%s' % job_id).get_json()['data']['job']
        assert job['status'] == 'done'
        assert job['item_done'] == 2
        assert job['finished_at']

        items = api.get('/api/jobs/%s/items' % job_id).get_json()['data']['items']
        assert [item['status'] for item in items] == ['done', 'done']
        assert items[0]['char_count'] == len('识别出来的文字')
        assert items[0]['duration_ms'] >= 0

        text = api.get('/api/items/%s/text' % items[0]['id']).get_data(as_text=True)
        assert text == '识别出来的文字'

        data_dir = app.extensions['ocr']['config'].data_dir
        assert (data_dir / 'results' / job_id / (items[0]['id'] + '.txt')).is_file()

        # 排队计数应归零
        assert api.get('/api/jobs/summary').get_json()['data']['queue']['pending'] == 0
    finally:
        if queue is not None:
            queue.stop()
        fake.stop()


def test_worker_marks_failure_without_breaking_batch(app_factory, login_on, tmp_path):
    """Umi 报业务错误时，该项标记失败，其他项不受影响。"""
    fake = FakeUmi(mode='error').start()
    queue = None
    try:
        app = app_factory(umi_port=fake.port, umi_autostart=False,
                          frontend_dist_dir=str(tmp_path / 'no-frontend'))
        api = login_on(app)
        job_id = api.post('/api/jobs', json={'title': '失败用例', 'source_type': 'image'}
                          ).get_json()['data']['job']['id']
        api.post('/api/jobs/%s/items' % job_id,
                 data={'file': (io.BytesIO(PNG), '坏图.png')},
                 content_type='multipart/form-data')
        api.post('/api/jobs/%s/start' % job_id)

        queue = app.extensions['ocr']['queue']
        queue.start()
        try:
            finished = wait_until(
                lambda: api.get('/api/jobs/%s' % job_id).get_json()['data']['job']['status']
                in ('done', 'partial', 'failed'), timeout=25)
        finally:
            queue.stop()
        assert finished

        job = api.get('/api/jobs/%s' % job_id).get_json()['data']['job']
        assert job['status'] == 'failed'
        item = api.get('/api/jobs/%s/items' % job_id).get_json()['data']['items'][0]
        assert item['status'] == 'failed'
        assert item['error_code'] == 'umi_ocr_failed'
        assert '识别器' in item['error_message']
    finally:
        if queue is not None:
            queue.stop()
        fake.stop()