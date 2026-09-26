# -*- coding: utf-8 -*-
"""M4 拍照相关测试：来源标记、类型限制、走完整识别流程、根证书公开下载。"""

import io

from conftest import wait_until
from fake_umi import FakeUmi

JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 60
PDF = b'%PDF-1.4\n' + b'\x00' * 40


def create_camera_job(api, title='拍照任务'):
    response = api.post('/api/jobs', json={'title': title, 'source_type': 'camera'})
    return response.get_json()['data']['job']['id']


def upload(api, job_id, name, data):
    return api.post('/api/jobs/%s/items' % job_id,
                    data={'file': (io.BytesIO(data), name)},
                    content_type='multipart/form-data')


def test_camera_job_accepts_capture_and_marks_source(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    job_id = create_camera_job(api)

    response = upload(api, job_id, 'camera-001.jpg', JPEG)
    assert response.status_code == 201
    item = response.get_json()['data']['item']
    assert item['kind'] == 'image'
    assert item['source'] == 'camera'
    assert item['original_name'] == 'camera-001.jpg'


def test_camera_job_rejects_pdf(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    job_id = create_camera_job(api)
    response = upload(api, job_id, 'document.pdf', PDF)
    assert response.status_code == 400
    assert response.get_json()['error']['code'] == 'unsupported_type'


def test_camera_capture_runs_through_worker(app_factory, login_on, tmp_path):
    """模拟浏览器上传两段拍摄结果，验证能正常识别。"""
    fake = FakeUmi(image_text='拍照识别结果').start()
    queue = None
    try:
        app = app_factory(umi_port=fake.port, umi_autostart=False,
                          frontend_dist_dir=str(tmp_path / 'no-frontend'))
        api = login_on(app)
        job_id = create_camera_job(api, '拍照识别')
        for name in ('camera-001.jpg', 'camera-002.jpg'):
            assert upload(api, job_id, name, JPEG).status_code == 201
        assert api.post('/api/jobs/%s/start' % job_id).status_code == 200

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
        assert job['status'] == 'done'
        assert job['source_type'] == 'camera'

        items = api.get('/api/jobs/%s/items' % job_id).get_json()['data']['items']
        assert [item['source'] for item in items] == ['camera', 'camera']
        assert [item['status'] for item in items] == ['done', 'done']
        text = api.get('/api/items/%s/text' % items[0]['id']).get_data(as_text=True)
        assert text == '拍照识别结果'
    finally:
        if queue is not None:
            queue.stop()
        fake.stop()


def test_root_cert_is_public_and_downloadable(app, client):
    """摄像头引导页要在 http 下就能下载根证书，所以这个接口不能要求登录。"""
    cert_dir = app.extensions['ocr']['config'].cert_dir
    cert_dir.mkdir(parents=True, exist_ok=True)
    (cert_dir / 'ca.cer').write_bytes(b'0\x82\x01\x00dummy-der-certificate')

    response = client.get('/api/system/root-cert')
    assert response.status_code == 200
    assert response.data.startswith(b'0\x82')
    assert 'attachment' in response.headers.get('Content-Disposition', '')