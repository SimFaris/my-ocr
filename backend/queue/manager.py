# -*- coding: utf-8 -*-
"""OCR 队列的生命周期管理：调度器 + 工作线程。"""

import logging
import threading

log = logging.getLogger(__name__)


class OcrQueue(object):
    """把调度器和 N 个工作线程打包成一个可启停的整体。

    应用装配时不启动，由启动入口在服务就绪后调用 start()，测试里也能独立控制。
    """

    def __init__(self, context):
        from .scheduler import Scheduler
        from .worker import Worker

        self._scheduler_class = Scheduler
        self._worker_class = Worker
        self.context = context
        self.db = context['db']
        self.worker_count = max(1, int(context['config']['ocr_workers']))
        self.scheduler = Scheduler(self.db)
        self.stop_event = threading.Event()
        self.workers = []

    def start(self):
        if any(worker.is_alive() for worker in self.workers):
            return False
        self.stop_event.clear()
        self.workers = []
        for index in range(self.worker_count):
            worker = self._worker_class(index, self.context, self.scheduler, self.stop_event)
            worker.start()
            self.workers.append(worker)
        log.info('OCR 队列已启动：工作线程 %d 个', self.worker_count)
        return True

    def stop(self, timeout=5):
        """停止所有工作线程；正在执行的任务项会在下次启动时被自动回队。"""
        if not self.workers:
            return False
        self.stop_event.set()
        for worker in self.workers:
            worker.join(timeout=timeout)
        self.workers = []
        log.info('OCR 队列已停止')
        return True

    def snapshot(self):
        alive = len([worker for worker in self.workers if worker.is_alive()])
        return {'workers': self.worker_count, 'alive': alive, 'running': bool(alive)}