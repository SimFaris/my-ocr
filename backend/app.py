# -*- coding: utf-8 -*-
"""应用装配：配置、数据库、认证、接口蓝图与前端静态资源。"""

import hmac
import logging
import os
import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory, session
from werkzeug.exceptions import HTTPException

from . import security
from .api import auth as auth_api
from .api import system as system_api
from .config import load_config
from .db import Database
from .logging_setup import setup_logging
from .repositories import users as users_repo
from .umi.manager import UmiManager

log = logging.getLogger(__name__)

CSRF_EXEMPT = frozenset(['/api/auth/login'])
SAFE_METHODS = frozenset(['GET', 'HEAD', 'OPTIONS'])


def load_or_create_session_key(path):
    """读取或生成会话签名密钥。"""
    if os.path.isfile(path):
        with open(path, 'rb') as handle:
            data = handle.read().strip()
        if data:
            return data
    data = secrets.token_bytes(48)
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, 'wb') as handle:
        handle.write(data)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return data


def _placeholder_page():
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<title>局域网离线 OCR</title></head>'
        '<body style="font-family:system-ui,Segoe UI,sans-serif;max-width:42em;'
        'margin:4em auto;line-height:1.8;color:#222">'
        '<h1>后端已启动</h1>'
        '<p>前端尚未构建。请在本机执行 <code>cd frontend</code> 与 '
        '<code>npm install</code>、<code>npm run build</code>，然后刷新本页。</p>'
        '<p>可用接口：<code>/api/system/status</code>（需登录）、'
        '<code>/api/system/root-cert</code>（下载根证书）。</p>'
        '</body></html>')


def create_app(config=None, base_dir=None):
    config = config or load_config(base_dir=base_dir)
    setup_logging(config.log_dir, config['log_level'])

    db = Database(config.db_path)
    db.init_schema()
    bootstrap = users_repo.ensure_initial_admin(db, config.data_dir)
    if bootstrap:
        log.warning('已创建初始管理员：%s，初始密码已写入 %s',
                    bootstrap[0], config.data_dir / 'initial_admin_password.txt')

    umi = UmiManager(config)

    app = Flask(__name__, static_folder=None)
    app.config['SECRET_KEY'] = load_or_create_session_key(str(config.session_secret_file))
    app.config['MAX_CONTENT_LENGTH'] = config.upload_max_bytes
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = False
    app.json.ensure_ascii = False

    app.extensions['ocr'] = {
        'config': config,
        'db': db,
        'umi': umi,
        'limiter': security.LoginRateLimiter(),
    }

    @app.before_request
    def _before_request():
        # 会话 Cookie 的 Secure 标记跟随当前请求是否为 https
        app.config['SESSION_COOKIE_SECURE'] = request.is_secure

        g.user = None
        uid = session.get('uid')
        if uid is not None:
            user = users_repo.get(db, uid)
            if user is not None and user['is_active']:
                g.user = user
            else:
                session.clear()

        if request.method in SAFE_METHODS or request.path in CSRF_EXEMPT:
            return None
        if g.user is None:
            return None
        expected = session.get('csrf') or ''
        provided = request.headers.get('X-CSRF-Token') or ''
        if not expected or not provided or not hmac.compare_digest(
                str(expected).encode('utf-8'), str(provided).encode('utf-8')):
            return jsonify({'ok': False, 'error': {
                'code': 'forbidden', 'message': 'CSRF 校验失败，请刷新页面后重试'}}), 403
        return None

    @app.errorhandler(Exception)
    def _unhandled(error):
        if isinstance(error, HTTPException):
            if error.code == 413:
                return jsonify({'ok': False, 'error': {
                    'code': 'payload_too_large',
                    'message': '文件超过大小限制（%d MB）' % config['upload_max_mb']}}), 413
            if request.path.startswith('/api/'):
                return jsonify({'ok': False, 'error': {
                    'code': 'not_found' if error.code == 404 else 'internal',
                    'message': error.description}}), error.code
            return error
        log.exception('未处理异常')
        return jsonify({'ok': False, 'error': {
            'code': 'internal', 'message': '服务器内部错误，详见服务端日志'}}), 500

    app.register_blueprint(auth_api.bp)
    app.register_blueprint(system_api.bp)

    dist_dir = Path(config['frontend_dist_dir'])

    @app.get('/')
    def _index():
        if (dist_dir / 'index.html').is_file():
            return send_from_directory(str(dist_dir), 'index.html')
        return _placeholder_page()

    @app.get('/<path:filename>')
    def _frontend(filename):
        if filename.startswith('api/'):
            return jsonify({'ok': False, 'error': {
                'code': 'not_found', 'message': '接口不存在'}}), 404
        target = dist_dir / filename
        if target.is_file():
            return send_from_directory(str(dist_dir), filename)
        if (dist_dir / 'index.html').is_file():
            return send_from_directory(str(dist_dir), 'index.html')
        return _placeholder_page()

    log.info('应用已装配：数据目录 %s，前端目录 %s', config.data_dir, dist_dir)
    return app