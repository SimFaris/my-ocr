# -*- coding: utf-8 -*-
"""工作线程：领取任务项并执行，结果落库落文件。"""

import json
import logging
import threading
import time
from pathlib import Path

from ..repositories import items as items_repo
from ..repositories import jobs as jobs_repo
from ..umi import UmiError

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


# 输入类型 -> 处理函数。PDF 在 M3 加入，摄像头拍摄的图片复用 image。
HANDLERS = {'image': run_image_item}


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