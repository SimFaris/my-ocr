# -*- coding: utf-8 -*-
"""运行时设置：管理员在界面上可改、改完立即生效、并持久化到数据库。

与 config.json 的分工：config.json 是部署配置（改完要重启），这里是不需要重启的
那几个参数。优先级上运行时设置高于 config.json，因为它是管理员刚刚显式改的。
"""

import logging

from ..repositories import settings as settings_repo

log = logging.getLogger(__name__)

INT_KEYS = {
    'retention_days': (0, 3650),
    'disk_min_free_gb': (0, 100000),
    'upload_max_mb': (1, 20480),
    'ocr_workers': (1, 8),
}
LOG_LEVELS = ('DEBUG', 'INFO', 'WARNING', 'ERROR')
RUNTIME_KEYS = tuple(sorted(list(INT_KEYS) + ['log_level']))

_PREFIX = 'runtime.'


def _coerce(key, raw):
    if key in INT_KEYS:
        value = int(str(raw).strip())
        low, high = INT_KEYS[key]
        if value < low or value > high:
            raise ValueError('%s 需在 %d 到 %d 之间' % (key, low, high))
        return value
    text = str(raw).strip().upper()
    if text not in LOG_LEVELS:
        raise ValueError('log_level 只能是 %s' % '/'.join(LOG_LEVELS))
    return text


def validate(values):
    """校验并整理提交上来的设置，返回 (可用值, 错误列表)。"""
    clean = {}
    errors = []
    for key, raw in (values or {}).items():
        if key not in RUNTIME_KEYS:
            errors.append('不支持修改 %s' % key)
            continue
        try:
            clean[key] = _coerce(key, raw)
        except (ValueError, TypeError) as exc:
            errors.append(str(exc))
    return clean, errors


def load_runtime(db, config):
    """启动时把库里保存的运行时设置叠加到配置上。"""
    stored = settings_repo.get_all(db)
    applied = {}
    for key in RUNTIME_KEYS:
        raw = stored.get(_PREFIX + key)
        if raw is None:
            continue
        try:
            value = _coerce(key, raw)
        except (ValueError, TypeError):
            log.warning('忽略数据库里非法的运行时设置 %s=%r', key, raw)
            continue
        config.set_runtime(key, value)
        applied[key] = value
    if applied:
        log.info('已应用运行时设置：%s', applied)
    return applied


def save(db, values):
    """持久化运行时设置。"""
    settings_repo.set_many(db, dict((_PREFIX + key, value) for key, value in values.items()))


def apply(app, context, values):
    """让设置立即生效（日志级别、上传上限、识别线程数）。"""
    config = context['config']
    for key, value in values.items():
        config.set_runtime(key, value)
        if key == 'log_level':
            logging.getLogger().setLevel(getattr(logging, value, logging.INFO))

    if 'upload_max_mb' in values:
        app.config['MAX_CONTENT_LENGTH'] = int(values['upload_max_mb']) * 1024 * 1024

    if 'ocr_workers' in values:
        queue = context.get('queue')
        if queue is not None and queue.snapshot().get('running'):
            queue.stop()
            queue.start()
            log.info('识别工作线程数已调整为 %s', values['ocr_workers'])