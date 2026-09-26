# -*- coding: utf-8 -*-
"""运行时设置接口（仅管理员）。"""

import logging

from flask import Blueprint, current_app, request

from ..repositories import audit
from ..repositories import settings as settings_repo
from ..security import admin_required, current_user
from ..services import runtime_settings
from .common import client_ip, context, fail, ok

log = logging.getLogger(__name__)

RUNTIME_PREFIX = 'runtime.'

bp = Blueprint('settings', __name__)


@bp.get('/api/settings')
@admin_required
def get_settings():
    ctx = context()
    config = ctx['config']
    stored = settings_repo.get_all(ctx['db'])
    values = dict((key, config[key]) for key in runtime_settings.RUNTIME_KEYS)
    overridden = dict((key, (RUNTIME_PREFIX + key) in stored)
                      for key in runtime_settings.RUNTIME_KEYS)
    return ok({
        'values': values,
        'overridden': overridden,
        'limits': dict((key, list(bounds)) for key, bounds in runtime_settings.INT_KEYS.items()),
        'log_levels': list(runtime_settings.LOG_LEVELS),
        'config_file': str(config.base_dir / 'config.json'),
    })



@bp.put('/api/settings')
@admin_required
def update_settings():
    ctx = context()
    payload = request.get_json(silent=True) or {}
    values = payload.get('values') if isinstance(payload.get('values'), dict) else payload

    clean, errors = runtime_settings.validate(values)
    if errors:
        return fail('invalid_request', '；'.join(errors), 400)
    if not clean:
        return fail('invalid_request', '没有需要修改的设置', 400)

    runtime_settings.save(ctx['db'], clean)
    runtime_settings.apply(current_app, ctx, clean)
    audit.write(ctx['db'], 'settings_updated', user_id=current_user()['id'],
                detail=clean, ip=client_ip())
    return get_settings()