# -*- coding: utf-8 -*-
"""任务文件目录的清理，供删除任务与保留策略共用。"""

import logging
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

JOB_SUBDIRS = ('uploads', 'results', 'exports')


def remove_job_files(data_dir, job_id):
    """删除某个任务占用的目录；失败只记日志，不中断调用方。"""
    removed = 0
    for name in JOB_SUBDIRS:
        target = Path(data_dir) / name / job_id
        if target.is_dir():
            try:
                shutil.rmtree(str(target))
                removed += 1
            except OSError as exc:
                log.warning('删除目录 %s 失败：%s', target, exc)
    return removed


def remove_orphan_dirs(data_dir, known_job_ids):
    """删除没有对应任务的残留目录，返回删除数量。"""
    removed = 0
    for name in JOB_SUBDIRS:
        root = Path(data_dir) / name
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if not child.is_dir() or child.name in known_job_ids:
                continue
            try:
                shutil.rmtree(str(child))
                removed += 1
                log.info('清理孤立目录 %s', child)
            except OSError as exc:
                log.warning('清理孤立目录 %s 失败：%s', child, exc)
    return removed