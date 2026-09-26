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


@pytest.fixture
def app_config(tmp_path):
    """测试用配置：独立数据目录，Umi 指向一个必然连不上的端口。"""
    return load_config(base_dir=PROJECT_ROOT, env={
        'OCR_DATA_DIR': str(tmp_path / 'data'),
        'OCR_UMI_AUTOSTART': 'false',
        'OCR_UMI_PORT': '9',
    })


@pytest.fixture
def app(app_config):
    application = create_app(app_config)
    application.config['TESTING'] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


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