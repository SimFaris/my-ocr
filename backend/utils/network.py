# -*- coding: utf-8 -*-
"""客户端机器名的尽力解析。

浏览器不会把主机名发上来，只能拿 IP 反查局域网内的 DNS/NetBIOS 名字。局域网里
经常查不到，所以这里的约定是：查不到就返回 None，界面只显示 IP，绝不影响业务。
解析放在后台线程里做，结果（包括失败）缓存下来，避免重复查询。
"""

import logging
import socket
import threading

log = logging.getLogger(__name__)

_cache = {}
_lock = threading.Lock()
LOCAL_ADDRESSES = ('127.0.0.1', '::1', 'localhost')


def resolve_hostname(ip):
    """把 IP 反解成机器名；失败返回 None。结果会缓存。"""
    if not ip:
        return None
    if ip in LOCAL_ADDRESSES:
        return '本机'
    with _lock:
        if ip in _cache:
            return _cache[ip]
    try:
        name = socket.gethostbyaddr(ip)[0]
    except Exception:                      # noqa: BLE001 - 解析失败是常态
        name = None
    with _lock:
        _cache[ip] = name
    return name


def resolve_in_background(ip, apply_result):
    """在后台线程里解析，解析到名字时回调 apply_result(名字)。"""
    if not ip:
        return None
    if ip in LOCAL_ADDRESSES:
        apply_result('本机')
        return None

    def worker():
        try:
            name = resolve_hostname(ip)
            if name:
                apply_result(name)
        except Exception:
            log.debug('解析客户端机器名失败：%s', ip)

    thread = threading.Thread(target=worker, name='resolve-client-host')
    thread.daemon = True
    thread.start()
    return thread