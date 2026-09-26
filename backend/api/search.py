# -*- coding: utf-8 -*-
"""历史检索：按任务标题、文件名与识别文本开头查找关键字。

说明：识别全文存放在结果文件里，逐条读文件检索在任务量大时太慢，所以这里检索的是
入库时保存的文本开头片段（默认前 200 字）与文件名。需要全文检索时可在任务详情页下载
该任务的导出文件后自行搜索。
"""

import logging

from flask import Blueprint, request

from ..security import current_user, login_required
from .common import context, fail, item_view, job_view, ok

log = logging.getLogger(__name__)

bp = Blueprint('search', __name__)

PREVIEW_CHARS = 200
SNIPPET_WIDTH = 60

_ITEM_FIELDS = ('i.id, i.job_id, i.seq, i.kind, i.source, i.original_name, i.byte_size, '
                'i.status, i.char_count, i.preview, i.text_relpath, i.artifact_relpaths, '
                'i.error_code, i.error_message, i.duration_ms, i.page_total, i.page_done, '
                'i.attempts, i.queued_at, i.started_at, i.finished_at, j.user_id')


def _snippet(preview, keyword):
    """截取关键字附近的片段，便于在结果里一眼看到命中位置。"""
    text = (preview or '').replace('\n', ' ').strip()
    if not text:
        return ''
    position = text.find(keyword)
    if position < 0:
        return text[:SNIPPET_WIDTH]
    start = max(0, position - SNIPPET_WIDTH // 3)
    head = '…' if start > 0 else ''
    tail = '…' if start + SNIPPET_WIDTH < len(text) else ''
    return head + text[start:start + SNIPPET_WIDTH] + tail


@bp.get('/api/search')
@login_required
def search():
    ctx = context()
    db = ctx['db']
    user = current_user()

    keyword = (request.args.get('q') or '').strip()
    if not keyword:
        return fail('invalid_request', '请输入要检索的关键字', 400)
    limit = min(200, max(1, int(request.args.get('limit') or 50)))
    scope_all = request.args.get('scope') == 'all' and user['role'] == 'admin'

    like = '%' + keyword + '%'
    suffix = '' if scope_all else ' AND j.user_id = ?'
    extra = () if scope_all else (user['id'],)

    job_rows = db.query(
        'SELECT j.*, u.username, u.display_name AS user_display_name '
        'FROM jobs j LEFT JOIN users u ON u.id = j.user_id '
        'WHERE j.title LIKE ?' + suffix + ' ORDER BY j.created_at DESC LIMIT ?',
        (like,) + extra + (limit,))

    item_rows = db.query(
        'SELECT ' + _ITEM_FIELDS + ', j.title AS job_title, u.username '
        'FROM job_items i JOIN jobs j ON j.id = i.job_id '
        'LEFT JOIN users u ON u.id = j.user_id '
        'WHERE (i.original_name LIKE ? OR i.preview LIKE ?)' + suffix +
        ' ORDER BY i.finished_at DESC, i.seq LIMIT ?', (like, like) + extra + (limit,))

    is_admin = user['role'] == 'admin'
    items = []
    for row in item_rows:
        view = item_view(row)
        view['job_title'] = row['job_title']
        view['snippet'] = _snippet(row['preview'], keyword)
        if is_admin:
            view['username'] = row['username']
            view['user_id'] = row['user_id']
        items.append(view)

    return ok({
        'keyword': keyword,
        'jobs': [job_view(row, with_client=is_admin) for row in job_rows],
        'items': items,
        'note': '任务按标题匹配；文件按名称与识别文本开头（前 %d 字）匹配' % PREVIEW_CHARS,
    })