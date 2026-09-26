# -*- coding: utf-8 -*-
"""SQLite 连接管理与建表。"""

import contextlib
import sqlite3
import threading
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    source_type TEXT NOT NULL,
    status TEXT NOT NULL,
    ocr_options TEXT NOT NULL,
    item_total INTEGER NOT NULL DEFAULT 0,
    item_done INTEGER NOT NULL DEFAULT 0,
    item_failed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS job_items (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    original_name TEXT NOT NULL,
    stored_relpath TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    status TEXT NOT NULL,
    umi_task_id TEXT,
    page_total INTEGER,
    page_done INTEGER,
    text_relpath TEXT,
    artifact_relpaths TEXT,
    char_count INTEGER,
    preview TEXT,
    error_code TEXT,
    error_message TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    queued_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    duration_ms INTEGER
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    target TEXT,
    detail TEXT,
    ip TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_items_job ON job_items(job_id, seq);
CREATE INDEX IF NOT EXISTS idx_items_status ON job_items(status, queued_at);
CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);
"""


class Database(object):
    """按线程持有连接的 SQLite 访问层。"""

    def __init__(self, path):
        self.path = str(path)
        self._local = threading.local()

    def connect(self):
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, timeout=10.0,
                                   isolation_level=None, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('PRAGMA busy_timeout=5000')
            self._local.conn = conn
        return conn

    def close(self):
        conn = getattr(self._local, 'conn', None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    @contextlib.contextmanager
    def transaction(self):
        conn = self.connect()
        conn.execute('BEGIN IMMEDIATE')
        try:
            yield conn
        except Exception:
            conn.execute('ROLLBACK')
            raise
        conn.execute('COMMIT')

    def execute(self, sql, params=()):
        return self.connect().execute(sql, params)

    def query(self, sql, params=()):
        return self.connect().execute(sql, params).fetchall()

    def query_one(self, sql, params=()):
        return self.connect().execute(sql, params).fetchone()

    def init_schema(self):
        conn = self.connect()
        conn.executescript(SCHEMA_SQL)
        conn.execute('PRAGMA user_version = %d' % SCHEMA_VERSION)
        return SCHEMA_VERSION