# -*- coding: utf-8 -*-
"""任务接口测试：上传、提交、权限、取消、重试、删除与导出。"""

import io

from conftest import wait_until

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 40


def upload(api, job_id, name='a.png', data=PNG, kind='image/png'):
    return api.post('/api/jobs/%s/items' % job_id,
                    data={'file': (io.BytesIO(data), name)},
                    content_type='multipart/form-data')


def create_job(api, title='测试任务', source_type='image', options=None):
    payload = {'title': title, 'source_type': source_type}
    if options is not None:
        payload['ocr_options'] = options
    return api.post('/api/jobs', json=payload)


def test_create_job_requires_login(client):
    assert client.post('/api/jobs', json={'title': 'x'}).status_code == 401


def test_create_job_and_list(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    response = create_job(api, '报表扫描件', options={'ocr.language': 'models/config_chinese.txt'})
    assert response.status_code == 201
    job = response.get_json()['data']['job']
    assert job['status'] == 'draft'
    assert job['title'] == '报表扫描件'
    assert job['ocr_options']['ocr.language'] == 'models/config_chinese.txt'
    assert '.png' in response.get_json()['data']['image_extensions']

    listing = api.get('/api/jobs').get_json()['data']
    assert listing['total'] == 1
    assert listing['items'][0]['id'] == job['id']


def test_create_job_accepts_pdf_and_rejects_mixed(api_client, admin):
    """PDF 在 M3 开放；mixed 仍未开放。"""
    api = api_client(admin['username'], admin['password'])
    assert create_job(api, source_type='pdf').status_code == 201
    response = create_job(api, source_type='mixed')
    assert response.status_code == 400
    assert response.get_json()['error']['code'] == 'invalid_request'


def test_pdf_job_declares_accepted_kinds(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    payload = create_job(api, source_type='pdf').get_json()['data']
    assert payload['accepts'] == ['pdf']
    assert '.pdf' in payload['pdf_extensions']


def test_create_job_rejects_bad_source(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    assert create_job(api, source_type='nope').status_code == 400


def test_create_job_blocked_when_disk_low(app_factory, login_on):
    """磁盘水位阈值设成不可能满足的值，应拒绝建任务。"""
    app = app_factory(disk_min_free_gb=999999)
    api = login_on(app)
    response = create_job(api)
    assert response.status_code == 507
    assert response.get_json()['error']['code'] == 'disk_low'


def test_upload_validate_and_start(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    job_id = create_job(api).get_json()['data']['job']['id']

    response = upload(api, job_id, '第一页.png')
    assert response.status_code == 201
    item = response.get_json()['data']['item']
    assert item['status'] == 'pending'
    assert item['original_name'] == '第一页.png'

    bad = upload(api, job_id, 'x.png', b'%PDF-1.4 fake')
    assert bad.status_code == 400
    assert bad.get_json()['error']['code'] == 'unsupported_type'

    detail = api.get('/api/jobs/%s' % job_id).get_json()['data']['job']
    assert detail['item_total'] == 1
    assert detail['status'] == 'draft'

    started = api.post('/api/jobs/%s/start' % job_id)
    assert started.status_code == 200
    job = started.get_json()['data']['job']
    assert job['status'] == 'queued'

    again = api.post('/api/jobs/%s/start' % job_id)
    assert again.status_code == 409

    after = upload(api, job_id, 'late.png')
    assert after.status_code == 409


def test_start_without_items_fails(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    job_id = create_job(api).get_json()['data']['job']['id']
    response = api.post('/api/jobs/%s/start' % job_id)
    assert response.status_code == 400


def test_jobs_are_isolated_between_users(api_client, admin, make_user):
    api = api_client(admin['username'], admin['password'])
    job_id = create_job(api, '管理员的任务').get_json()['data']['job']['id']
    upload(api, job_id, 'a.png')

    other = make_user('bob')
    bob_api = api_client(other['username'], other['password'])

    assert bob_api.get('/api/jobs/%s' % job_id).status_code == 403
    assert bob_api.get('/api/jobs').get_json()['data']['total'] == 0
    assert bob_api.post('/api/jobs/%s/start' % job_id).status_code == 403

    items = api.get('/api/jobs/%s/items' % job_id).get_json()['data']['items']
    assert bob_api.get('/api/items/%s/text' % items[0]['id']).status_code == 403


def test_cancel_and_retry(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    job_id = create_job(api).get_json()['data']['job']['id']
    upload(api, job_id, 'a.png')
    api.post('/api/jobs/%s/start' % job_id)

    canceled = api.post('/api/jobs/%s/cancel' % job_id)
    assert canceled.status_code == 200
    assert canceled.get_json()['data']['job']['status'] == 'canceled'
    items = api.get('/api/jobs/%s/items' % job_id).get_json()['data']['items']
    assert items[0]['status'] == 'skipped'

    retried = api.post('/api/jobs/%s/retry' % job_id)
    assert retried.status_code == 200
    assert retried.get_json()['data']['requeued'] == 1
    assert retried.get_json()['data']['job']['status'] == 'queued'

    nothing = api.post('/api/jobs/%s/retry' % job_id)
    assert nothing.status_code == 400


def test_delete_job_removes_files(api_client, admin, app):
    api = api_client(admin['username'], admin['password'])
    job_id = create_job(api).get_json()['data']['job']['id']
    upload(api, job_id, 'a.png')

    data_dir = app.extensions['ocr']['config'].data_dir
    assert (data_dir / 'uploads' / job_id).is_dir()

    assert api.delete('/api/jobs/%s' % job_id).status_code == 200
    assert api.get('/api/jobs/%s' % job_id).status_code == 404
    assert not (data_dir / 'uploads' / job_id).exists()


def test_export_txt_and_csv(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    job_id = create_job(api, '导出验证').get_json()['data']['job']['id']
    upload(api, job_id, '甲.png')
    item_id = api.get('/api/jobs/%s/items' % job_id).get_json()['data']['items'][0]['id']

    # 手工写入识别文本，模拟识别完成
    saved = api.put('/api/items/%s/text' % item_id, json={'text': '第一行\n第二行'})
    assert saved.status_code == 200
    assert saved.get_json()['data']['item']['char_count'] == 7

    text = api.get('/api/items/%s/text' % item_id).get_data(as_text=True)
    assert text == '第一行\n第二行'

    exported = api.get('/api/jobs/%s/export?format=txt' % job_id)
    assert exported.status_code == 200
    body = exported.get_data(as_text=True)
    assert '导出验证' in body and '甲.png' in body and '第一行' in body

    csv_response = api.get('/api/jobs/%s/export?format=csv' % job_id)
    assert csv_response.status_code == 200
    raw = csv_response.get_data()
    assert raw.startswith(b'\xef\xbb\xbf')          # Excel 需要的 UTF-8 BOM
    assert '文件名' in raw.decode('utf-8-sig')

    assert api.get('/api/jobs/%s/export?format=pdf' % job_id).status_code == 400


def test_write_requires_csrf(client, admin):
    response = client.post('/api/auth/login', json=admin)
    token = response.get_json()['data']['csrf']
    assert token
    # 不带 CSRF 头：写操作被拒
    blocked = client.post('/api/jobs', json={'title': 'x'})
    assert blocked.status_code == 403