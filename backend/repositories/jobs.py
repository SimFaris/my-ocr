# -*- coding: utf-8 -*-
"""任务与任务项的统计查询。M1 阶段系统状态页需要，M2 起扩展为完整任务仓库。"""

JOB_STATUSES = ('draft', 'queued', 'running', 'done', 'partial', 'failed', 'canceled')
ITEM_STATUSES = ('queued', 'running', 'done', 'empty', 'failed', 'skipped')


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
    """给系统状态页使用的队列概览。"""
    items = item_summary(db)
    return {
        'pending': items.get('queued', 0),
        'running': items.get('running', 0),
        'done': items.get('done', 0) + items.get('empty', 0),
        'failed': items.get('failed', 0),
        'items': items,
        'jobs': job_summary(db),
    }