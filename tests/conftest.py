# -*- coding: utf-8 -*-
"""pytest 公共夹具。"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import create_app      # noqa: E402
from backend.config import load_config  # noqa: E402


def build_config(tmp_path, overrides=None):
    """测试配置：独立数据目录、指向必然连不上的 Umi 端口、前端目录默认不存在。

    前端目录默认指向一个不存在的路径，让"前端未构建时的占位页"行为可确定复现；
    需要验证静态文件托管时用 app_factory(dist_dir=...) 指定真实目录。
    """
    values = {
        'data_dir': str(tmp_path / 'data'),
        'frontend_dist_dir': str(tmp_path / 'no-frontend'),
        'umi_autostart': False,
        'umi_port': 9,
    }
    if overrides:
        values.update(overrides)
    return load_config(base_dir=PROJECT_ROOT, env={}, overrides=values)


@pytest.fixture
def app_config(tmp_path):
    return build_config(tmp_path)


@pytest.fixture
def app(app_config):
    application = create_app(app_config)
    application.config['TESTING'] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def app_factory(tmp_path):
    """按需构造应用，可覆盖任意配置项。"""
    def make(**overrides):
        application = create_app(build_config(tmp_path, overrides))
        application.config['TESTING'] = True
        return application
    return make


@pytest.fixture
def admin(app):
    """读取首次启动生成的初始管理员账号。"""
    marker = app.extensions['ocr']['config'].data_dir / 'initial_admin_password.txt'
    username = ''
    password = ''
    for line in marker.read_text(encoding='utf-8').splitlines():
        if line.startswith('用户名：'):
            username = line.split('：', 1)[1].strip()
        elif line.startswith('密码：'):
            password = line.split('：', 1)[1].strip()
    assert username and password, '未能从 %s 解析初始账号' % marker
    return {'username': username, 'password': password}


@pytest.fixture
def logged_in(client, admin):
    """返回 (client, csrf_token)，已完成登录。"""
    response = client.post('/api/auth/login', json=admin)
    assert response.status_code == 200, response.get_data(as_text=True)
    return client, response.get_json()['data']['csrf']

class ApiClient(object):
    """测试用接口客户端：自动带上会话 Cookie 与 CSRF 头。"""

    def __init__(self, client, csrf):
        self.client = client
        self.csrf = csrf

    def request(self, method, path, **kwargs):
        headers = dict(kwargs.pop('headers', None) or {})
        if method.upper() not in ('GET', 'HEAD', 'OPTIONS'):
            headers['X-CSRF-Token'] = self.csrf
        return self.client.open(path, method=method, headers=headers, **kwargs)

    def get(self, path, **kwargs):
        return self.request('GET', path, **kwargs)

    def post(self, path, **kwargs):
        return self.request('POST', path, **kwargs)

    def put(self, path, **kwargs):
        return self.request('PUT', path, **kwargs)

    def delete(self, path, **kwargs):
        return self.request('DELETE', path, **kwargs)


@pytest.fixture
def api_client(app):
    """在同一个应用上以指定账号登录，返回带 CSRF 头的接口客户端。"""
    def login(username, password):
        client = app.test_client()
        response = client.post('/api/auth/login', json={'username': username, 'password': password})
        assert response.status_code == 200, response.get_data(as_text=True)
        return ApiClient(client, response.get_json()['data']['csrf'])
    return login


@pytest.fixture
def make_user(app):
    """直接建用户，用于验证多用户隔离。"""
    from backend.repositories import users as users_repo

    def create(username, password='password123', role='user'):
        users_repo.create(app.extensions['ocr']['db'], username, password,
                          display_name=username, role=role)
        return {'username': username, 'password': password}
    return create


def wait_until(predicate, timeout=20.0, interval=0.1):
    """轮询等待条件成立，超时返回 False。"""
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False

@pytest.fixture
def login_on():
    """在指定应用实例上新建账号并登录，返回带 CSRF 头的接口客户端。"""
    def make(app, username='tester', password='password123', role='admin'):
        from backend.repositories import users as users_repo

        users_repo.create(app.extensions['ocr']['db'], username, password,
                          display_name=username, role=role)
        client = app.test_client()
        response = client.post('/api/auth/login', json={'username': username, 'password': password})
        assert response.status_code == 200, response.get_data(as_text=True)
        return ApiClient(client, response.get_json()['data']['csrf'])
    return make