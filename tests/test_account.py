# -*- coding: utf-8 -*-
"""改密相关测试：自助改密、管理员自重置、命令行重置工具。"""

import importlib.util
from pathlib import Path

from backend import security
from backend.repositories import users as users_repo

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_tool(filename):
    path = PROJECT_ROOT / 'tools' / filename
    spec = importlib.util.spec_from_file_location('tool_' + filename.replace('.', '_'), str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def admin_self_id(api, username):
    users = api.get('/api/users').get_json()['data']['items']
    return [item for item in users if item['username'] == username][0]['id']


def test_change_own_password_then_login_with_new_one(app, api_client, admin):
    api = api_client(admin['username'], admin['password'])
    data_dir = app.extensions['ocr']['config'].data_dir
    assert (data_dir / 'initial_admin_password.txt').is_file()

    response = api.post('/api/auth/password', json={
        'old_password': admin['password'], 'new_password': 'myNewPass123'})
    assert response.status_code == 200
    # 改密成功后初始密码文件应被删除
    assert not (data_dir / 'initial_admin_password.txt').exists()

    fresh = app.test_client()
    assert fresh.post('/api/auth/login', json={
        'username': admin['username'], 'password': 'myNewPass123'}).status_code == 200
    # 旧密码不再可用
    assert fresh.post('/api/auth/login', json={
        'username': admin['username'], 'password': admin['password']}).status_code == 401


def test_change_own_password_requires_correct_old(app, api_client, admin):
    api = api_client(admin['username'], admin['password'])
    wrong = api.post('/api/auth/password', json={
        'old_password': 'not-the-password', 'new_password': 'myNewPass123'})
    assert wrong.status_code == 400
    assert wrong.get_json()['error']['code'] == 'invalid_credentials'

    short = api.post('/api/auth/password', json={
        'old_password': admin['password'], 'new_password': 'short'})
    assert short.status_code == 400

    # 失败不应修改密码
    fresh = app.test_client()
    assert fresh.post('/api/auth/login', json={
        'username': admin['username'], 'password': admin['password']}).status_code == 200


def test_admin_reset_own_password_removes_initial_file(app, api_client, admin):
    """管理员在用户列表里重置自己的密码，也应清掉初始密码文件。"""
    api = api_client(admin['username'], admin['password'])
    data_dir = app.extensions['ocr']['config'].data_dir
    me = admin_self_id(api, admin['username'])

    response = api.patch('/api/users/%d' % me, json={'reset_password': True})
    assert response.status_code == 200
    new_password = response.get_json()['data']['new_password']
    assert new_password
    assert not (data_dir / 'initial_admin_password.txt').exists()

    fresh = app.test_client()
    assert fresh.post('/api/auth/login', json={
        'username': admin['username'], 'password': new_password}).status_code == 200


def test_reset_tool_sets_explicit_password(app, admin, capsys):
    module = load_tool('reset_admin.py')
    data_dir = str(app.extensions['ocr']['config'].data_dir)

    assert module.main(['--username', admin['username'], '--password', 'toolPass123',
                        '--data-dir', data_dir]) == 0
    output = capsys.readouterr().out
    assert '已重置用户' in output

    db = app.extensions['ocr']['db']
    row = users_repo.get_by_username(db, admin['username'])
    assert security.verify_password('toolPass123', row['password_hash'])
    assert not (Path(data_dir) / 'initial_admin_password.txt').exists()


def test_reset_tool_generates_password_and_lists_users(app, admin, capsys):
    module = load_tool('reset_admin.py')
    data_dir = str(app.extensions['ocr']['config'].data_dir)

    assert module.main(['--list', '--data-dir', data_dir]) == 0
    listing = capsys.readouterr().out
    assert admin['username'] in listing
    assert '管理员' in listing

    assert module.main(['--username', admin['username'], '--data-dir', data_dir]) == 0
    generated = capsys.readouterr().out
    assert '已重置用户' in generated


def test_reset_tool_rejects_bad_input(app, admin, capsys):
    module = load_tool('reset_admin.py')
    data_dir = str(app.extensions['ocr']['config'].data_dir)

    assert module.main(['--username', 'nobody', '--data-dir', data_dir]) == 1
    assert '用户不存在' in capsys.readouterr().out

    assert module.main(['--username', admin['username'], '--password', 'short',
                        '--data-dir', data_dir]) == 1
    assert '至少 8 位' in capsys.readouterr().out