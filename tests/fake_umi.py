# -*- coding: utf-8 -*-
"""可控的假 Umi-OCR 服务，用于测试与本地联调。

模式 mode:
    ok      —— 一切正常
    offline —— 所有接口返回 503，模拟引擎未启动
    error   —— 图片识别返回业务错误码
"""

import threading
from wsgiref.simple_server import make_server

from flask import Flask, jsonify, request

DEFAULT_OPTIONS = {
    'ocr.language': {
        'title': '语言/模型库', 'type': 'enum', 'default': 'models/config_chinese.txt',
        'optionsList': [['models/config_chinese.txt', '简体中文'],
                        ['models/config_en.txt', 'English']],
    },
    'tbpu.parser': {
        'title': '排版解析方案', 'type': 'enum', 'default': 'multi_para',
        'optionsList': [['multi_para', '多栏-按自然段换行'], ['single_line', '单栏-总是换行']],
    },
    'data.format': {
        'title': '数据返回格式', 'type': 'enum', 'default': 'dict',
        'optionsList': [['dict', '字典'], ['text', '纯文本']],
    },
}


def create_fake_app(state):
    app = Flask(__name__)

    @app.get('/control/mode/<mode>')
    def set_mode(mode):
        state['mode'] = mode
        return jsonify({'ok': True, 'mode': mode})

    @app.get('/control/calls')
    def calls():
        return jsonify({'calls': list(state['calls'])})

    @app.get('/api/ocr/get_options')
    def get_options():
        if state['mode'] == 'offline':
            return 'service unavailable', 503
        state['calls'].append('get_options')
        return jsonify(DEFAULT_OPTIONS)

    @app.get('/api/doc/get_options')
    def get_doc_options():
        if state['mode'] == 'offline':
            return 'service unavailable', 503
        state['calls'].append('get_doc_options')
        return jsonify(DEFAULT_OPTIONS)

    @app.post('/api/ocr')
    def ocr():
        payload = request.get_json(silent=True) or {}
        state['calls'].append('ocr')
        if state['mode'] == 'error':
            return jsonify({'code': 902, 'data': '向识别器进程传入指令失败，疑似子进程已崩溃'})
        if not payload.get('base64'):
            return jsonify({'code': 400, 'data': '缺少 base64'})
        fmt = (payload.get('options') or {}).get('data.format', 'text')
        text = state['image_text']
        if fmt == 'text':
            return jsonify({'code': 100, 'data': text, 'time': 0.1, 'timestamp': 0})
        return jsonify({
            'code': 100,
            'data': [{'text': text, 'score': 0.99,
                      'box': [[0, 0], [1, 0], [1, 1], [0, 1]], 'end': ''}],
            'time': 0.1, 'timestamp': 0,
        })

    @app.post('/api/doc/upload')
    def doc_upload():
        state['calls'].append('doc_upload')
        if state['mode'] == 'offline':
            return 'service unavailable', 503
        return jsonify({'code': 100, 'data': 'fake-doc-1'})

    @app.post('/api/doc/result')
    def doc_result():
        payload = request.get_json(silent=True) or {}
        state['calls'].append('doc_result')
        if state['mode'] == 'offline':
            return 'service unavailable', 503
        data = '第 1 页文字' if payload.get('is_data') else []
        return jsonify({'code': 100, 'data': data, 'processed_count': 1,
                        'pages_count': 1, 'is_done': True, 'state': 'success'})

    @app.post('/api/doc/download')
    def doc_download():
        state['calls'].append('doc_download')
        if state['mode'] == 'offline':
            return 'service unavailable', 503
        return jsonify({'code': 100, 'data': '/download/fake.txt', 'name': 'fake.txt'})

    @app.get('/download/<name>')
    def download(name):
        return '下载内容', 200, {'Content-Type': 'text/plain; charset=utf-8'}

    @app.get('/api/doc/clear/<task_id>')
    def clear(task_id):
        state['calls'].append('doc_clear')
        if state['mode'] == 'offline':
            return 'service unavailable', 503
        return jsonify({'code': 100, 'data': 'ok'})

    return app


class FakeUmi(object):
    """带控制开关的假 Umi-OCR。"""

    def __init__(self, mode='ok', image_text='识别结果示例'):
        self.state = {'mode': mode, 'image_text': image_text, 'calls': []}
        self.app = create_fake_app(self.state)
        self.port = None
        self._server = None
        self._thread = None

    def start(self, port=0):
        self._server = make_server('127.0.0.1', port, self.app)
        self.port = self._server.server_port
        self._thread = threading.Thread(target=self._server.serve_forever, name='fake-umi')
        self._thread.daemon = True
        self._thread.start()
        return self

    @property
    def base_url(self):
        return 'http://127.0.0.1:%d' % self.port

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None