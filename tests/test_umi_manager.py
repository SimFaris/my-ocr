# -*- coding: utf-8 -*-
"""Umi 进程托管测试。"""

from backend.config import load_config
from backend.umi.manager import UmiManager
from fake_umi import FakeUmi


def test_manager_reports_online_engine(tmp_path):
    server = FakeUmi().start()
    try:
        config = load_config(base_dir=tmp_path, env={
            'OCR_DATA_DIR': str(tmp_path / 'data'),
            'OCR_UMI_PORT': str(server.port),
            'OCR_UMI_AUTOSTART': 'false',
        })
        manager = UmiManager(config)
        online, options = manager.probe()
        assert online is True
        assert options

        snapshot = manager.snapshot()
        assert snapshot['online'] is True
        assert snapshot['process_running'] is False
        assert snapshot['last_error'] is None
        assert snapshot['last_check']
        assert snapshot['base_url'].endswith(':%d' % server.port)
    finally:
        server.stop()


def test_manager_without_autostart_stays_offline(tmp_path):
    config = load_config(base_dir=tmp_path, env={
        'OCR_DATA_DIR': str(tmp_path / 'data'),
        'OCR_UMI_PORT': '9',
        'OCR_UMI_AUTOSTART': 'false',
    })
    manager = UmiManager(config)
    online, options = manager.ensure_online()
    assert online is False
    assert options is None
    assert manager.snapshot()['process_running'] is False


def test_manager_reports_missing_executable(tmp_path):
    config = load_config(base_dir=tmp_path, env={
        'OCR_DATA_DIR': str(tmp_path / 'data'),
        'OCR_UMI_PORT': '9',
        'OCR_UMI_EXE': str(tmp_path / 'vendor' / 'missing.exe'),
    })
    manager = UmiManager(config)
    assert manager.probe()[0] is False
    assert manager.start_process() is False
    snapshot = manager.snapshot()
    assert snapshot['exe_exists'] is False
    assert '未找到' in snapshot['last_error']


def test_manager_snapshot_is_offline_before_first_probe(tmp_path):
    config = load_config(base_dir=tmp_path, env={
        'OCR_DATA_DIR': str(tmp_path / 'data'),
        'OCR_UMI_AUTOSTART': 'false',
    })
    snapshot = UmiManager(config).snapshot()
    assert snapshot['online'] is False
    assert snapshot['last_check'] is None