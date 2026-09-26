# -*- coding: utf-8 -*-
"""M3 PDF 相关测试：文档识别流程、双层 PDF、错误与超时判定。"""

import io

from conftest import wait_until
from fake_umi import FakeUmi

PDF = b'%PDF-1.4\n' + b'\x00' * 60
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 40


def create_pdf_job(api, title='PDF 任务', options=None):
    response = api.post('/api/jobs', json={
        'title': title, 'source_type': 'pdf', 'ocr_options': options or {}})
    return response.get_json()['data']['job']['id']


def upload(api, job_id, name, data):
    return api.post('/api/jobs/%s/items' % job_id,
                    data={'file': (io.BytesIO(data), name)},
                    content_type='multipart/form-data')


def wait_job(api, job_id, timeout=30):
    return wait_until(
        lambda: api.get('/api/jobs/%s' % job_id).get_json()['data']['job']['status']
        in ('done', 'partial', 'failed'), timeout=timeout)


def job_items(api, job_id):
    return api.get('/api/jobs/%s/items' % job_id).get_json()['data']['items']


def test_pdf_job_rejects_image_and_image_job_rejects_pdf(api_client, admin):
    api = api_client(admin['username'], admin['password'])

    pdf_job = create_pdf_job(api)
    wrong = upload(api, pdf_job, 'a.png', PNG)
    assert wrong.status_code == 400
    assert wrong.get_json()['error']['code'] == 'unsupported_type'

    image_job = api.post('/api/jobs', json={'title': '图片任务', 'source_type': 'image'}
                         ).get_json()['data']['job']['id']
    wrong2 = upload(api, image_job, 'a.pdf', PDF)
    assert wrong2.status_code == 400
    assert wrong2.get_json()['error']['code'] == 'unsupported_type'


def test_doc_options_are_proxied(app_factory, login_on, tmp_path):
    fake = FakeUmi().start()
    try:
        app = app_factory(umi_port=fake.port, umi_autostart=False,
                          frontend_dist_dir=str(tmp_path / 'no-frontend'))
        api = login_on(app)
        response = api.get('/api/system/doc-options')
        assert response.status_code == 200
        assert 'ocr.language' in response.get_json()['data']
    finally:
        fake.stop()


def test_pdf_worker_produces_text_and_layered_pdf(app_factory, login_on, tmp_path):
    """两个 PDF 走完整流程：文本、页级进度、双层 PDF 产物与打包导出。"""
    fake = FakeUmi(doc_pages=2).start()
    queue = None
    try:
        app = app_factory(umi_port=fake.port, umi_autostart=False, pdf_poll_interval=0.05,
                          frontend_dist_dir=str(tmp_path / 'no-frontend'))
        api = login_on(app)
        job_id = create_pdf_job(api, '扫描件验证', {'laying_pdf': True})
        for name in ('甲.pdf', '乙.pdf'):
            assert upload(api, job_id, name, PDF).status_code == 201
        assert api.post('/api/jobs/%s/start' % job_id).status_code == 200

        queue = app.extensions['ocr']['queue']
        queue.start()
        try:
            finished = wait_job(api, job_id)
        finally:
            queue.stop()
        assert finished, 'PDF 任务未在预期时间内完成'

        job = api.get('/api/jobs/%s' % job_id).get_json()['data']['job']
        assert job['status'] == 'done'
        assert job['item_done'] == 2

        items = job_items(api, job_id)
        for item in items:
            assert item['status'] == 'done'
            assert item['page_total'] == 2
            assert item['page_done'] == 2
            assert item['has_layered_pdf'] is True

        text = api.get('/api/items/%s/text' % items[0]['id']).get_data(as_text=True)
        assert '第 1 页文字' in text and '第 2 页文字' in text

        artifact = api.get('/api/items/%s/artifact?type=pdfLayered' % items[0]['id'])
        assert artifact.status_code == 200
        assert artifact.headers['Content-Type'].startswith('application/pdf')

        assert api.get('/api/items/%s/artifact?type=nope' % items[0]['id']).status_code == 404

        # 两个双层 PDF：导出应为 zip 包
        exported = api.get('/api/jobs/%s/export?format=pdfLayered' % job_id)
        assert exported.status_code == 200
        assert exported.headers['Content-Type'].startswith('application/zip')

        # Umi 侧任务必须被清理，避免其临时文件堆积
        assert 'doc_clear' in fake.state['calls']
    finally:
        if queue is not None:
            queue.stop()
        fake.stop()


def test_pdf_without_layered_has_no_artifact(app_factory, login_on, tmp_path):
    fake = FakeUmi(doc_pages=1).start()
    queue = None
    try:
        app = app_factory(umi_port=fake.port, umi_autostart=False, pdf_poll_interval=0.05,
                          frontend_dist_dir=str(tmp_path / 'no-frontend'))
        api = login_on(app)
        job_id = create_pdf_job(api, '只要文本')
        upload(api, job_id, 'a.pdf', PDF)
        api.post('/api/jobs/%s/start' % job_id)

        queue = app.extensions['ocr']['queue']
        queue.start()
        try:
            assert wait_job(api, job_id)
        finally:
            queue.stop()

        item = job_items(api, job_id)[0]
        assert item['status'] == 'done'
        assert item['has_layered_pdf'] is False
        assert api.get('/api/items/%s/artifact' % item['id']).status_code == 404
        assert 'doc_download' not in fake.state['calls']
    finally:
        if queue is not None:
            queue.stop()
        fake.stop()


def test_encrypted_pdf_reports_clear_error(app_factory, login_on, tmp_path):
    """加密 PDF 属于业务错误：不重试，错误原因要能看懂。"""
    fake = FakeUmi(doc_mode='encrypted').start()
    queue = None
    try:
        app = app_factory(umi_port=fake.port, umi_autostart=False, pdf_poll_interval=0.05,
                          frontend_dist_dir=str(tmp_path / 'no-frontend'))
        api = login_on(app)
        job_id = create_pdf_job(api, '加密文档')
        upload(api, job_id, '加密.pdf', PDF)
        api.post('/api/jobs/%s/start' % job_id)

        queue = app.extensions['ocr']['queue']
        queue.start()
        try:
            assert wait_job(api, job_id)
        finally:
            queue.stop()

        job = api.get('/api/jobs/%s' % job_id).get_json()['data']['job']
        assert job['status'] == 'failed'
        item = job_items(api, job_id)[0]
        assert item['status'] == 'failed'
        assert item['error_code'] == 'umi_doc_upload_failed'
        assert '加密' in item['error_message']
    finally:
        if queue is not None:
            queue.stop()
        fake.stop()


def test_stalled_pdf_is_detected(app_factory, login_on, tmp_path):
    """页数长时间不推进要判为卡死，而不是无限等下去。"""
    fake = FakeUmi(doc_pages=5, doc_mode='stall').start()
    queue = None
    try:
        app = app_factory(umi_port=fake.port, umi_autostart=False, pdf_poll_interval=0.05,
                          pdf_stall_seconds=1, pdf_item_timeout_base=600,
                          frontend_dist_dir=str(tmp_path / 'no-frontend'))
        api = login_on(app)
        job_id = create_pdf_job(api, '卡死用例')
        upload(api, job_id, 'a.pdf', PDF)
        api.post('/api/jobs/%s/start' % job_id)

        queue = app.extensions['ocr']['queue']
        queue.start()
        try:
            assert wait_job(api, job_id, timeout=30)
        finally:
            queue.stop()

        item = job_items(api, job_id)[0]
        assert item['status'] == 'failed'
        assert item['error_code'] == 'stalled'
        assert '进展' in item['error_message']
    finally:
        if queue is not None:
            queue.stop()
        fake.stop()


def test_canceled_pdf_item_is_skipped_and_task_cleared(app_factory, login_on, tmp_path):
    """取消任务时，正在跑的 PDF 项应停止轮询并清理 Umi 侧任务。"""
    fake = FakeUmi(doc_pages=50).start()
    queue = None
    try:
        app = app_factory(umi_port=fake.port, umi_autostart=False, pdf_poll_interval=0.2,
                          frontend_dist_dir=str(tmp_path / 'no-frontend'))
        api = login_on(app)
        job_id = create_pdf_job(api, '取消用例')
        upload(api, job_id, 'a.pdf', PDF)
        api.post('/api/jobs/%s/start' % job_id)

        queue = app.extensions['ocr']['queue']
        queue.start()
        try:
            assert wait_until(lambda: job_items(api, job_id)[0]['status'] == 'running', timeout=20)
            assert api.post('/api/jobs/%s/cancel' % job_id).status_code == 200
            assert wait_until(lambda: job_items(api, job_id)[0]['status'] in ('skipped', 'done'),
                              timeout=20)
        finally:
            queue.stop()

        assert 'doc_clear' in fake.state['calls']
        job = api.get('/api/jobs/%s' % job_id).get_json()['data']['job']
        assert job['status'] == 'canceled'
    finally:
        if queue is not None:
            queue.stop()
        fake.stop()