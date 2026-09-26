# -*- coding: utf-8 -*-
"""保留策略与手动清理测试。"""

import datetime
import io

from backend.services.retention import cleanup
from backend.utils import now_iso

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 40


def days_ago(days):
    moment = (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)
              - datetime.timedelta(days=days))
    return moment.isoformat() + 'Z'


def upload(api, job_id, name='a.png'):
    return api.post('/api/jobs/%s/items' % job_id,
                    data={'file': (io.BytesIO(PNG), name)},
                    content_type='multipart/form-data')


def make_job(api, title, start=False):
    job_id = api.post('/api/jobs', json={'title': title, 'source_type': 'image'}
                      ).get_json()['data']['job']['id']
    upload(api, job_id)
    if start:
        api.post('/api/jobs/%s/start' % job_id)
    return job_id


def test_cleanup_disabled_when_retention_zero(app, api_client, admin):
    api = api_client(admin['username'], admin['password'])
    make_job(api, '不清理')
    config = app.extensions['ocr']['config']
    config.set_runtime('retention_days', 0)
    result = cleanup(app.extensions['ocr']['db'], config)
    assert result['enabled'] is False
    assert result['deleted_jobs'] == 0
    assert api.get('/api/jobs').get_json()['data']['total'] == 1


def test_cleanup_removes_expired_jobs_and_files(app, api_client, admin):
    api = api_client(admin['username'], admin['password'])
    db = app.extensions['ocr']['db']
    data_dir = app.extensions['ocr']['config'].data_dir

    old_job = make_job(api, '很旧的任务', start=True)
    api.post('/api/jobs/%s/cancel' % old_job)
    fresh_job = make_job(api, '新任务')
    active_job = make_job(api, '排队中的旧任务', start=True)

    # 把两个任务的时间改到 200 天前
    for job_id in (old_job, active_job):
        db.execute('UPDATE jobs SET created_at = ?, finished_at = ? WHERE id = ?',
                   (days_ago(200), days_ago(200), job_id))

    assert (data_dir / 'uploads' / old_job).is_dir()
    result = cleanup(db, app.extensions['ocr']['config'])
    assert result['enabled'] is True
    assert result['deleted_jobs'] == 1          # 只有已取消的那个被删
    assert not (data_dir / 'uploads' / old_job).exists()

    remaining = [row['id'] for row in db.query('SELECT id FROM jobs')]
    assert old_job not in remaining
    assert fresh_job in remaining
    assert active_job in remaining             # 排队中的任务不能被删


def test_cleanup_removes_orphan_directories(app, api_client, admin):
    api = api_client(admin['username'], admin['password'])
    db = app.extensions['ocr']['db']
    data_dir = app.extensions['ocr']['config'].data_dir

    orphan = data_dir / 'results' / 'no-such-job'
    orphan.mkdir(parents=True, exist_ok=True)
    (orphan / 'left.txt').write_text('残留', encoding='utf-8')

    result = cleanup(db, app.extensions['ocr']['config'])
    assert result['orphan_dirs'] == 1
    assert not orphan.exists()


def test_cleanup_keeps_draft_within_retention(app, api_client, admin):
    api = api_client(admin['username'], admin['password'])
    db = app.extensions['ocr']['db']
    draft = make_job(api, '刚建的草稿')
    result = cleanup(db, app.extensions['ocr']['config'])
    assert result['deleted_jobs'] == 0
    assert api.get('/api/jobs/%s' % draft).status_code == 200


def test_maintenance_endpoint_reports_stats(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    response = api.post('/api/maintenance/cleanup')
    assert response.status_code == 200
    result = response.get_json()['data']['result']
    assert result['enabled'] is True
    assert 'deleted_jobs' in result and 'orphan_dirs' in result