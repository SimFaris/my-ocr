# -*- coding: utf-8 -*-
"""接口层公共辅助：统一响应、序列化、权限校验。"""

from flask import current_app, jsonify, request

from ..repositories import items as items_repo
from ..repositories import jobs as jobs_repo
from ..security import current_user


def ok(data=None, status=200):
    return jsonify({'ok': True, 'data': data}), status


def fail(code, message, status=400):
    return jsonify({'ok': False, 'error': {'code': code, 'message': message}}), status


def context():
    """当前应用的上下文对象：配置、数据库、Umi 管理器、队列、限速器。"""
    return current_app.extensions['ocr']


def client_ip():
    """客户端 IP：优先取代理头，否则用直连地址。"""
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or '-'


def job_view(job, items=None):
    """任务的可返回视图。"""
    if job is None:
        return None
    total = int(job['item_total'] or 0)
    done = int(job['item_done'] or 0)
    view = {
        'id': job['id'],
        'user_id': job['user_id'],
        'title': job['title'],
        'source_type': job['source_type'],
        'status': job['status'],
        'item_total': total,
        'item_done': done,
        'item_failed': int(job['item_failed'] or 0),
        'created_at': job['created_at'],
        'started_at': job['started_at'],
        'finished_at': job['finished_at'],
        'progress': 0.0 if total == 0 else round(done * 100.0 / total, 1),
        'ocr_options': jobs_repo.get_options(job),
    }
    if items is not None:
        view['items'] = [item_view(item) for item in items]
    return view


def item_view(item):
    """任务项的可返回视图（不含识别文本正文）。"""
    if item is None:
        return None
    artifacts = items_repo.artifacts(item)
    return {
        'artifacts': artifacts,
        'has_layered_pdf': bool(artifacts.get('pdfLayered')),
        'id': item['id'],
        'job_id': item['job_id'],
        'seq': item['seq'],
        'kind': item['kind'],
        'source': item['source'],
        'original_name': item['original_name'],
        'byte_size': item['byte_size'],
        'status': item['status'],
        'char_count': item['char_count'],
        'preview': item['preview'],
        'error_code': item['error_code'],
        'error_message': item['error_message'],
        'duration_ms': item['duration_ms'],
        'page_done': item['page_done'],
        'page_total': item['page_total'],
        'attempts': item['attempts'],
        'has_text': bool(item['text_relpath']),
        'queued_at': item['queued_at'],
        'started_at': item['started_at'],
        'finished_at': item['finished_at'],
    }


def _owned_by_current_user(owner_id):
    user = current_user()
    if user is None:
        return False
    return owner_id == user['id'] or user['role'] == 'admin'


def load_job_or_error(job_id):
    """取任务并做权限校验，返回 (job, error_response)。"""
    job = jobs_repo.get(context()['db'], job_id)
    if job is None:
        return None, fail('not_found', '任务不存在', 404)
    if not _owned_by_current_user(job['user_id']):
        return None, fail('forbidden', '无权访问该任务', 403)
    return job, None


def load_item_or_error(item_id):
    """取任务项并按所属任务做权限校验，返回 (item, error_response)。"""
    db = context()['db']
    item = items_repo.get(db, item_id)
    if item is None:
        return None, fail('not_found', '任务项不存在', 404)
    job = jobs_repo.get(db, item['job_id'])
    if job is None:
        return None, fail('not_found', '任务项不存在', 404)
    if not _owned_by_current_user(job['user_id']):
        return None, fail('forbidden', '无权访问该任务项', 403)
    return item, None