# -*- coding: utf-8 -*-
"""系统接口测试。"""


def test_status_requires_login(client):
    assert client.get('/api/system/status').status_code == 401


def test_status_reports_offline_engine(logged_in):
    client, _token = logged_in
    response = client.get('/api/system/status')
    assert response.status_code == 200
    payload = response.get_json()['data']

    assert payload['umi']['online'] is False
    assert payload['umi']['process_running'] is False
    assert payload['umi']['autostart'] is False
    assert payload['queue']['pending'] == 0
    assert payload['queue']['running'] == 0
    assert payload['workers'] == 1
    assert payload['disk']['free'] > 0
    assert payload['https']['cert_exists'] is False
    assert payload['app_version']


def test_ocr_options_unavailable_without_engine(logged_in):
    client, _token = logged_in
    response = client.get('/api/system/ocr-options')
    assert response.status_code == 503
    assert response.get_json()['error']['code'] == 'umi_unavailable'


def test_root_cert_missing_returns_404(client):
    response = client.get('/api/system/root-cert')
    assert response.status_code == 404
    assert response.get_json()['error']['code'] == 'not_found'


def test_unknown_api_path_returns_json_404(client):
    response = client.get('/api/does-not-exist')
    assert response.status_code == 404
    assert response.get_json()['error']['code'] == 'not_found'


def test_placeholder_page_when_frontend_not_built(client):
    response = client.get('/')
    assert response.status_code == 200
    assert '后端已启动' in response.get_data(as_text=True)