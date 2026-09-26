# -*- coding: utf-8 -*-
"""任务项数据访问：上传登记、原子认领、状态与结果落库、调度查询。"""

import json
import uuid

from ..utils import now_iso

_FIELDS = ('id, job_id, seq, kind, source, original_name, stored_relpath, byte_size, status, '
           'umi_task_id, page_total, page_done, text_relpath, artifact_relpaths, char_count, '
           'preview, error_code, error_message, attempts, queued_at, started_at, finished_at, '
           'duration_ms')


def new_id():
    return uuid.uuid4().hex


def add(db, job_id, kind, source, original_name, stored_relpath, byte_size, item_id=None):
    """登记一个任务项，状态为 pending（已上传未提交）。"""
    item_id = item_id or new_id()
    row = db.query_one('SELECT COALESCE(MAX(seq), 0) AS m FROM job_items WHERE job_id = ?', (job_id,))
    seq = int(row['m']) + 1 if row else 1
    with db.transaction() as conn:
        conn.execute(
            'INSERT INTO job_items (id, job_id, seq, kind, source, original_name, stored_relpath, '
            'byte_size, status, attempts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)',
            (item_id, job_id, seq, kind, source, original_name, stored_relpath, int(byte_size), 'pending'))
    return get(db, item_id)


def get(db, item_id):
    return db.query_one('SELECT * FROM job_items WHERE id = ?', (item_id,))


def list_items(db, job_id, page=1, page_size=100, status=None):
    where = ['job_id = ?']
    params = [job_id]
    if status:
        where.append('status = ?')
        params.append(status)
    clause = ' WHERE ' + ' AND '.join(where)
    total_row = db.query_one('SELECT COUNT(*) AS n FROM job_items' + clause, tuple(params))
    total = int(total_row['n']) if total_row else 0
    page = max(1, int(page))
    page_size = min(500, max(1, int(page_size)))
    rows = db.query(
        'SELECT %s FROM job_items%s ORDER BY seq LIMIT ? OFFSET ?' % (_FIELDS, clause),
        tuple(params) + (page_size, (page - 1) * page_size))
    return rows, total


def list_all(db, job_id, status=None):
    """取出全部任务项（导出、批量重试用），不分页。"""
    where = ['job_id = ?']
    params = [job_id]
    if status:
        where.append('status = ?')
        params.append(status)
    return db.query(
        'SELECT %s FROM job_items WHERE %s ORDER BY seq' % (_FIELDS, ' AND '.join(where)),
        tuple(params))


def mark_queued(db, job_id):
    """把待提交的项置为排队，返回受影响行数。"""
    with db.transaction() as conn:
        cursor = conn.execute(
            "UPDATE job_items SET status = 'queued', queued_at = ? "
            "WHERE job_id = ? AND status = 'pending'", (now_iso(), job_id))
        return cursor.rowcount


def claim(db, item_id):
    """原子领取：只有仍处于 queued 的项才能被置为 running。"""
    with db.transaction() as conn:
        cursor = conn.execute(
            "UPDATE job_items SET status = 'running', started_at = ?, attempts = attempts + 1 "
            "WHERE id = ? AND status = 'queued'", (now_iso(), item_id))
        claimed = cursor.rowcount == 1
    return claimed


def set_progress(db, item_id, page_done=None, page_total=None):
    with db.transaction() as conn:
        conn.execute(
            'UPDATE job_items SET page_done = COALESCE(?, page_done), '
            'page_total = COALESCE(?, page_total) WHERE id = ?',
            (page_done, page_total, item_id))


def finish(db, item_id, status, text_relpath=None, char_count=None, preview=None,
           error_code=None, error_message=None, duration_ms=None, artifacts=None):
    with db.transaction() as conn:
        conn.execute(
            'UPDATE job_items SET status = ?, text_relpath = COALESCE(?, text_relpath), '
            'char_count = ?, preview = ?, error_code = ?, error_message = ?, '
            'duration_ms = ?, finished_at = ?, artifact_relpaths = COALESCE(?, artifact_relpaths) '
            'WHERE id = ?',
            (status, text_relpath, char_count, preview, error_code, error_message,
             duration_ms, now_iso(),
             json.dumps(artifacts, ensure_ascii=False) if artifacts else None, item_id))


def save_text(db, item_id, text_relpath, char_count, preview):
    """人工校对后保存文本，同时刷新字数与预览。"""
    with db.transaction() as conn:
        conn.execute(
            'UPDATE job_items SET text_relpath = ?, char_count = ?, preview = ? WHERE id = ?',
            (text_relpath, char_count, preview, item_id))


def requeue_failed(db, job_id, item_ids=None):
    """把失败或跳过的项重新排队，返回受影响行数。"""
    sql = ("UPDATE job_items SET status = 'queued', queued_at = ?, error_code = NULL, "
           "error_message = NULL, started_at = NULL, finished_at = NULL WHERE job_id = ? "
           "AND status IN ('failed', 'skipped')")
    params = [now_iso(), job_id]
    if item_ids:
        placeholders = ','.join('?' for _ in item_ids)
        sql += ' AND id IN (%s)' % placeholders
        params.extend(item_ids)
    with db.transaction() as conn:
        cursor = conn.execute(sql, tuple(params))
        return cursor.rowcount


def skip_unfinished(db, job_id):
    """取消任务时跳过尚未完成的项，返回受影响行数。"""
    with db.transaction() as conn:
        cursor = conn.execute(
            "UPDATE job_items SET status = 'skipped', finished_at = ? "
            "WHERE job_id = ? AND status IN ('pending', 'queued')", (now_iso(), job_id))
        return cursor.rowcount


def active_count(db, job_id):
    row = db.query_one(
        "SELECT COUNT(*) AS n FROM job_items WHERE job_id = ? AND status IN ('queued', 'running')",
        (job_id,))
    return int(row['n']) if row else 0


# ---------- 调度查询 ----------


def queued_users(db):
    """有排队任务的用户，按最早排队时间排序。只统计已提交的任务。"""
    return db.query(
        "SELECT j.user_id AS user_id, MIN(i.queued_at) AS first_at, COUNT(*) AS n "
        "FROM job_items i JOIN jobs j ON j.id = i.job_id "
        "WHERE i.status = 'queued' AND j.status IN ('queued', 'running') "
        "GROUP BY j.user_id ORDER BY first_at")


def claim_oldest_for_user(db, user_id):
    """领取该用户最早排队的项；返回任务项行，没有则返回 None。"""
    candidate = db.query_one(
        "SELECT i.id AS id FROM job_items i JOIN jobs j ON j.id = i.job_id "
        "WHERE i.status = 'queued' AND j.status IN ('queued', 'running') AND j.user_id = ? "
        "ORDER BY i.queued_at, i.seq LIMIT 1", (user_id,))
    if candidate is None:
        return None
    if not claim(db, candidate['id']):
        return None
    return get(db, candidate['id'])