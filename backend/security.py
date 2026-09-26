# -*- coding: utf-8 -*-
"""密码哈希、CSRF、登录限速与访问控制装饰器。"""

import base64
import functools
import hashlib
import hmac
import os
import secrets
import threading
import time

from flask import g, jsonify

SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32


def hash_password(password):
    """生成 scrypt$n$r$p$salt$hash 格式的密码哈希。"""
    salt = os.urandom(16)
    derived = hashlib.scrypt(password.encode('utf-8'), salt=salt,
                             n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN)
    return 'scrypt$%d$%d$%d$%s$%s' % (
        SCRYPT_N, SCRYPT_R, SCRYPT_P,
        base64.b64encode(salt).decode('ascii'),
        base64.b64encode(derived).decode('ascii'))


def verify_password(password, stored):
    """校验密码；格式异常一律视为不匹配。"""
    try:
        algo, n, r, p, salt_b64, hash_b64 = str(stored).split('$')
        if algo != 'scrypt':
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        derived = hashlib.scrypt(password.encode('utf-8'), salt=salt,
                                 n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError, AttributeError):
        return False
    return hmac.compare_digest(derived, expected)


def generate_password(length=12):
    """生成随机初始密码（去掉易混淆字符）。"""
    alphabet = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def new_csrf_token():
    return secrets.token_urlsafe(24)


class LoginRateLimiter(object):
    """同一用户名+IP 连续失败后锁定；进程内存实现，重启即清空。"""

    def __init__(self, max_failures=5, lock_seconds=300):
        self.max_failures = int(max_failures)
        self.lock_seconds = int(lock_seconds)
        self._entries = {}
        self._lock = threading.Lock()

    def is_locked(self, key):
        now = time.time()
        with self._lock:
            entry = self._entries.get(str(key))
            if not entry:
                return False
            _count, first_at, locked_until = entry
            if locked_until > now:
                return True
            if now - first_at > self.lock_seconds:
                self._entries.pop(str(key), None)
            return False

    def record_failure(self, key):
        now = time.time()
        with self._lock:
            name = str(key)
            count, first_at, _locked = self._entries.get(name, (0, now, 0.0))
            if now - first_at > self.lock_seconds:
                count, first_at = 0, now
            count += 1
            locked_until = now + self.lock_seconds if count >= self.max_failures else 0.0
            self._entries[name] = (count, first_at, locked_until)
            return count

    def reset(self, key):
        with self._lock:
            self._entries.pop(str(key), None)


def current_user():
    """当前登录用户（sqlite3.Row 或 None），由 before_request 注入。"""
    return getattr(g, 'user', None)


def login_required(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return jsonify({'ok': False, 'error': {
                'code': 'auth_required', 'message': '请先登录'}}), 401
        return view(*args, **kwargs)
    return wrapper


def admin_required(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({'ok': False, 'error': {
                'code': 'auth_required', 'message': '请先登录'}}), 401
        if user['role'] != 'admin':
            return jsonify({'ok': False, 'error': {
                'code': 'forbidden', 'message': '需要管理员权限'}}), 403
        return view(*args, **kwargs)
    return wrapper