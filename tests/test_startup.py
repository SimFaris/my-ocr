# -*- coding: utf-8 -*-
"""启动入口相关测试：端口占用检查。"""

import importlib.util
import socket
from pathlib import Path

import run

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def hold_port():
    """占用一个随机可用端口，返回 (socket, port)。"""
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(('127.0.0.1', 0))
    holder.listen(1)
    return holder, holder.getsockname()[1]


def test_run_detects_occupied_port():
    """服务启动前必须能发现端口被占用。

    cheroot 默认开启 SO_REUSEADDR，Windows 上两个实例能绑同一端口，
    结果请求被旧实例接走——所以启动前必须自己检查。
    """
    holder, port = hold_port()
    try:
        assert run.port_in_use('127.0.0.1', port) is True
    finally:
        holder.close()
    assert run.port_in_use('127.0.0.1', port) is False


def test_run_reports_free_port_as_free():
    holder, port = hold_port()
    holder.close()
    assert run.port_in_use('127.0.0.1', port) is False
    assert run.port_in_use('127.0.0.1', 0) is False


def load_check_env():
    path = PROJECT_ROOT / 'tools' / 'check_env.py'
    spec = importlib.util.spec_from_file_location('check_env_module', str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_check_env_port_free_matches_reality():
    module = load_check_env()
    holder, port = hold_port()
    try:
        assert module.port_free('127.0.0.1', port) is False
    finally:
        holder.close()
    assert module.port_free('127.0.0.1', port) is True