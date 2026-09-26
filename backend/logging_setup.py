# -*- coding: utf-8 -*-
"""日志配置：按天滚动写入 data/logs，同时输出到控制台。"""

import logging
import logging.handlers
import sys
from pathlib import Path

_FORMAT = '%(asctime)s %(levelname)-7s [%(name)s] %(message)s'
_DATEFMT = '%Y-%m-%d %H:%M:%S'


def _ensure_utf8_console():
    """输出被重定向到文件时改用 UTF-8，避免中文日志乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None and not stream.isatty():
                stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError, OSError):
            pass


def setup_logging(log_dir, level='INFO', name='app'):
    """配置根日志器，返回根日志器。可重复调用（会先清空已有 handler）。"""
    _ensure_utf8_console()
    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    formatter = logging.Formatter(_FORMAT, _DATEFMT)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        str(directory / ('%s.log' % name)),
        when='midnight', backupCount=30, encoding='utf-8', delay=True)
    file_handler.suffix = '%Y-%m-%d'
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    logging.getLogger('cheroot').setLevel(logging.WARNING)
    return root