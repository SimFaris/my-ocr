# -*- coding: utf-8 -*-
"""初始凭据显示与使用测试。"""


def test_hint_visible_with_default_credentials(app, client):
    """全新部署时，登录页能拿到 cm/cm（仅在未改密前）。"""
    response = client.get('/api/auth/bootstrap-hint')
    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['visible'] is True
    assert data['username'] == 'cm'
    assert data['password'] == 'cm'
    assert (app.extensions['ocr']['config'].data_dir / 'initial_admin_password.txt').is_file()


def test_login_with_default_credentials(client):
    response = client.post('/api/auth/login', json={'username': 'cm', 'password': 'cm'})
    assert response.status_code == 200
    assert response.get_json()['data']['user']['username'] == 'cm'
    assert response.get_json()['data']['user']['role'] == 'admin'


def test_hint_disappears_after_password_change(app, client):
    login = client.post('/api/auth/login', json={'username': 'cm', 'password': 'cm'})
    csrf = login.get_json()['data']['csrf']

    changed = client.post('/api/auth/password',
                          json={'old_password': 'cm', 'new_password': 'newpassword123'},
                          headers={'X-CSRF-Token': csrf})
    assert changed.status_code == 200

    data = client.get('/api/auth/bootstrap-hint').get_json()['data']
    assert data['visible'] is False
    assert not (app.extensions['ocr']['config'].data_dir / 'initial_admin_password.txt').exists()


def test_hint_can_be_disabled(app_factory):
    app = app_factory(show_initial_credentials=False)
    with app.test_client() as client:
        data = client.get('/api/auth/bootstrap-hint').get_json()['data']
    assert data['visible'] is False


def test_marker_file_contents_match(app):
    marker = app.extensions['ocr']['config'].data_dir / 'initial_admin_password.txt'
    text = marker.read_text(encoding='utf-8')
    assert '用户名：cm' in text
    assert '密码：cm' in text
    assert '修改密码' in text