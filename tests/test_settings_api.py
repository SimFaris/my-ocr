# -*- coding: utf-8 -*-
"""运行时设置接口测试。"""


def test_get_settings_defaults(api_client, admin, app):
    api = api_client(admin['username'], admin['password'])
    payload = api.get('/api/settings').get_json()['data']
    assert payload['values']['retention_days'] == 90
    assert payload['values']['ocr_workers'] == 1
    assert payload['values']['log_level'] == 'INFO'
    assert payload['overridden']['retention_days'] is False
    assert payload['limits']['ocr_workers'] == [1, 8]
    assert 'config.json' in payload['config_file']


def test_update_settings_takes_effect(app, api_client, admin):
    api = api_client(admin['username'], admin['password'])
    response = api.put('/api/settings', json={'values': {
        'retention_days': 7, 'disk_min_free_gb': 2, 'upload_max_mb': 50,
        'ocr_workers': 3, 'log_level': 'DEBUG'}})
    assert response.status_code == 200
    payload = response.get_json()['data']
    assert payload['values']['retention_days'] == 7
    assert payload['overridden']['retention_days'] is True

    config = app.extensions['ocr']['config']
    assert config['retention_days'] == 7
    assert config['ocr_workers'] == 3
    # 立即可见：上传上限与日志级别都已生效
    assert app.config['MAX_CONTENT_LENGTH'] == 50 * 1024 * 1024
    assert app.extensions['ocr']['queue'].snapshot()['workers'] == 3


def test_update_settings_accepts_flat_payload(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    response = api.put('/api/settings', json={'retention_days': 30})
    assert response.status_code == 200
    assert response.get_json()['data']['values']['retention_days'] == 30


def test_update_settings_validations(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    assert api.put('/api/settings', json={'values': {'retention_days': -1}}).status_code == 400
    assert api.put('/api/settings', json={'values': {'ocr_workers': 99}}).status_code == 400
    assert api.put('/api/settings', json={'values': {'log_level': 'VERBOSE'}}).status_code == 400
    assert api.put('/api/settings', json={'values': {'unknown_key': 1}}).status_code == 400
    assert api.put('/api/settings', json={'values': {}}).status_code == 400
    assert api.put('/api/settings', json={'values': {'retention_days': 'abc'}}).status_code == 400


def test_settings_persist_across_restart(app_factory, login_on, tmp_path):
    """改过的设置重启后仍然生效。"""
    data_dir = str(tmp_path / 'shared')
    first = app_factory(data_dir=data_dir)
    api = login_on(first)
    assert api.put('/api/settings', json={'values': {'retention_days': 15,
                                                     'log_level': 'WARNING'}}).status_code == 200

    second = app_factory(data_dir=data_dir)
    config = second.extensions['ocr']['config']
    assert config['retention_days'] == 15
    assert config['log_level'] == 'WARNING'

    api2 = login_on(second, username='tester2')
    payload = api2.get('/api/settings').get_json()['data']
    assert payload['overridden']['retention_days'] is True