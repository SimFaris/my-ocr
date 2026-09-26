# -*- coding: utf-8 -*-
"""Umi-OCR 进程托管：探测、启动、健康检查与崩溃重启。"""

import logging
import os
import subprocess
import threading
import time

from ..utils import now_iso
from .client import UmiClient

log = logging.getLogger(__name__)

CREATE_NO_WINDOW = 0x08000000


class UmiManager(object):
    """托管 Umi-OCR 进程，并对外提供健康状态快照。

    M1 只负责在线探测与进程启停；任务级调用由工作线程使用 self.client 完成。
    """

    def __init__(self, config, client=None, probe_client=None):
        self.config = config
        self.client = client or UmiClient(
            host=config['umi_host'], port=config['umi_port'],
            timeout=config['umi_request_timeout'], retries=config['umi_retries'])
        self.probe_client = probe_client or UmiClient(
            host=config['umi_host'], port=config['umi_port'], timeout=3, retries=1)
        self.check_interval = 30
        self.max_restarts = 5
        self._process = None
        self._process_started_at = None
        self._restarts = 0
        self._online = False
        self._last_error = None
        self._last_check = None
        self._log_handle = None
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread = None

    # ---------- 查询 ----------
    @property
    def base_url(self):
        return self.probe_client.base_url

    def probe(self):
        """实时探测引擎是否在线，返回 (online, options)。"""
        online, options = self.probe_client.probe()
        with self._lock:
            self._online = online
            self._last_check = now_iso()
            if online:
                self._last_error = None
                self._reset_restarts_if_stable()
            else:
                self._last_error = '无法连接 Umi-OCR（%s）' % self.base_url
        return online, options

    def snapshot(self):
        """返回状态快照，不发起网络请求。"""
        with self._lock:
            process = self._process
            running = bool(process is not None and process.poll() is None)
            return {
                'base_url': self.base_url,
                'online': bool(self._online),
                'process_running': running,
                'process_pid': process.pid if running else None,
                'autostart': bool(self.config['umi_autostart']),
                'exe_path': str(self.config.umi_exe),
                'exe_exists': self.config.umi_exe.is_file(),
                'restarts': self._restarts,
                'max_restarts': self.max_restarts,
                'last_error': self._last_error,
                'last_check': self._last_check,
            }

    # ---------- 进程管理 ----------
    def start_process(self):
        """按需启动 Umi-OCR.exe；返回是否处于运行状态。"""
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return True
            if not self.config['umi_autostart']:
                return False
            exe = self.config.umi_exe
            if not exe.is_file():
                self._last_error = '未找到 Umi-OCR 可执行文件：%s' % exe
                log.warning(self._last_error)
                return False
            self._close_log_handle()
            log_path = self.config.log_dir / 'umi-ocr.log'
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_handle = open(str(log_path), 'ab')
            creationflags = CREATE_NO_WINDOW if os.name == 'nt' else 0
            try:
                self._process = subprocess.Popen(
                    [str(exe)], cwd=str(exe.parent),
                    stdout=self._log_handle, stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL, creationflags=creationflags)
            except OSError as exc:
                self._last_error = '启动 Umi-OCR 失败：%s' % exc
                log.warning(self._last_error)
                self._close_log_handle()
                return False
            self._process_started_at = time.time()
            log.info('已启动 Umi-OCR：pid=%s，日志见 %s', self._process.pid, log_path)
            return True

    def ensure_online(self):
        """探测；离线且允许自启时尝试启动。返回 (online, options)。"""
        online, options = self.probe()
        if online:
            return True, options
        if not self.config['umi_autostart']:
            return False, None
        with self._lock:
            if self._restarts >= self.max_restarts:
                self._last_error = ('Umi-OCR 连续重启 %d 次仍不可用，已停止自动重启，'
                                    '请人工检查' % self._restarts)
                return False, None
        if not self.start_process():
            return False, None
        time.sleep(1.5)
        online, options = self.probe()
        if not online:
            with self._lock:
                self._restarts += 1
        return online, options

    # ---------- 监控线程 ----------
    def start_monitor(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, name='umi-monitor')
        self._thread.daemon = True
        self._thread.start()

    def _monitor_loop(self):
        while not self._stop_event.is_set():
            try:
                self.ensure_online()
            except Exception:
                log.exception('Umi-OCR 监控循环异常')
            self._stop_event.wait(self.check_interval)

    def stop(self):
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5)
            self._thread = None
        with self._lock:
            process = self._process
            if process is not None and process.poll() is None:
                log.info('停止 Umi-OCR：pid=%s', process.pid)
                process.terminate()
                try:
                    process.wait(timeout=10)
                except Exception:
                    process.kill()
            self._process = None
            self._close_log_handle()

    # ---------- 内部 ----------
    def _reset_restarts_if_stable(self):
        process = self._process
        if process is None or process.poll() is not None:
            self._restarts = 0
            return
        started = self._process_started_at or 0
        if started and (time.time() - started) > 120:
            self._restarts = 0

    def _close_log_handle(self):
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except Exception:
                pass
            self._log_handle = None