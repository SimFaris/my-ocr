# -*- coding: utf-8 -*-
"""启动入口：同时监听 http 与 https。

使用 cheroot（纯 Python WSGI 服务器）而不是 waitress，因为 waitress 官方明确
不支持 TLS，而浏览器调用摄像头必须走 HTTPS。
"""

import argparse
import logging
import os
import socket
import sys
import threading
import time

from cheroot import wsgi
from cheroot.ssl.builtin import BuiltinSSLAdapter

from backend.app import create_app
from backend.config import load_config

log = logging.getLogger(__name__)


def port_in_use(host, port):
    """判断端口是否已被占用。

    这里刻意不使用 SO_REUSEADDR：Windows 上它会让"已被占用"的端口也能绑定成功，
    结果两个服务实例同时在跑，请求被旧实例接走，排查起来非常费劲。
    """
    if not port:
        return False
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        bind_host = '' if host in ('0.0.0.0', '::') else host
        probe.bind((bind_host, int(port)))
    except OSError:
        return True
    finally:
        probe.close()
    return False


def build_servers(app, config):
    """按配置创建 http / https 监听，返回 [(scheme, server)]。"""
    servers = []
    threads = int(config['web_threads'])

    if int(config['http_port']) > 0:
        servers.append(('http', wsgi.Server(
            (config['host'], int(config['http_port'])), app,
            numthreads=threads, timeout=60, shutdown_timeout=5)))

    if config['enable_https'] and int(config['https_port']) > 0:
        cert = str(config.cert_path('server.crt'))
        key = str(config.cert_path('server.key'))
        if os.path.isfile(cert) and os.path.isfile(key):
            server = wsgi.Server((config['host'], int(config['https_port'])), app,
                                 numthreads=threads, timeout=60, shutdown_timeout=5)
            server.ssl_adapter = BuiltinSSLAdapter(cert, key)
            servers.append(('https', server))
        else:
            log.warning('未找到证书 %s / %s，https 监听未启用；可先运行 tools/gen_cert.ps1',
                        cert, key)
    return servers


def main(argv=None):
    parser = argparse.ArgumentParser(description='局域网离线 OCR 服务')
    parser.add_argument('--base-dir', help='项目根目录，默认自动探测')
    parser.add_argument('--config', help='config.json 路径')
    parser.add_argument('--host', help='监听地址，默认 0.0.0.0')
    parser.add_argument('--http-port', type=int, help='http 端口，0 表示关闭')
    parser.add_argument('--https-port', type=int, help='https 端口，0 表示关闭')
    parser.add_argument('--no-https', action='store_true', help='本次运行不启用 https')
    args = parser.parse_args(argv)

    overrides = {}
    if args.host:
        overrides['host'] = args.host
    if args.http_port is not None:
        overrides['http_port'] = args.http_port
    if args.https_port is not None:
        overrides['https_port'] = args.https_port
    if args.no_https:
        overrides['enable_https'] = False

    config = load_config(base_dir=args.base_dir, config_path=args.config, overrides=overrides)
    app = create_app(config)

    wanted = [('http', int(config['http_port']))]
    if config['enable_https']:
        wanted.append(('https', int(config['https_port'])))
    conflicts = [item for item in wanted if port_in_use(config['host'], item[1])]
    if conflicts:
        log.error('以下端口已被占用：%s。通常是上一个服务实例还在运行，请先停止它再启动。',
                  '、'.join('%s %d' % item for item in conflicts))
        return 3

    servers = build_servers(app, config)
    if not servers:
        log.error('没有可用的监听端口（http/https 都已关闭或证书缺失），退出')
        return 2

    for _scheme, server in servers:
        server.prepare()
    log.info('服务已启动：%s', '，'.join(
        '%s://%s:%s' % (scheme, config['host'], server.bind_addr[1])
        for scheme, server in servers))

    context = app.extensions['ocr']
    context['umi'].start_monitor()
    context['queue'].start()
    context['retention'].start()

    try:
        for scheme, server in servers:
            worker = threading.Thread(target=server.serve, name='serve-%s' % scheme)
            worker.daemon = True
            worker.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info('收到中断信号，正在停止…')
    finally:
        for _scheme, server in servers:
            try:
                server.stop()
            except Exception:
                log.exception('停止监听失败')
        context['retention'].stop()
        context['queue'].stop()
        context['umi'].stop()
        log.info('已停止')
    return 0


if __name__ == '__main__':
    sys.exit(main())