# -*- coding: utf-8 -*-
"""用户管理接口测试。"""


def test_user_management_requires_admin(app, api_client, make_user):
    normal = make_user('normal')
    api = api_client(normal['username'], normal['password'])
    assert api.get('/api/users').status_code == 403
    assert api.post('/api/users', json={'username': 'x1', 'password': 'password123'}).status_code == 403
    assert api.get('/api/settings').status_code == 403
    assert api.post('/api/maintenance/cleanup').status_code == 403


def test_list_users_includes_initial_admin(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    response = api.get('/api/users')
    assert response.status_code == 200
    users = response.get_json()['data']['items']
    assert [item['username'] for item in users] == [admin['username']]
    assert users[0]['role'] == 'admin'
    assert 'password_hash' not in users[0]


def test_create_user_with_generated_password(app, api_client, admin):
    api = api_client(admin['username'], admin['password'])
    response = api.post('/api/users', json={'username': 'zhangsan', 'display_name': '张三'})
    assert response.status_code == 201
    payload = response.get_json()['data']
    assert payload['user']['username'] == 'zhangsan'
    assert payload['user']['role'] == 'user'
    assert payload['user']['is_active'] is True
    generated = payload['initial_password']
    assert generated and len(generated) >= 12

    # 生成的密码可以直接登录（用独立客户端，别覆盖管理员会话）
    fresh = app.test_client()
    login = fresh.post('/api/auth/login', json={'username': 'zhangsan', 'password': generated})
    assert login.status_code == 200


def test_create_user_with_given_password(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    response = api.post('/api/users', json={
        'username': 'lisi', 'password': 'password123', 'role': 'admin'})
    assert response.status_code == 201
    assert response.get_json()['data']['initial_password'] is None
    assert response.get_json()['data']['user']['role'] == 'admin'


def test_create_user_validations(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    assert api.post('/api/users', json={'username': 'ab'}).status_code == 400          # 太短
    assert api.post('/api/users', json={'username': '有中文'}).status_code == 400
    assert api.post('/api/users', json={'username': 'okname', 'password': 'short'}).status_code == 400
    assert api.post('/api/users', json={'username': 'okname', 'role': 'root'}).status_code == 400

    assert api.post('/api/users', json={'username': 'okname'}).status_code == 201
    duplicate = api.post('/api/users', json={'username': 'okname'})
    assert duplicate.status_code == 409


def test_update_user_role_and_reset_password(app, api_client, admin):
    api = api_client(admin['username'], admin['password'])
    created = api.post('/api/users', json={'username': 'wangwu', 'password': 'password123'})
    user_id = created.get_json()['data']['user']['id']

    promoted = api.patch('/api/users/%d' % user_id, json={'role': 'admin'})
    assert promoted.status_code == 200
    assert promoted.get_json()['data']['user']['role'] == 'admin'

    reset = api.patch('/api/users/%d' % user_id, json={'reset_password': True})
    assert reset.status_code == 200
    new_password = reset.get_json()['data']['new_password']
    assert new_password and len(new_password) >= 12

    # 注意：必须用独立客户端登录，否则会覆盖管理员会话，
    # 连带的 CSRF 令牌也会失配（表现为莫名其妙的 403）。
    other = app.test_client()
    login = other.post('/api/auth/login', json={'username': 'wangwu', 'password': new_password})
    assert login.status_code == 200

    disabled = api.patch('/api/users/%d' % user_id, json={'is_active': False})
    assert disabled.status_code == 200
    blocked = other.post('/api/auth/login', json={'username': 'wangwu', 'password': new_password})
    assert blocked.status_code == 401


def test_admin_cannot_lock_itself_out(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    users = api.get('/api/users').get_json()['data']['items']
    me = [item for item in users if item['username'] == admin['username']][0]

    assert api.patch('/api/users/%d' % me['id'], json={'role': 'user'}).status_code == 409
    assert api.patch('/api/users/%d' % me['id'], json={'is_active': False}).status_code == 409


def test_update_user_without_changes(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    users = api.get('/api/users').get_json()['data']['items']
    assert api.patch('/api/users/%d' % users[0]['id'], json={}).status_code == 400
    assert api.patch('/api/users/9999', json={'role': 'user'}).status_code == 404