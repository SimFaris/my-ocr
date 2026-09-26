# -*- coding: utf-8 -*-
"""保留策略：定期清理超过保留期的任务及其文件。"""

import datetime
import logging
import threading
import time

from ..repositories import jobs as jobs_repo
from ..services import storage
from ..utils import parse_iso

log = logging.getLogger(__name__)

# 这些状态的任务还在进行中，无论多旧都不能删
ACTIVE_STATUSES = ('queued', 'running')
DEFAULT_INTERVAL_SECONDS = 6 * 3600


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)


def cleanup(db, config, now=None):
    """按保留天数清理过期任务，返回统计信息。

    retention_days 为 0 表示不自动清理（只做孤立目录清理）。
    """
    days = int(config['retention_days'])
    moment = now or _now()
    result = {'enabled': days > 0, 'days': days, 'deleted_jobs': 0,
              'removed_dirs': 0, 'deleted_items': 0, 'orphan_dirs': 0}

    known_ids = set()
    for row in db.query('SELECT id, status, created_at, finished_at FROM jobs'):
        job_id = row['id']
        known_ids.add(job_id)
        if days <= 0 or row['status'] in ACTIVE_STATUSES:
            continue
        stamp = parse_iso(row['finished_at'] or row['created_at'])
        if stamp is None:
            continue
        if stamp > moment - datetime.timedelta(days=days):
            continue

        counts = db.query_one('SELECT COUNT(*) AS n FROM job_items WHERE job_id = ?', (job_id,))
        result['deleted_items'] += int(counts['n']) if counts else 0
        result['removed_dirs'] += storage.remove_job_files(config.data_dir, job_id)
        jobs_repo.delete(db, job_id)
        result['deleted_jobs'] += 1
        log.info('已清理过期任务 %s（创建于 %s）', job_id, row['created_at'])

    result['orphan_dirs'] = storage.remove_orphan_dirs(config.data_dir, known_ids)
    if result['deleted_jobs'] or result['orphan_dirs']:
        log.info('保留策略执行完成：%s', result)
    return result


class RetentionRunner(object):
    """后台定时清理线程；也可手动触发一次。"""

    def __init__(self, context, interval_seconds=DEFAULT_INTERVAL_SECONDS):
        self.context = context
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread = None

    def run_once(self):
        try:
            return cleanup(self.context['db'], self.context['config'])
        except Exception:
            log.exception('保留策略执行失败')
            return None

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return False
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name='retention')
        self._thread.daemon = True
        self._thread.start()
        log.info('保留策略已启动：每 %d 小时清理一次', self.interval_seconds // 3600)
        return True

    def _loop(self):
        while not self._stop_event.is_set():
            self.run_once()
            self._stop_event.wait(self.interval_seconds)

    def stop(self, timeout=5):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        return True

    def snapshot(self):
        return {
            'running': bool(self._thread is not None and self._thread.is_alive()),
            'interval_hours': self.interval_seconds // 3600,
        }