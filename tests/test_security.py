# -*- coding: utf-8 -*-
"""安全组件测试。"""

from backend import security


def test_hash_and_verify_password():
    stored = security.hash_password('secret123')
    assert stored.startswith('scrypt$')
    assert security.verify_password('secret123', stored)
    assert not security.verify_password('secret124', stored)


def test_verify_rejects_malformed_hash():
    assert not security.verify_password('x', '')
    assert not security.verify_password('x', 'not-a-hash')
    assert not security.verify_password('x', 'md5$1$2$3$4$5')


def test_generated_password_shape():
    password = security.generate_password()
    assert len(password) == 12
    assert password.isalnum()
    assert security.generate_password() != password


def test_csrf_token_is_unique_and_urlsafe():
    first = security.new_csrf_token()
    second = security.new_csrf_token()
    assert first != second
    assert len(first) > 20


def test_rate_limiter_locks_after_max_failures():
    limiter = security.LoginRateLimiter(max_failures=3, lock_seconds=60)
    key = 'admin|127.0.0.1'
    assert limiter.is_locked(key) is False
    limiter.record_failure(key)
    limiter.record_failure(key)
    assert limiter.is_locked(key) is False
    limiter.record_failure(key)
    assert limiter.is_locked(key) is True
    limiter.reset(key)
    assert limiter.is_locked(key) is False