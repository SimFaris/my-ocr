# -*- coding: utf-8 -*-
"""Umi-OCR HTTP 客户端：全系统唯一出口，含超时与重试。"""

import base64
import json
import logging
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

TRANSPORT_ERRORS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)

JSON_HEADERS = {'Content-Type': 'application/json'}


class UmiError(Exception):
    """Umi 调用失败。retryable 表示属于可重试的连接类故障。"""

    def __init__(self, message, code='umi_error', retryable=False):
        Exception.__init__(self, message)
        self.message = message
        self.code = code
        self.retryable = retryable


def reason_of(data, fallback):
    """从 Umi 返回体中提取可读的失败原因。"""
    if isinstance(data, str) and data.strip():
        return data.strip()
    if isinstance(data, dict):
        for key in ('message', 'data', 'msg'):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return fallback


def flatten_data(data):
    """把识别结果统一成纯文本；data.format=dict 时按 text+end 拼接。"""
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        parts = []
        for block in data:
            if isinstance(block, dict):
                parts.append(str(block.get('text') or ''))
                parts.append(str(block.get('end') or ''))
            elif isinstance(block, str):
                parts.append(block)
        return ''.join(parts)
    if data is None:
        return ''
    return str(data)


class UmiClient(object):
    """封装 Umi-OCR 的 HTTP 接口。"""

    def __init__(self, host='127.0.0.1', port=1224, timeout=120,
                 retries=3, retry_backoff=(1, 3, 9), session=None):
        self.base_url = 'http://%s:%d' % (host, int(port))
        self.timeout = timeout
        self.retries = max(1, int(retries))
        self.retry_backoff = tuple(retry_backoff)
        self._session = session or requests.Session()

    # ---------- 底层请求 ----------
    def _url(self, path):
        if path.startswith('http://') or path.startswith('https://'):
            return path
        return self.base_url + path

    def _request(self, method, path, **kwargs):
        url = self._url(path)
        kwargs.setdefault('timeout', self.timeout)
        last_error = None
        for attempt in range(self.retries):
            try:
                response = self._session.request(method, url, **kwargs)
            except TRANSPORT_ERRORS as exc:
                last_error = UmiError('无法连接 Umi-OCR：%s' % exc,
                                      code='umi_unavailable', retryable=True)
            else:
                if response.status_code >= 500:
                    last_error = UmiError('Umi-OCR 返回 %d' % response.status_code,
                                          code='umi_unavailable', retryable=True)
                elif response.status_code >= 400:
                    raise UmiError('Umi-OCR 返回 %d' % response.status_code,
                                   code='umi_bad_request', retryable=False)
                else:
                    return response
            if attempt < self.retries - 1:
                delay = self.retry_backoff[min(attempt, len(self.retry_backoff) - 1)]
                log.warning('Umi 请求失败(%s %s)，%s 秒后重试：%s', method, path, delay, last_error)
                time.sleep(delay)
        raise last_error

    def _json(self, method, path, **kwargs):
        response = self._request(method, path, **kwargs)
        try:
            return response.json()
        except ValueError:
            raise UmiError('Umi-OCR 返回值不是合法 JSON',
                           code='umi_bad_response', retryable=False)

    # ---------- 通用 ----------
    def probe(self):
        """轻量健康探测：能取到图片识别参数即视为在线。"""
        try:
            data = self._json('GET', '/api/ocr/get_options')
        except UmiError as exc:
            log.debug('Umi 探测失败：%s', exc)
            return False, None
        if isinstance(data, dict) and data:
            return True, data
        return False, None

    def get_ocr_options(self):
        return self._json('GET', '/api/ocr/get_options')

    def get_doc_options(self):
        return self._json('GET', '/api/doc/get_options')

    # ---------- 图片识别 ----------
    def ocr_image(self, image_path, options=None):
        """识别单张图片，返回 {'status','text','raw'}。"""
        raw = Path(image_path).read_bytes()
        payload = {'base64': base64.b64encode(raw).decode('ascii')}
        if options:
            payload['options'] = options
        data = self._json('POST', '/api/ocr',
                          data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                          headers=JSON_HEADERS)
        code = data.get('code')
        if code == 100:
            return {'status': 'done', 'text': flatten_data(data.get('data')), 'raw': data}
        if code == 101:
            return {'status': 'empty', 'text': '', 'raw': data}
        raise UmiError(reason_of(data, '识别失败（code=%s）' % code),
                       code='umi_ocr_failed', retryable=False)

    # ---------- 文档识别 ----------
    def doc_upload(self, file_path, options=None):
        """上传文档，返回 Umi 任务 ID。"""
        path = Path(file_path)
        handle = open(str(path), 'rb')
        try:
            files = {'file': (path.name, handle, 'application/octet-stream')}
            form = {}
            if options:
                form['json'] = json.dumps(options, ensure_ascii=False)
            data = self._json('POST', '/api/doc/upload', files=files, data=form,
                              timeout=max(self.timeout, 600))
        finally:
            handle.close()
        if data.get('code') != 100:
            raise UmiError(reason_of(data, '上传文档失败（code=%s）' % data.get('code')),
                           code='umi_doc_upload_failed', retryable=False)
        return data.get('data')

    def doc_result(self, task_id, with_data=False, fmt='text'):
        """查询文档任务状态；with_data=True 时附带识别结果。"""
        payload = {
            'id': task_id,
            'is_data': bool(with_data),
            'is_unread': True,
            'format': fmt,
        }
        data = self._json('POST', '/api/doc/result',
                          data=json.dumps(payload).encode('utf-8'), headers=JSON_HEADERS)
        if data.get('code') != 100:
            raise UmiError(reason_of(data, '查询文档任务失败（code=%s）' % data.get('code')),
                           code='umi_doc_result_failed', retryable=False)
        return data

    def doc_download(self, task_id, file_types=('txtPlain',), ignore_blank=True):
        """请求生成产物，返回 {'name','url'}。"""
        payload = {
            'id': task_id,
            'file_types': list(file_types),
            'ignore_blank': bool(ignore_blank),
        }
        data = self._json('POST', '/api/doc/download',
                          data=json.dumps(payload).encode('utf-8'), headers=JSON_HEADERS)
        if data.get('code') != 100:
            raise UmiError(reason_of(data, '生成下载文件失败（code=%s）' % data.get('code')),
                           code='umi_doc_download_failed', retryable=False)
        url = data.get('data')
        if not isinstance(url, str) or not url:
            raise UmiError('Umi-OCR 未返回下载链接',
                           code='umi_bad_response', retryable=False)
        return {'name': data.get('name') or 'result', 'url': url}

    def download(self, url, dest_path):
        """把 Umi 提供的下载链接保存到本地文件。"""
        response = self._request('GET', url, timeout=max(self.timeout, 900), stream=True)
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(str(dest), 'wb') as handle:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    handle.write(chunk)
        return dest

    def doc_clear(self, task_id):
        """清理 Umi 侧任务；失败只记日志，不抛出。"""
        try:
            return self._json('GET', '/api/doc/clear/%s' % task_id)
        except UmiError as exc:
            log.warning('清理 Umi 任务 %s 失败：%s', task_id, exc)
            return None