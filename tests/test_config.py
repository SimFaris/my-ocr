# -*- coding: utf-8 -*-
"""配置加载测试。"""

import os

import pytest

from backend.config import load_config


def test_defaults_create_data_dirs(tmp_path):
    config = load_config(base_dir=tmp_path, env={})
    assert config.data_dir == (tmp_path / 'data').resolve()
    assert config.db_path.parent == config.data_dir
    assert config.session_secret_file.parent == config.data_dir
    for name in ('uploads', 'results', 'exports', 'certs', 'logs', 'tmp'):
        assert (config.data_dir / name).is_dir()
    assert config['http_port'] == 8080
    assert config['enable_https'] is True
    assert config.upload_max_bytes == 200 * 1024 * 1024


def test_env_override_and_type_coercion(tmp_path):
    config = load_config(base_dir=tmp_path, env={
        'OCR_HTTP_PORT': '9000',
        'OCR_ENABLE_HTTPS': 'false',
        'OCR_DATA_DIR': str(tmp_path / 'custom'),
    })
    assert config['http_port'] == 9000
    assert config['enable_https'] is False
    assert config.data_dir == (tmp_path / 'custom').resolve()


def test_bad_env_type_raises(tmp_path):
    with pytest.raises(ValueError):
        load_config(base_dir=tmp_path, env={'OCR_HTTP_PORT': 'abc'})


def test_json_config_and_unknown_key(tmp_path):
    (tmp_path / 'config.json').write_text('{"http_port": "9100"}', encoding='utf-8')
    config = load_config(base_dir=tmp_path, env={})
    assert config['http_port'] == 9100

    (tmp_path / 'config.json').write_text('{"nope": 1}', encoding='utf-8')
    with pytest.raises(ValueError):
        load_config(base_dir=tmp_path, env={})


def test_overrides_have_highest_priority(tmp_path):
    (tmp_path / 'config.json').write_text('{"http_port": 9200}', encoding='utf-8')
    config = load_config(base_dir=tmp_path, env={'OCR_HTTP_PORT': '9300'},
                         overrides={'http_port': 1234})
    assert config['http_port'] == 1234


def test_session_key_derived_from_data_dir(tmp_path):
    config = load_config(base_dir=tmp_path, env={'OCR_DATA_DIR': str(tmp_path / 'd2')})
    assert os.path.dirname(str(config.session_secret_file)) == str(config.data_dir)