# -*- coding: utf-8 -*-
"""工作线程：领取任务项并执行，结果落库落文件。"""

import json
import logging
import threading
import time
from pathlib import Path

from ..repositories import items as items_repo
from ..repositories import jobs as jobs_repo
from ..umi import UmiError, flatten_data

log = logging.getLogger(__name__)

PREVIEW_CHARS = 200


def _elapsed_ms(started):
    return int((time.time() - started) * 1000)


def _write_text(config, item, text):
    """把识别文本写入 results/<job_id>/<item_id>.txt，返回相对路径。"""
    relpath = 'results/%s/%s.txt' % (item['job_id'], item['id'])
    target = Path(config.data_dir) / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding='utf-8')
    return relpath


def run_image_item(context, item):
    """识别单张图片：调用 Umi-OCR，文本落到结果目录。"""
    config = context['config']
    db = context['db']
    client = context['umi'].client

    job = jobs_repo.get(db, item['job_id'])
    options = dict(jobs_repo.get_options(job) if job else {})
    options.setdefault('data.format', 'text')

    started = time.time()
    source = Path(config.data_dir) / item['stored_relpath']
    if not source.is_file():
        items_repo.finish(db, item['id'], 'failed', error_code='file_missing',
                          error_message='原始文件不存在', duration_ms=_elapsed_ms(started))
        return

    try:
        result = client.ocr_image(str(source), options)
    except UmiError as exc:
        log.warning('任务项 %s 识别失败：%s', item['id'], exc.message)
        items_repo.finish(db, item['id'], 'failed', error_code=exc.code,
                          error_message=exc.message, duration_ms=_elapsed_ms(started))
        return
    except OSError as exc:
        items_repo.finish(db, item['id'], 'failed', error_code='file_read_failed',
                          error_message='读取原始文件失败：%s' % exc,
                          duration_ms=_elapsed_ms(started))
        return

    text = result.get('text') or ''
    if result.get('status') == 'empty' or not text.strip():
        items_repo.finish(db, item['id'], 'empty', char_count=0, preview='',
                          duration_ms=_elapsed_ms(started))
        return

    relpath = _write_text(config, item, text)
    items_repo.finish(db, item['id'], 'done', text_relpath=relpath, char_count=len(text),
                      preview=text[:PREVIEW_CHARS], duration_ms=_elapsed_ms(started))


def _document_timeout(config, page_total):
    """按页数估算文档识别超时时间（页数未知时按 0 页算基准值）。"""
    base = float(config['pdf_item_timeout_base'])
    per_page = float(config['pdf_item_timeout_per_page'])
    limit = float(config['pdf_item_timeout_max'])
    return min(limit, base + per_page * int(page_total or 0))


def _job_canceled(db, job_id):
    job = jobs_repo.get(db, job_id)
    return job is None or job['status'] == 'canceled'


def _poll_document(context, item, client, umi_task_id, started):
    """轮询文档任务并回写页级进度，返回结束原因。"""
    config = context['config']
    db = context['db']
    poll_interval = float(config['pdf_poll_interval'])
    stall_seconds = float(config['pdf_stall_seconds'])

    page_total = None
    last_done = -1
    last_progress_at = time.time()

    while True:
        if _job_canceled(db, item['job_id']):
            return {'state': 'canceled'}
        timeout = _document_timeout(config, page_total)
        if time.time() - started > timeout:
            return {'state': 'timeout', 'message': '文档识别超时（超过 %d 秒）' % timeout}
        if time.time() - last_progress_at > stall_seconds:
            return {'state': 'stalled', 'message': '文档识别长时间没有进展'}

        try:
            data = client.doc_result(umi_task_id, with_data=False)
        except UmiError as exc:
            return {'state': 'failure', 'code': exc.code, 'message': exc.message}

        page_total = data.get('pages_count') or page_total
        page_done = data.get('processed_count')
        items_repo.set_progress(db, item['id'], page_done=page_done, page_total=page_total)

        if page_done is not None and page_done != last_done:
            last_done = page_done
            last_progress_at = time.time()

        if data.get('is_done'):
            if data.get('state') == 'success':
                return {'state': 'success'}
            return {'state': 'failure', 'code': 'umi_doc_failed',
                    'message': data.get('message') or '文档识别失败'}
        time.sleep(poll_interval)


def run_pdf_item(context, item):
    """识别单个 PDF：上传 → 轮询页级进度 → 取文本 →（可选）产出双层 PDF → 清理。"""
    config = context['config']
    db = context['db']
    client = context['umi'].client

    job = jobs_repo.get(db, item['job_id'])
    options = dict(jobs_repo.get_options(job) if job else {})
    want_layered = bool(options.pop('laying_pdf', False))
    if not options.get('doc.extractionMode'):
        options['doc.extractionMode'] = 'mixed'

    started = time.time()
    source = Path(config.data_dir) / item['stored_relpath']
    if not source.is_file():
        items_repo.finish(db, item['id'], 'failed', error_code='file_missing',
                          error_message='原始文件不存在', duration_ms=_elapsed_ms(started))
        return

    try:
        umi_task_id = client.doc_upload(str(source), options)
    except UmiError as exc:
        log.warning('文档 %s 上传失败：%s', item['id'], exc.message)
        items_repo.finish(db, item['id'], 'failed', error_code=exc.code,
                          error_message=exc.message, duration_ms=_elapsed_ms(started))
        return
    except OSError as exc:
        items_repo.finish(db, item['id'], 'failed', error_code='file_read_failed',
                          error_message='读取原始文件失败：%s' % exc,
                          duration_ms=_elapsed_ms(started))
        return

    items_repo.set_umi_task(db, item['id'], umi_task_id)
    try:
        outcome = _poll_document(context, item, client, umi_task_id, started)
        state = outcome.get('state')

        if state == 'canceled':
            items_repo.finish(db, item['id'], 'skipped', duration_ms=_elapsed_ms(started))
            return
        if state in ('timeout', 'stalled'):
            items_repo.finish(db, item['id'], 'failed', error_code=state,
                              error_message=outcome.get('message'),
                              duration_ms=_elapsed_ms(started))
            return
        if state == 'failure':
            items_repo.finish(db, item['id'], 'failed',
                              error_code=outcome.get('code') or 'umi_doc_failed',
                              error_message=outcome.get('message') or '文档识别失败',
                              duration_ms=_elapsed_ms(started))
            return

        try:
            result = client.doc_result(umi_task_id, with_data=True, unread=False, fmt='text')
        except UmiError as exc:
            items_repo.finish(db, item['id'], 'failed', error_code=exc.code,
                              error_message='取回识别文本失败：%s' % exc.message,
                              duration_ms=_elapsed_ms(started))
            return

        text = flatten_data(result.get('data'))
        artifacts = {}
        if want_layered:
            try:
                artifact = client.doc_download(umi_task_id, file_types=['pdfLayered'])
                relpath = 'results/%s/%s.pdf' % (item['job_id'], item['id'])
                client.download(artifact['url'], Path(config.data_dir) / relpath)
                artifacts['pdfLayered'] = relpath
            except UmiError as exc:
                # 双层 PDF 生成失败不影响文本结果，但要留下原因
                log.warning('文档 %s 产出双层 PDF 失败：%s', item['id'], exc.message)
                artifacts['pdfLayeredError'] = exc.message

        if not text.strip():
            items_repo.finish(db, item['id'], 'empty', char_count=0, preview='',
                              duration_ms=_elapsed_ms(started), artifacts=artifacts or None)
            return

        relpath = _write_text(config, item, text)
        items_repo.finish(db, item['id'], 'done', text_relpath=relpath, char_count=len(text),
                          preview=text[:PREVIEW_CHARS], duration_ms=_elapsed_ms(started),
                          artifacts=artifacts or None)
    finally:
        # 无论成败都清理 Umi 侧任务，避免其临时文件堆积
        if umi_task_id:
            client.doc_clear(umi_task_id)


# 输入类型 -> 处理函数。摄像头拍摄的图片复用 image 处理。
HANDLERS = {'image': run_image_item, 'pdf': run_pdf_item}


class Worker(threading.Thread):
    """单个工作线程：不断领取任务项执行，直到收到停止信号。"""

    def __init__(self, index, context, scheduler, stop_event):
        threading.Thread.__init__(self, name='ocr-worker-%d' % (index + 1))
        self.daemon = True
        self.context = context
        self.db = context['db']
        self.scheduler = scheduler
        self.stop_event = stop_event

    def run(self):
        log.info('工作线程 %s 已启动', self.name)
        while not self.stop_event.is_set():
            item = self.scheduler.next_item()
            if item is None:
                self.stop_event.wait(self.scheduler.poll_interval)
                continue
            self.execute(item)
        log.info('工作线程 %s 已退出', self.name)

    def execute(self, item):
        """执行单个任务项；任何异常都只能影响这一项，不能中断整批任务。"""
        jobs_repo.mark_started(self.db, item['job_id'])
        handler = HANDLERS.get(item['kind'])
        try:
            if handler is None:
                items_repo.finish(self.db, item['id'], 'failed', error_code='unsupported_kind',
                                  error_message='暂不支持的输入类型：%s' % item['kind'])
            else:
                handler(self.context, item)
        except Exception as exc:                      # noqa: BLE001 - 兜底，避免线程退出
            log.exception('处理任务项 %s 时发生未预期异常', item['id'])
            items_repo.finish(self.db, item['id'], 'failed', error_code='internal',
                              error_message='处理异常：%s' % exc)
        finally:
            jobs_repo.refresh_counts(self.db, item['job_id'])