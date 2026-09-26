# -*- coding: utf-8 -*-
"""运行时设置（key/value）。"""

_UPSERT = ('INSERT INTO settings (key, value) VALUES (?, ?) '
           'ON CONFLICT(key) DO UPDATE SET value = excluded.value')


def get(db, key, default=None):
    row = db.query_one('SELECT value FROM settings WHERE key = ?', (key,))
    return row['value'] if row else default


def get_all(db):
    return dict((row['key'], row['value'])
                for row in db.query('SELECT key, value FROM settings'))


def set_value(db, key, value):
    with db.transaction() as conn:
        conn.execute(_UPSERT, (str(key), str(value)))


def set_many(db, values):
    with db.transaction() as conn:
        for key, value in values.items():
            conn.execute(_UPSERT, (str(key), str(value)))