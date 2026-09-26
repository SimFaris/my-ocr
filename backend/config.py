# -*- coding: utf-8 -*-
"""配置加载：环境变量 > config.json > 内置默认值。"""

import json
import os
from pathlib import Path

DEFAULTS = {
    'host': '0.0.0.0',
    'http_port': 8080,
    'https_port': 8443,
    'enable_https': True,
    'cert_san': '',
    'data_dir': 'data',
    'umi_exe_path': 'vendor/umi-ocr/Umi-OCR.exe',
    'umi_host': '127.0.0.1',
    'umi_port': 1224,
    'umi_autostart': True,
    'umi_request_timeout': 300,
    'umi_retries': 3,
    'ocr_workers': 1,
    'web_threads': 8,
    'upload_max_mb': 200,
    'retention_days': 90,
    'disk_min_free_gb': 5,
    'log_level': 'INFO',
    'session_secret_file': '',
}

ENV_MAP = {
    'host': 'OCR_HOST',
    'http_port': 'OCR_HTTP_PORT',
    'https_port': 'OCR_HTTPS_PORT',
    'enable_https': 'OCR_ENABLE_HTTPS',
    'cert_san': 'OCR_CERT_SAN',
    'data_dir': 'OCR_DATA_DIR',
    'umi_exe_path': 'OCR_UMI_EXE',
    'umi_host': 'OCR_UMI_HOST',
    'umi_port': 'OCR_UMI_PORT',
    'umi_autostart': 'OCR_UMI_AUTOSTART',
    'ocr_workers': 'OCR_WORKERS',
    'web_threads': 'OCR_WEB_THREADS',
    'upload_max_mb': 'OCR_UPLOAD_MAX_MB',
    'retention_days': 'OCR_RETENTION_DAYS',
    'disk_min_free_gb': 'OCR_DISK_MIN_FREE_GB',
    'log_level': 'OCR_LOG_LEVEL',
}

_TRUTHY = ('1', 'true', 'yes', 'on', 'y')


def _coerce(key, raw, default):
    """按默认值的类型转换配置值。"""
    text = str(raw).strip()
    if isinstance(default, bool):
        return text.lower() in _TRUTHY
    if isinstance(default, int):
        try:
            return int(text)
        except ValueError:
            raise ValueError('配置项 %s 需要整数，收到 %r' % (key, raw))
    return text


def _resolve(base, raw):
    path = Path(raw)
    if not path.is_absolute():
        path = base / path
    return str(path.resolve())


class Config(object):
    """配置对象；路径类配置已解析为绝对路径。"""

    def __init__(self, values, base_dir):
        self._values = dict(values)
        self.base_dir = Path(base_dir).resolve()

    def get(self, key, default=None):
        return self._values.get(key, default)

    def __getitem__(self, key):
        return self._values[key]

    def __contains__(self, key):
        return key in self._values

    def as_dict(self):
        return dict(self._values)

    @property
    def data_dir(self):
        return Path(self._values['data_dir'])

    @property
    def umi_exe(self):
        return Path(self._values['umi_exe_path'])

    @property
    def session_secret_file(self):
        return Path(self._values['session_secret_file'])

    @property
    def db_path(self):
        return self.data_dir / 'ocr.db'

    @property
    def cert_dir(self):
        return self.data_dir / 'certs'

    @property
    def log_dir(self):
        return self.data_dir / 'logs'

    @property
    def upload_max_bytes(self):
        return int(self._values['upload_max_mb']) * 1024 * 1024

    def cert_path(self, name='server.crt'):
        return self.cert_dir / name

    def ensure_dirs(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for name in ('uploads', 'results', 'exports', 'certs', 'logs', 'tmp'):
            (self.data_dir / name).mkdir(parents=True, exist_ok=True)
        return self.data_dir


def load_config(base_dir=None, config_path=None, env=None, overrides=None):
    """读取配置（默认值 < config.json < 环境变量 < overrides），解析路径并确保数据目录存在。"""
    base = Path(base_dir) if base_dir else Path(__file__).resolve().parent.parent
    base = base.resolve()
    environ = os.environ if env is None else env

    values = dict(DEFAULTS)
    path = Path(config_path) if config_path else (base / 'config.json')
    if path.is_file():
        with open(str(path), 'r', encoding='utf-8') as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            raise ValueError('config.json 顶层必须是 JSON 对象')
        for key, value in loaded.items():
            if key not in DEFAULTS:
                raise ValueError('config.json 中出现未知配置项：%s' % key)
            default = DEFAULTS[key]
            if isinstance(default, (bool, int)) and not isinstance(value, (bool, int)):
                values[key] = _coerce(key, value, default)
            else:
                values[key] = value

    for key, env_name in ENV_MAP.items():
        raw = environ.get(env_name)
        if raw is not None and str(raw) != '':
            values[key] = _coerce(key, raw, DEFAULTS[key])

    if overrides:
        for key, value in overrides.items():
            if key not in DEFAULTS:
                raise ValueError('未知配置项：%s' % key)
            if value is not None:
                values[key] = value
    values['data_dir'] = _resolve(base, values['data_dir'])
    values['umi_exe_path'] = _resolve(base, values['umi_exe_path'])
    if values['session_secret_file']:
        values['session_secret_file'] = _resolve(base, values['session_secret_file'])
    else:
        values['session_secret_file'] = str(Path(values['data_dir']) / 'session.key')

    config = Config(values, base)
    config.ensure_dirs()
    return config