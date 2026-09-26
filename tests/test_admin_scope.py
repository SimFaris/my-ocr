# -*- coding: utf-8 -*-
"""管理员跨用户查看与任务来源记录测试。"""

import sqlite3

from backend.db import Database

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 40


def make_job(api, title):
    response = api.post('/api/jobs', json={'title': title, 'source_type': 'image'})
    assert response.status_code == 201
    return response.get_json()['data']['job']


def test_admin_sees_all_jobs_with_scope(api_client, admin, make_user):
    admin_api = api_client(admin['username'], admin['password'])
    make_job(admin_api, '管理员的任务')

    bob = make_user('bob')
    bob_api = api_client(bob['username'], bob['password'])
    bob_job = make_job(bob_api, '小张的任务')

    mine = admin_api.get('/api/jobs?scope=mine').get_json()['data']
    assert mine['total'] == 1
    assert mine['scope'] == 'mine'

    everything = admin_api.get('/api/jobs?scope=all').get_json()['data']
    assert everything['total'] == 2
    assert everything['scope'] == 'all'
    assert sorted(item['username'] for item in everything['items']) == [admin['username'], 'bob']

    # 管理员可以直接打开别人的任务详情
    assert admin_api.get('/api/jobs/%s' % bob_job['id']).status_code == 200

    # 普通用户传 scope=all 无效，仍然只能看到自己的
    assert bob_api.get('/api/jobs?scope=all').get_json()['data']['total'] == 1


def test_client_ip_recorded_and_visible_to_admin(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    job = make_job(api, '来源记录')
    assert job['client_ip'] == '127.0.0.1'

    listing = api.get('/api/jobs?scope=all').get_json()['data']['items']
    assert listing[0]['client_ip'] == '127.0.0.1'
    assert 'username' in listing[0]

    detail = api.get('/api/jobs/%s' % job['id']).get_json()['data']['job']
    assert detail['client_ip'] == '127.0.0.1'


def test_client_ip_hidden_from_normal_user(api_client, make_user):
    bob = make_user('bob')
    api = api_client(bob['username'], bob['password'])
    job = make_job(api, '普通用户的任务')
    assert 'client_ip' not in job

    listing = api.get('/api/jobs').get_json()['data']['items']
    assert 'client_ip' not in listing[0]


def test_admin_search_all_scope_includes_username(api_client, admin, make_user):
    bob = make_user('bob')
    bob_api = api_client(bob['username'], bob['password'])
    bob_api.post('/api/jobs', json={'title': '发票报销单据', 'source_type': 'image'})

    admin_api = api_client(admin['username'], admin['password'])
    payload = admin_api.get('/api/search?q=发票&scope=all').get_json()['data']
    assert len(payload['jobs']) == 1
    assert payload['jobs'][0]['username'] == 'bob'

    mine = admin_api.get('/api/search?q=发票').get_json()['data']
    assert mine['jobs'] == []


def test_migration_upgrades_old_database(tmp_path):
    """老版本数据库（没有来源列）应自动升级且不丢数据。"""
    path = tmp_path / 'old.db'
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
            display_name TEXT, password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user', is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, last_login_at TEXT);
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, title TEXT NOT NULL,
            source_type TEXT NOT NULL, status TEXT NOT NULL, ocr_options TEXT NOT NULL,
            item_total INTEGER NOT NULL DEFAULT 0, item_done INTEGER NOT NULL DEFAULT 0,
            item_failed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
            started_at TEXT, finished_at TEXT);
        INSERT INTO users (username, password_hash, created_at)
            VALUES ('olduser', 'scrypt$1$1$1$aaaa$bbbb', '2026-01-01T00:00:00Z');
        INSERT INTO jobs (id, user_id, title, source_type, status, ocr_options, created_at)
            VALUES ('j-old', 1, '老任务', 'image', 'done', '{}', '2026-01-01T00:00:00Z');
        PRAGMA user_version = 1;
    """)
    conn.commit()
    conn.close()

    db = Database(path)
    assert db.init_schema() == 2

    columns = [row[1] for row in db.query('PRAGMA table_info(jobs)')]
    assert 'client_ip' in columns
    assert 'client_host' in columns

    row = db.query_one("SELECT title, client_ip FROM jobs WHERE id = 'j-old'")
    assert row['title'] == '老任务'
    assert row['client_ip'] is None
    assert db.query_one('PRAGMA user_version')[0] == 2


def test_migration_is_idempotent(app):
    """重复执行迁移不应报错。"""
    db = app.extensions['ocr']['db']
    assert db.init_schema() == 2
    assert db.init_schema() == 2