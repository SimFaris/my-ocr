# -*- coding: utf-8 -*-
"""接口层公共辅助。"""

from flask import current_app, jsonify, request


def ok(data=None, status=200):
    return jsonify({'ok': True, 'data': data}), status


def fail(code, message, status=400):
    return jsonify({'ok': False, 'error': {'code': code, 'message': message}}), status


def context():
    """当前应用的上下文对象：配置、数据库、Umi 管理器、限速器。"""
    return current_app.extensions['ocr']


def client_ip():
    """客户端 IP：优先取代理头，否则用直连地址。"""
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or '-'