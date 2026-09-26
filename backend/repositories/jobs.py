# -*- coding: utf-8 -*-
"""任务数据访问：创建、查询、状态流转与计数维护。"""

import json
import uuid

from ..utils import now_iso

JOB_STATUSES = ('draft', 'queued', 'running', 'done', 'partial', 'failed', 'canceled')
# pending：已上传但尚未提交；queued：已提交待识别
ITEM_STATUSES = ('pending', 'queued', 'running', 'done', 'empty', 'failed', 'skipped')
ACTIVE_STATUSES = ('queued', 'running')

_FIELDS = ('id, user_id, title, source_type, status, ocr_options, '
           'item_total, item_done, item_failed, created_at, started_at, finished_at')


def new_id():
    return uuid.uuid4().hex


def create(db, user_id, title, source_type, ocr_options):
    job_id = new_id()
    with db.transaction() as conn:
        conn.execute(
            'INSERT INTO jobs (id, user_id, title, source_type, status, ocr_options, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (job_id, user_id, title, source_type, 'draft',
             json.dumps(ocr_options or {}, ensure_ascii=False), now_iso()))
    return job_id


def get(db, job_id):
    return db.query_one('SELECT * FROM jobs WHERE id = ?', (job_id,))


def get_options(job):
    """解析任务上的识别参数。"""
    try:
        value = json.loads(job['ocr_options'] or '{}')
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def list_jobs(db, user_id=None, status=None, page=1, page_size=50, keyword=None):
    """分页列出任务，返回 (rows, total)。"""
    where = []
    params = []
    if user_id is not None:
        where.append('user_id = ?')
        params.append(user_id)
    if status:
        where.append('status = ?')
        params.append(status)
    if keyword:
        where.append('title LIKE ?')
        params.append('%' + keyword + '%')
    clause = (' WHERE ' + ' AND '.join(where)) if where else ''

    total_row = db.query_one('SELECT COUNT(*) AS n FROM jobs' + clause, tuple(params))
    total = int(total_row['n']) if total_row else 0
    page = max(1, int(page))
    page_size = min(200, max(1, int(page_size)))
    rows = db.query(
        'SELECT %s FROM jobs%s ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?'
        % (_FIELDS, clause), tuple(params) + (page_size, (page - 1) * page_size))
    return rows, total


def mark_submitted(db, job_id):
    """提交任务：进入排队状态，等待工作线程认领。"""
    with db.transaction() as conn:
        conn.execute("UPDATE jobs SET status = 'queued', finished_at = NULL WHERE id = ?", (job_id,))


def mark_started(db, job_id):
    """首次认领任务项时把任务置为进行中。"""
    with db.transaction() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'running', "
            "started_at = COALESCE(started_at, ?), finished_at = NULL WHERE id = ?",
            (now_iso(), job_id))


def set_status(db, job_id, status):
    with db.transaction() as conn:
        conn.execute('UPDATE jobs SET status = ? WHERE id = ?', (status, job_id))


def refresh_counts(db, job_id):
    """按任务项的真实状态重算计数；全部结束后落到终态。"""
    rows = db.query('SELECT status, COUNT(*) AS n FROM job_items WHERE job_id = ? GROUP BY status',
                    (job_id,))
    counts = dict((row['status'], int(row['n'])) for row in rows)
    total = sum(counts.values())
    done = counts.get('done', 0) + counts.get('empty', 0)
    failed = counts.get('failed', 0)
    unfinished = counts.get('pending', 0) + counts.get('queued', 0) + counts.get('running', 0)

    job = get(db, job_id)
    if job is None:
        return None
    status = job['status']
    finished_at = job['finished_at']

    if status in ('draft', 'canceled'):
        pass
    elif unfinished == 0:
        if failed == 0 and done > 0:
            status = 'done'
        elif done == 0:
            status = 'failed'
        else:
            status = 'partial'
        finished_at = finished_at or now_iso()
    else:
        status = 'running' if job['started_at'] else 'queued'
        finished_at = None

    with db.transaction() as conn:
        conn.execute(
            'UPDATE jobs SET item_total = ?, item_done = ?, item_failed = ?, '
            'status = ?, finished_at = ? WHERE id = ?',
            (total, done, failed, status, finished_at, job_id))
    return status


def delete(db, job_id):
    with db.transaction() as conn:
        conn.execute('DELETE FROM job_items WHERE job_id = ?', (job_id,))
        conn.execute('DELETE FROM jobs WHERE id = ?', (job_id,))


def recover_running(db):
    """服务启动时把中断的任务与任务项恢复为待办，返回恢复的项数。"""
    with db.transaction() as conn:
        cursor = conn.execute(
            "UPDATE job_items SET status = 'queued', started_at = NULL, umi_task_id = NULL "
            "WHERE status = 'running'")
        recovered = cursor.rowcount
        conn.execute(
            "UPDATE jobs SET status = 'queued', finished_at = NULL WHERE status = 'running'")
    return recovered


def job_summary(db):
    counts = dict((status, 0) for status in JOB_STATUSES)
    for row in db.query('SELECT status, COUNT(*) AS n FROM jobs GROUP BY status'):
        counts[row['status']] = int(row['n'])
    return counts


def item_summary(db):
    counts = dict((status, 0) for status in ITEM_STATUSES)
    for row in db.query('SELECT status, COUNT(*) AS n FROM job_items GROUP BY status'):
        counts[row['status']] = int(row['n'])
    return counts


def queue_summary(db):
    """系统状态页使用的队列概览。"""
    items = item_summary(db)
    return {
        'pending': items.get('queued', 0),
        'running': items.get('running', 0),
        'done': items.get('done', 0) + items.get('empty', 0),
        'failed': items.get('failed', 0),
        'unsubmitted': items.get('pending', 0),
        'items': items,
        'jobs': job_summary(db),
    }