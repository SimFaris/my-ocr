# -*- coding: utf-8 -*-
"""用户数据访问。"""

from pathlib import Path

from .. import security
from ..utils import now_iso

_PUBLIC_FIELDS = 'id, username, display_name, role, is_active, created_at, last_login_at'


def create(db, username, password, display_name=None, role='user'):
    with db.transaction() as conn:
        cursor = conn.execute(
            'INSERT INTO users (username, display_name, password_hash, role, is_active, created_at) '
            'VALUES (?, ?, ?, ?, 1, ?)',
            (username, display_name or username, security.hash_password(password), role, now_iso()))
        return cursor.lastrowid


def get(db, user_id):
    return db.query_one('SELECT * FROM users WHERE id = ?', (user_id,))


def get_by_username(db, username):
    return db.query_one('SELECT * FROM users WHERE lower(username) = lower(?)', (username,))


def list_all(db):
    return db.query('SELECT %s FROM users ORDER BY id' % _PUBLIC_FIELDS)


def count(db):
    row = db.query_one('SELECT COUNT(*) AS n FROM users')
    return int(row['n']) if row else 0


def set_password(db, user_id, password):
    with db.transaction() as conn:
        conn.execute('UPDATE users SET password_hash = ? WHERE id = ?',
                     (security.hash_password(password), user_id))


def set_active(db, user_id, active):
    with db.transaction() as conn:
        conn.execute('UPDATE users SET is_active = ? WHERE id = ?',
                     (1 if active else 0, user_id))


def set_display_name(db, user_id, display_name):
    with db.transaction() as conn:
        conn.execute('UPDATE users SET display_name = ? WHERE id = ?', (display_name, user_id))


def set_role(db, user_id, role):
    with db.transaction() as conn:
        conn.execute('UPDATE users SET role = ? WHERE id = ?', (role, user_id))


def touch_login(db, user_id):
    with db.transaction() as conn:
        conn.execute('UPDATE users SET last_login_at = ? WHERE id = ?', (now_iso(), user_id))


def public_view(row):
    """转成可直接返回给前端的字典。"""
    if row is None:
        return None
    return {
        'id': row['id'],
        'username': row['username'],
        'display_name': row['display_name'],
        'role': row['role'],
        'is_active': bool(row['is_active']),
        'created_at': row['created_at'],
        'last_login_at': row['last_login_at'],
    }


def ensure_initial_admin(db, data_dir, username='admin'):
    """首次启动时创建管理员，返回 (用户名, 明文密码)；已有用户则返回 None。"""
    if count(db) > 0:
        return None
    password = security.generate_password()
    create(db, username, password, display_name='系统管理员', role='admin')
    marker = Path(data_dir) / 'initial_admin_password.txt'
    marker.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '初始管理员账号（首次启动自动生成）',
        '用户名：%s' % username,
        '密码：%s' % password,
        '',
        '请登录后立即修改密码，修改成功后本文件会被自动删除。',
    ]
    with open(str(marker), 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines) + '\n')
    return username, password