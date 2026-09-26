# -*- coding: utf-8 -*-
"""通用工具：时间、磁盘、字节格式化。"""

import datetime
import shutil


def now_iso():
    """当前 UTC 时间，秒级精度，带 Z 后缀。

    使用 timezone.utc 而非已弃用的 utcnow()，同时保持 Python 3.8 兼容
    （datetime.UTC 常量要 3.11 才有，这里不用）。
    """
    stamp = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)
    return stamp.isoformat() + 'Z'


def parse_iso(text):
    """解析 now_iso() 产生的字符串，失败返回 None。"""
    if not text:
        return None
    raw = str(text).rstrip('Z')
    try:
        return datetime.datetime.strptime(raw, '%Y-%m-%dT%H:%M:%S')
    except ValueError:
        return None


def disk_usage(path):
    """返回 {'total','used','free','free_gb'}，单位字节。"""
    usage = shutil.disk_usage(str(path))
    return {
        'total': usage.total,
        'used': usage.used,
        'free': usage.free,
        'free_gb': round(usage.free / (1024.0 ** 3), 2),
    }


def human_bytes(size):
    """把字节数格式化为易读字符串。"""
    value = float(size)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if value < 1024.0:
            return '%.1f %s' % (value, unit)
        value /= 1024.0
    return '%.1f TB' % value