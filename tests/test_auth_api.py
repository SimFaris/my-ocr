# -*- coding: utf-8 -*-
"""认证接口测试。"""


def test_me_requires_login(client):
    response = client.get('/api/auth/me')
    assert response.status_code == 401
    assert response.get_json()['error']['code'] == 'auth_required'


def test_login_rejects_wrong_password(client, admin):
    response = client.post('/api/auth/login', json={
        'username': admin['username'], 'password': 'wrong-password'})
    assert response.status_code == 401
    assert response.get_json()['error']['code'] == 'invalid_credentials'


def test_login_requires_both_fields(client):
    response = client.post('/api/auth/login', json={'username': 'admin'})
    assert response.status_code == 400
    assert response.get_json()['error']['code'] == 'invalid_request'


def test_login_success_then_me(client, admin):
    response = client.post('/api/auth/login', json=admin)
    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['user']['username'] == admin['username']
    assert data['user']['role'] == 'admin'
    assert data['csrf']
    assert 'password_hash' not in data['user']

    me = client.get('/api/auth/me')
    assert me.status_code == 200
    assert me.get_json()['data']['user']['username'] == admin['username']


def test_write_request_without_csrf_is_forbidden(client, admin):
    client.post('/api/auth/login', json=admin)
    response = client.post('/api/auth/password', json={
        'old_password': admin['password'], 'new_password': 'newpass123'})
    assert response.status_code == 403
    assert response.get_json()['error']['code'] == 'forbidden'


def test_change_password_and_initial_password_file_removed(app, client, admin):
    data_dir = app.extensions['ocr']['config'].data_dir
    token = client.post('/api/auth/login', json=admin).get_json()['data']['csrf']

    response = client.post('/api/auth/password',
                           json={'old_password': admin['password'],
                                 'new_password': 'newpass123'},
                           headers={'X-CSRF-Token': token})
    assert response.status_code == 200
    assert not (data_dir / 'initial_admin_password.txt').exists()

    client.post('/api/auth/logout', headers={'X-CSRF-Token': token})
    assert client.post('/api/auth/login', json={
        'username': admin['username'], 'password': 'newpass123'}).status_code == 200


def test_change_password_rejects_short_password(client, admin):
    token = client.post('/api/auth/login', json=admin).get_json()['data']['csrf']
    response = client.post('/api/auth/password',
                           json={'old_password': admin['password'], 'new_password': 'short'},
                           headers={'X-CSRF-Token': token})
    assert response.status_code == 400
    assert response.get_json()['error']['code'] == 'invalid_request'


def test_login_rate_limited_after_repeated_failures(client, admin):
    payload = {'username': admin['username'], 'password': 'wrong-password'}
    codes = []
    for _ in range(6):
        codes.append(client.post('/api/auth/login', json=payload).status_code)
    assert 429 in codes


def test_logout_clears_session(client, admin):
    token = client.post('/api/auth/login', json=admin).get_json()['data']['csrf']
    assert client.post('/api/auth/logout', headers={'X-CSRF-Token': token}).status_code == 200
    assert client.get('/api/auth/me').status_code == 401