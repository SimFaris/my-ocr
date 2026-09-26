# -*- coding: utf-8 -*-
"""审计日志。"""

import json
import logging

from ..utils import now_iso

log = logging.getLogger(__name__)


def write(db, action, user_id=None, target=None, detail=None, ip=None):
    """写一条审计记录；失败只记日志，不影响主流程。"""
    if isinstance(detail, (dict, list)):
        detail = json.dumps(detail, ensure_ascii=False)
    try:
        with db.transaction() as conn:
            conn.execute(
                'INSERT INTO audit_log (user_id, action, target, detail, ip, created_at) '
                'VALUES (?, ?, ?, ?, ?, ?)',
                (user_id, action, target, detail, ip, now_iso()))
    except Exception as exc:
        log.warning('写审计日志失败：%s', exc)


def recent(db, limit=50):
    return db.query(
        'SELECT a.id, a.user_id, a.action, a.target, a.detail, a.ip, a.created_at, u.username '
        'FROM audit_log a LEFT JOIN users u ON u.id = a.user_id '
        'ORDER BY a.id DESC LIMIT ?', (int(limit),))