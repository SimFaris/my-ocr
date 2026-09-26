# -*- coding: utf-8 -*-
"""任务调度：在用户之间轮转，避免单个大任务独占工作线程。"""

import logging
import threading

from ..repositories import items as items_repo

log = logging.getLogger(__name__)


class Scheduler(object):
    """决定"下一个该做谁的任务"。

    纯 FIFO 会让一个用户提交的几百张图片把其他用户全部堵住，所以这里按用户
    轮转：每次取排在队首的用户之后的下一个用户的任务项。内存里的游标只是
    加速用的视图，真正的排队状态始终以数据库为准。
    """

    def __init__(self, db, poll_interval=1.0):
        self.db = db
        self.poll_interval = poll_interval
        self._cursor = None
        self._lock = threading.Lock()

    def next_item(self):
        with self._lock:
            users = [row['user_id'] for row in items_repo.queued_users(self.db)]
            if not users:
                self._cursor = None
                return None
            user_id = self._pick_user(users)
            item = items_repo.claim_oldest_for_user(self.db, user_id)
            if item is not None:
                self._cursor = user_id
            return item

    def _pick_user(self, users):
        if self._cursor is None or self._cursor not in users:
            return users[0]
        position = users.index(self._cursor)
        return users[(position + 1) % len(users)]