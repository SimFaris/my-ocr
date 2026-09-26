# -*- coding: utf-8 -*-
"""任务接口：创建、上传、提交、查询、取消、重试、删除与导出。"""

import logging
import shutil
import zipfile
from pathlib import Path

from flask import Blueprint, request, send_file

from ..repositories import audit
from ..repositories import items as items_repo
from ..repositories import jobs as jobs_repo
from ..security import current_user, login_required
from ..services.export import export_csv, export_txt
from ..services.ingest import (IMAGE_EXTENSIONS, PDF_EXTENSIONS, IngestError,
                               accept_upload)
from ..utils import disk_usage
from .common import (client_ip, context, fail, item_view, job_view,
                     load_job_or_error, ok)

log = logging.getLogger(__name__)

bp = Blueprint('jobs', __name__, url_prefix='/api')

SOURCE_TYPES = ('image', 'pdf', 'camera', 'mixed')
# 摄像头拍摄在 M4 接入；mixed 暂不开放
ENABLED_SOURCE_TYPES = ('image', 'pdf', 'camera')
# 每种来源允许的文件类型（以文件头判定为准）
SOURCE_KINDS = {'image': ('image',), 'camera': ('image',), 'pdf': ('pdf',)}
EXPORT_FORMATS = ('txt', 'csv', 'pdflayered')   # 与入参统一为小写，接口仍接受 pdfLayered
_ILLEGAL_FILENAME_CHARS = set('\\/:*?"<>|')


def _disk_blocked(ctx):
    """磁盘空间不足时返回原因，否则返回 None。"""
    usage = disk_usage(ctx['config'].data_dir)
    limit = float(ctx['config']['disk_min_free_gb'])
    if usage['free_gb'] < limit:
        return '磁盘可用空间不足（剩余 %.1f GB，阈值 %.1f GB）' % (usage['free_gb'], limit)
    return None


def _safe_stem(text, fallback='export'):
    """把任务标题清洗成可用的文件名主干。"""
    cleaned = ''.join(ch for ch in str(text or '') if ch not in _ILLEGAL_FILENAME_CHARS and ord(ch) >= 32)
    cleaned = cleaned.strip().strip('.')
    return cleaned[:60] or fallback


def _remove_job_files(config, job_id):
    """删除任务占用的目录；失败只记日志。"""
    for name in ('uploads', 'results', 'exports'):
        target = Path(config.data_dir) / name / job_id
        if target.is_dir():
            try:
                shutil.rmtree(str(target))
            except OSError as exc:
                log.warning('删除目录 %s 失败：%s', target, exc)


@bp.post('/jobs')
@login_required
def create_job():
    ctx = context()
    payload = request.get_json(silent=True) or {}

    source_type = str(payload.get('source_type') or 'image')
    if source_type not in SOURCE_TYPES:
        return fail('invalid_request', 'source_type 取值无效', 400)
    if source_type not in ENABLED_SOURCE_TYPES:
        return fail('invalid_request', '该来源类型尚未开放（摄像头见 M4）', 400)

    options = payload.get('ocr_options') or {}
    if not isinstance(options, dict):
        return fail('invalid_request', 'ocr_options 必须是对象', 400)

    blocked = _disk_blocked(ctx)
    if blocked:
        return fail('disk_low', blocked, 507)

    title = str(payload.get('title') or '').strip() or '未命名任务'
    user = current_user()
    job_id = jobs_repo.create(ctx['db'], user['id'], title, source_type, options)
    audit.write(ctx['db'], 'job_created', user_id=user['id'], target=job_id,
                detail={'title': title, 'source_type': source_type}, ip=client_ip())
    job = jobs_repo.get(ctx['db'], job_id)
    return ok({'job': job_view(job),
               'image_extensions': list(IMAGE_EXTENSIONS),
               'pdf_extensions': list(PDF_EXTENSIONS),
               'accepts': list(SOURCE_KINDS[source_type])}, 201)


@bp.post('/jobs/<job_id>/items')
@login_required
def upload_item(job_id):
    ctx = context()
    job, error = load_job_or_error(job_id)
    if error:
        return error
    if job['status'] != 'draft':
        return fail('conflict', '任务已提交，不能再添加文件', 409)

    storage = request.files.get('file')
    if storage is None or not storage.filename:
        return fail('invalid_request', '缺少上传文件（表单字段名应为 file）', 400)

    item_id = items_repo.new_id()
    try:
        relpath, size, kind, _extension = accept_upload(
            storage, ctx['config'].data_dir, job_id, item_id,
            allowed_kinds=SOURCE_KINDS[job['source_type']])
    except IngestError as exc:
        return fail(exc.code, exc.message, 400)

    item = items_repo.add(ctx['db'], job_id, kind,
                          'camera' if job['source_type'] == 'camera' else 'upload',
                          storage.filename, relpath, size, item_id=item_id)
    jobs_repo.refresh_counts(ctx['db'], job_id)
    return ok({'item': item_view(item)}, 201)


@bp.post('/jobs/<job_id>/start')
@login_required
def start_job(job_id):
    ctx = context()
    job, error = load_job_or_error(job_id)
    if error:
        return error
    if job['status'] != 'draft':
        return fail('conflict', '任务已提交过，不能重复提交', 409)

    blocked = _disk_blocked(ctx)
    if blocked:
        return fail('disk_low', blocked, 507)

    queued = items_repo.mark_queued(ctx['db'], job_id)
    if queued == 0:
        return fail('invalid_request', '任务里还没有文件', 400)
    jobs_repo.mark_submitted(ctx['db'], job_id)
    jobs_repo.refresh_counts(ctx['db'], job_id)
    job = jobs_repo.get(ctx['db'], job_id)
    audit.write(ctx['db'], 'job_started', user_id=current_user()['id'], target=job_id,
                detail={'items': queued}, ip=client_ip())
    return ok({'job': job_view(job), 'queued': queued})


@bp.get('/jobs')
@login_required
def list_jobs():
    ctx = context()
    user = current_user()
    scope = request.args.get('scope') or 'mine'
    status = request.args.get('status') or None
    keyword = (request.args.get('q') or '').strip() or None
    page = max(1, int(request.args.get('page') or 1))
    page_size = min(200, max(1, int(request.args.get('page_size') or 20)))
    user_id = None if (scope == 'all' and user['role'] == 'admin') else user['id']

    rows, total = jobs_repo.list_jobs(ctx['db'], user_id=user_id, status=status,
                                      page=page, page_size=page_size, keyword=keyword)
    return ok({'items': [job_view(row) for row in rows], 'total': total,
               'page': page, 'page_size': page_size})


@bp.get('/jobs/summary')
@login_required
def jobs_summary():
    """当前用户各状态任务数，供顶部徽标使用。"""
    ctx = context()
    user = current_user()
    if user['role'] == 'admin':
        counts = jobs_repo.job_summary(ctx['db'])
    else:
        rows = ctx['db'].query(
            'SELECT status, COUNT(*) AS n FROM jobs WHERE user_id = ? GROUP BY status', (user['id'],))
        counts = dict((row['status'], int(row['n'])) for row in rows)
    return ok({'counts': counts, 'queue': jobs_repo.queue_summary(ctx['db'])})


@bp.get('/jobs/<job_id>')
@login_required
def job_detail(job_id):
    job, error = load_job_or_error(job_id)
    if error:
        return error
    return ok({'job': job_view(job)})


@bp.get('/jobs/<job_id>/items')
@login_required
def job_items(job_id):
    job, error = load_job_or_error(job_id)
    if error:
        return error
    page = max(1, int(request.args.get('page') or 1))
    page_size = min(500, max(1, int(request.args.get('page_size') or 100)))
    status = request.args.get('status') or None
    rows, total = items_repo.list_items(context()['db'], job_id,
                                        page=page, page_size=page_size, status=status)
    return ok({'items': [item_view(row) for row in rows], 'total': total,
               'page': page, 'page_size': page_size})


@bp.get('/jobs/<job_id>/events')
@login_required
def job_events(job_id):
    """轻量轮询接口：任务状态 + 全部任务项的状态字段（不含文本正文）。"""
    job, error = load_job_or_error(job_id)
    if error:
        return error
    ctx = context()
    rows = items_repo.list_all(ctx['db'], job_id)
    queue = ctx.get('queue')
    return ok({
        'job': job_view(job),
        'items': [item_view(row) for row in rows],
        'runtime': queue.snapshot() if queue is not None else None,
    })


@bp.post('/jobs/<job_id>/cancel')
@login_required
def cancel_job(job_id):
    ctx = context()
    job, error = load_job_or_error(job_id)
    if error:
        return error
    if job['status'] not in ('draft', 'queued', 'running'):
        return fail('conflict', '任务已结束，无需取消', 409)

    skipped = items_repo.skip_unfinished(ctx['db'], job_id)
    jobs_repo.set_status(ctx['db'], job_id, 'canceled')
    jobs_repo.refresh_counts(ctx['db'], job_id)
    job = jobs_repo.get(ctx['db'], job_id)
    audit.write(ctx['db'], 'job_canceled', user_id=current_user()['id'], target=job_id,
                detail={'skipped': skipped}, ip=client_ip())
    return ok({'job': job_view(job), 'skipped': skipped})


@bp.post('/jobs/<job_id>/retry')
@login_required
def retry_job(job_id):
    ctx = context()
    job, error = load_job_or_error(job_id)
    if error:
        return error

    payload = request.get_json(silent=True) or {}
    item_ids = payload.get('item_ids') or None
    if item_ids is not None and not isinstance(item_ids, list):
        return fail('invalid_request', 'item_ids 必须是数组', 400)

    count = items_repo.requeue_failed(ctx['db'], job_id, item_ids)
    if count == 0:
        return fail('invalid_request', '没有需要重试的任务项', 400)
    jobs_repo.mark_submitted(ctx['db'], job_id)
    jobs_repo.refresh_counts(ctx['db'], job_id)
    job = jobs_repo.get(ctx['db'], job_id)
    return ok({'job': job_view(job), 'requeued': count})


@bp.delete('/jobs/<job_id>')
@login_required
def delete_job(job_id):
    ctx = context()
    job, error = load_job_or_error(job_id)
    if error:
        return error

    if job['status'] in ('queued', 'running'):
        items_repo.skip_unfinished(ctx['db'], job_id)
        jobs_repo.set_status(ctx['db'], job_id, 'canceled')
    _remove_job_files(ctx['config'], job_id)
    jobs_repo.delete(ctx['db'], job_id)
    audit.write(ctx['db'], 'job_deleted', user_id=current_user()['id'], target=job_id,
                detail={'title': job['title']}, ip=client_ip())
    return ok({'deleted': job_id})


def _export_layered(ctx, job, job_id):
    """下载 PDF 任务产出的双层可搜索 PDF；多个时打包成 zip。"""
    rows = items_repo.list_all(ctx['db'], job_id)
    found = []
    for item in rows:
        relpath = items_repo.artifacts(item).get('pdfLayered')
        if not relpath:
            continue
        path = Path(ctx['config'].data_dir) / relpath
        if path.is_file():
            found.append((item, path))
    if not found:
        return fail('invalid_request',
                    '还没有可下载的双层 PDF，请在导入 PDF 时勾选“生成双层可搜索 PDF”', 400)

    stem = _safe_stem(job['title'])
    if len(found) == 1:
        item, path = found[0]
        name = Path(item['original_name']).stem or stem
        return send_file(str(path), as_attachment=True,
                         download_name=name + '.pdf', mimetype='application/pdf')

    target = Path(ctx['config'].data_dir) / 'exports' / job_id / (stem + '-双层PDF.zip')
    target.parent.mkdir(parents=True, exist_ok=True)
    used = set()
    with zipfile.ZipFile(str(target), 'w', zipfile.ZIP_DEFLATED) as archive:
        for item, path in found:
            base = Path(item['original_name']).stem or item['id']
            candidate = base + '.pdf'
            index = 2
            while candidate in used:
                candidate = '%s-%d.pdf' % (base, index)
                index += 1
            used.add(candidate)
            archive.write(str(path), candidate)
    return send_file(str(target), as_attachment=True,
                     download_name=stem + '-双层PDF.zip', mimetype='application/zip')


@bp.get('/jobs/<job_id>/export')
@login_required
def export_job(job_id):
    ctx = context()
    job, error = load_job_or_error(job_id)
    if error:
        return error

    fmt = (request.args.get('format') or 'txt').lower()
    if fmt not in EXPORT_FORMATS:
        return fail('invalid_request', 'format 只支持 txt、csv 或 pdfLayered', 400)
    if fmt == 'pdflayered':
        return _export_layered(ctx, job, job_id)
    scope = request.args.get('scope') or 'all'
    if scope not in ('all', 'success'):
        return fail('invalid_request', 'scope 只支持 all 或 success', 400)

    rows = items_repo.list_all(ctx['db'], job_id)
    if scope == 'success':
        rows = [row for row in rows if row['status'] in ('done', 'empty')]
    if not rows:
        return fail('invalid_request', '没有可导出的内容', 400)

    stem = _safe_stem(job['title'])
    target = Path(ctx['config'].data_dir) / 'exports' / job_id / ('%s-%s.%s' % (stem, scope, fmt))
    if fmt == 'txt':
        path = export_txt(ctx['config'].data_dir, job, rows, target)
        mimetype = 'text/plain; charset=utf-8'
    else:
        path = export_csv(ctx['config'].data_dir, rows, target)
        mimetype = 'text/csv; charset=utf-8'

    audit.write(ctx['db'], 'job_exported', user_id=current_user()['id'], target=job_id,
                detail={'format': fmt, 'scope': scope, 'items': len(rows)}, ip=client_ip())
    return send_file(str(path), as_attachment=True,
                     download_name='%s-%s.%s' % (stem, scope, fmt), mimetype=mimetype)