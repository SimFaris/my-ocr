# -*- coding: utf-8 -*-
"""任务项接口：识别文本读取与人工校对保存、原始文件预览。"""

import logging
from pathlib import Path

from flask import Blueprint, make_response, request, send_file

from ..repositories import audit
from ..repositories import items as items_repo
from ..security import current_user, login_required
from ..services.export import read_text
from .common import client_ip, context, fail, item_view, load_item_or_error, ok

log = logging.getLogger(__name__)

bp = Blueprint('items', __name__, url_prefix='/api/items')

PREVIEW_CHARS = 200


def _text_relpath(item):
    return 'results/%s/%s.txt' % (item['job_id'], item['id'])


@bp.get('/<item_id>/text')
@login_required
def get_text(item_id):
    item, error = load_item_or_error(item_id)
    if error:
        return error
    text = read_text(context()['config'].data_dir, item)
    response = make_response(text)
    response.headers['Content-Type'] = 'text/plain; charset=utf-8'
    return response


@bp.put('/<item_id>/text')
@login_required
def save_text(item_id):
    """保存人工校对后的文本。"""
    item, error = load_item_or_error(item_id)
    if error:
        return error

    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        text = payload.get('text')
    else:
        text = request.get_data(as_text=True)
    if text is None:
        return fail('invalid_request', '缺少文本内容', 400)
    text = str(text)

    ctx = context()
    relpath = _text_relpath(item)
    target = Path(ctx['config'].data_dir) / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding='utf-8')
    items_repo.save_text(ctx['db'], item['id'], relpath, len(text), text[:PREVIEW_CHARS])
    audit.write(ctx['db'], 'item_text_saved', user_id=current_user()['id'], target=item['id'],
                detail={'chars': len(text)}, ip=client_ip())
    return ok({'item': item_view(items_repo.get(ctx['db'], item['id']))})


@bp.get('/<item_id>/preview')
@login_required
def preview(item_id):
    """返回原始上传文件，供页面预览（图片直接内联显示）。"""
    item, error = load_item_or_error(item_id)
    if error:
        return error
    path = Path(context()['config'].data_dir) / item['stored_relpath']
    if not path.is_file():
        return fail('not_found', '原始文件不存在', 404)
    return send_file(str(path), as_attachment=False, download_name=item['original_name'])