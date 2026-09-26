# -*- coding: utf-8 -*-
"""认证接口：登录、注销、当前用户、改密码。"""

import logging
from pathlib import Path

from flask import Blueprint, request, session

from .. import security
from ..repositories import audit
from ..repositories import users as users_repo
from .common import client_ip, context, fail, ok

log = logging.getLogger(__name__)

bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@bp.post('/login')
def login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get('username') or '').strip()
    password = str(payload.get('password') or '')
    if not username or not password:
        return fail('invalid_request', '请输入用户名和密码', 400)

    ctx = context()
    db = ctx['db']
    limiter = ctx['limiter']
    ip = client_ip()
    limit_key = '%s|%s' % (username.lower(), ip)
    if limiter.is_locked(limit_key):
        return fail('rate_limited', '失败次数过多，请 5 分钟后再试', 429)

    user = users_repo.get_by_username(db, username)
    if user is None or not user['is_active'] or not security.verify_password(password, user['password_hash']):
        limiter.record_failure(limit_key)
        audit.write(db, 'login_failed', user_id=user['id'] if user else None,
                    target=username, ip=ip)
        return fail('invalid_credentials', '用户名或密码错误', 401)

    limiter.reset(limit_key)
    session.clear()
    session['uid'] = user['id']
    session['csrf'] = security.new_csrf_token()
    session.permanent = True
    users_repo.touch_login(db, user['id'])
    audit.write(db, 'login', user_id=user['id'], ip=ip)
    return ok({'user': users_repo.public_view(user), 'csrf': session['csrf']})


@bp.post('/logout')
def logout():
    ctx = context()
    user = security.current_user()
    session.clear()
    if user is not None:
        audit.write(ctx['db'], 'logout', user_id=user['id'], ip=client_ip())
    return ok({'logged_out': True})


@bp.get('/me')
def me():
    user = security.current_user()
    if user is None:
        return fail('auth_required', '请先登录', 401)
    token = session.get('csrf')
    if not token:
        token = security.new_csrf_token()
        session['csrf'] = token
    return ok({'user': users_repo.public_view(user), 'csrf': token})


@bp.post('/password')
def change_password():
    ctx = context()
    user = security.current_user()
    if user is None:
        return fail('auth_required', '请先登录', 401)

    payload = request.get_json(silent=True) or {}
    old_password = str(payload.get('old_password') or '')
    new_password = str(payload.get('new_password') or '')
    if len(new_password) < 8:
        return fail('invalid_request', '新密码至少 8 位', 400)
    if not security.verify_password(old_password, user['password_hash']):
        return fail('invalid_credentials', '原密码不正确', 400)

    db = ctx['db']
    users_repo.set_password(db, user['id'], new_password)
    audit.write(db, 'password_changed', user_id=user['id'], ip=client_ip())
    _drop_initial_password_file(ctx['config'].data_dir)
    return ok({'changed': True})


def _drop_initial_password_file(data_dir):
    """改密成功后删除初始密码文件。"""
    marker = Path(data_dir) / 'initial_admin_password.txt'
    try:
        if marker.is_file():
            marker.unlink()
    except OSError as exc:
        log.warning('删除初始密码文件失败：%s', exc)