# -*- coding: utf-8 -*-
"""系统状态、识别参数与根证书接口。"""

import logging
import threading
import time

from flask import Blueprint, send_file

from .. import __version__
from ..security import login_required
from ..umi import UmiError
from ..utils import disk_usage, now_iso
from ..repositories import jobs as jobs_repo
from .common import context, fail, ok

log = logging.getLogger(__name__)

bp = Blueprint('system', __name__, url_prefix='/api/system')

CACHE_SECONDS = 300
_options_cache = {}
_cache_lock = threading.Lock()


@bp.get('/status')
@login_required
def status():
    ctx = context()
    config = ctx['config']
    manager = ctx['umi']
    manager.probe()
    snapshot = manager.snapshot()
    queue_payload = jobs_repo.queue_summary(ctx['db'])
    runtime = ctx.get('queue')
    queue_payload['runtime'] = runtime.snapshot() if runtime is not None else None
    return ok({
        'app_version': __version__,
        'server_time': now_iso(),
        'umi': snapshot,
        'queue': queue_payload,
        'workers': config['ocr_workers'],
        'disk': disk_usage(config.data_dir),
        'data_dir': str(config.data_dir),
        'https': {
            'enabled': bool(config['enable_https']),
            'port': config['https_port'],
            'cert_exists': config.cert_path('server.crt').is_file(),
        },
    })


def _cached_options(kind):
    """代理 Umi-OCR 的参数定义并缓存 5 分钟；取不到时退回旧缓存。"""
    manager = context()['umi']
    now = time.time()
    with _cache_lock:
        entry = _options_cache.setdefault(kind, {'data': None, 'fetched_at': 0.0})
        cached = entry['data']
        fetched_at = entry['fetched_at']
    if cached is not None and (now - fetched_at) < CACHE_SECONDS:
        return ok(cached)

    try:
        if kind == 'doc':
            data = manager.client.get_doc_options()
        else:
            data = manager.client.get_ocr_options()
    except UmiError as exc:
        if cached is not None:
            log.warning('取识别参数失败，返回缓存：%s', exc)
            return ok(cached)
        return fail('umi_unavailable', '无法从 Umi-OCR 获取识别参数：%s' % exc, 503)

    with _cache_lock:
        _options_cache[kind] = {'data': data, 'fetched_at': now}
    return ok(data)


@bp.get('/ocr-options')
@login_required
def ocr_options():
    """图片识别参数定义（供前端生成设置界面）。"""
    return _cached_options('ocr')


@bp.get('/doc-options')
@login_required
def doc_options():
    """文档（PDF）识别参数定义。"""
    return _cached_options('doc')


@bp.get('/root-cert')
def root_cert():
    """下载自签根证书。这是唯一无需登录的接口，用于客户端导入信任。"""
    path = context()['config'].cert_path('ca.cer')
    if not path.is_file():
        return fail('not_found', '根证书尚未生成，请先执行 tools/gen_cert.ps1', 404)
    return send_file(str(path), as_attachment=True, download_name='my-ocr-root-ca.cer')