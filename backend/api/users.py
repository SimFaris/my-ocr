# -*- coding: utf-8 -*-
"""用户管理接口（仅管理员）。"""

import logging
import re

from flask import Blueprint, request

from .. import security
from ..repositories import audit
from ..repositories import users as users_repo
from ..security import admin_required, current_user
from .common import client_ip, context, fail, ok

log = logging.getLogger(__name__)

bp = Blueprint('users', __name__)

USERNAME_PATTERN = re.compile(r'^[A-Za-z0-9_.-]{3,32}$')
ROLES = ('user', 'admin')
MIN_PASSWORD_LENGTH = 8


def _check_username(value):
    text = str(value or '').strip()
    if not USERNAME_PATTERN.match(text):
        return None, '用户名需为 3-32 位字母、数字、下划线、点或短横线'
    return text, None


@bp.get('/api/users')
@admin_required
def list_users():
    db = context()['db']
    return ok({'items': [users_repo.public_view(row) for row in users_repo.list_all(db)]})


@bp.post('/api/users')
@admin_required
def create_user():
    db = context()['db']
    payload = request.get_json(silent=True) or {}

    username, error = _check_username(payload.get('username'))
    if error:
        return fail('invalid_request', error, 400)

    provided = payload.get('password')
    password = str(provided) if provided else security.generate_password()
    if len(password) < MIN_PASSWORD_LENGTH:
        return fail('invalid_request', '密码至少 8 位', 400)

    role = str(payload.get('role') or 'user')
    if role not in ROLES:
        return fail('invalid_request', 'role 只能是 user 或 admin', 400)

    if users_repo.get_by_username(db, username) is not None:
        return fail('conflict', '用户名已存在', 409)

    user_id = users_repo.create(db, username, password,
                                display_name=payload.get('display_name') or username, role=role)
    audit.write(db, 'user_created', user_id=current_user()['id'], target=username,
                detail={'role': role}, ip=client_ip())
    return ok({
        'user': users_repo.public_view(users_repo.get(db, user_id)),
        'initial_password': password if not provided else None,
    }, 201)


@bp.patch('/api/users/<int:user_id>')
@admin_required
def update_user(user_id):
    db = context()['db']
    actor = current_user()
    target = users_repo.get(db, user_id)
    if target is None:
        return fail('not_found', '用户不存在', 404)

    payload = request.get_json(silent=True) or {}
    changed = {}

    if 'role' in payload:
        role = str(payload['role'])
        if role not in ROLES:
            return fail('invalid_request', 'role 只能是 user 或 admin', 400)
        if user_id == actor['id'] and role != 'admin':
            return fail('conflict', '不能把自己降为普通用户', 409)
        users_repo.set_role(db, user_id, role)
        changed['role'] = role

    if 'is_active' in payload:
        active = bool(payload['is_active'])
        if user_id == actor['id'] and not active:
            return fail('conflict', '不能停用当前登录的账号', 409)
        users_repo.set_active(db, user_id, active)
        changed['is_active'] = active

    if payload.get('display_name'):
        display_name = str(payload['display_name']).strip()
        users_repo.set_display_name(db, user_id, display_name)
        changed['display_name'] = display_name

    new_password = None
    if payload.get('password') or payload.get('reset_password'):
        new_password = str(payload.get('password') or security.generate_password())
        if len(new_password) < MIN_PASSWORD_LENGTH:
            return fail('invalid_request', '密码至少 8 位', 400)
        users_repo.set_password(db, user_id, new_password)
        changed['password_reset'] = True
        if user_id == actor['id']:
            # 自己改了密码，初始密码文件就不再有效了
            users_repo.drop_initial_password_file(context()['config'].data_dir)

    if not changed:
        return fail('invalid_request', '没有需要修改的内容', 400)

    audit.write(db, 'user_updated', user_id=actor['id'], target=target['username'],
                detail=changed, ip=client_ip())
    return ok({
        'user': users_repo.public_view(users_repo.get(db, user_id)),
        'new_password': new_password if payload.get('reset_password') else None,
    })