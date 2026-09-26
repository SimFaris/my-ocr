# -*- coding: utf-8 -*-
"""Umi-OCR 客户端测试（对假服务）。"""

import pytest

from backend.umi.client import UmiClient, UmiError, flatten_data
from fake_umi import FakeUmi


@pytest.fixture
def fake():
    server = FakeUmi().start()
    yield server
    server.stop()


def make_client(fake, **kwargs):
    options = {'host': '127.0.0.1', 'port': fake.port, 'timeout': 5, 'retries': 1}
    options.update(kwargs)
    return UmiClient(**options)


def test_flatten_data_variants():
    assert flatten_data('abc') == 'abc'
    assert flatten_data(None) == ''
    assert flatten_data([{'text': '第一行', 'end': '\n'}, {'text': '第二行', 'end': ''}]) == '第一行\n第二行'


def test_probe_online_then_offline(fake):
    client = make_client(fake)
    online, options = client.probe()
    assert online is True
    assert 'ocr.language' in options

    fake.state['mode'] = 'offline'
    online_again, _ = client.probe()
    assert online_again is False


def test_ocr_image_text_format(tmp_path, fake):
    image = tmp_path / 'sample.png'
    image.write_bytes(b'\x89PNG\r\n\x1a\n' + b'0' * 32)
    fake.state['image_text'] = '你好，世界'

    client = make_client(fake)
    result = client.ocr_image(str(image), {'data.format': 'text'})
    assert result['status'] == 'done'
    assert result['text'] == '你好，世界'


def test_ocr_image_dict_format_is_flattened(tmp_path, fake):
    image = tmp_path / 'sample.png'
    image.write_bytes(b'\x89PNG\r\n\x1a\n' + b'0' * 32)
    fake.state['image_text'] = '只有一行'

    client = make_client(fake)
    result = client.ocr_image(str(image), {'data.format': 'dict'})
    assert result['status'] == 'done'
    assert result['text'] == '只有一行'


def test_ocr_image_business_error_is_not_retryable(tmp_path):
    server = FakeUmi(mode='error').start()
    try:
        image = tmp_path / 'sample.png'
        image.write_bytes(b'\x89PNG\r\n\x1a\n')
        client = make_client(server)
        with pytest.raises(UmiError) as excinfo:
            client.ocr_image(str(image), {})
        assert excinfo.value.retryable is False
        assert excinfo.value.code == 'umi_ocr_failed'
    finally:
        server.stop()


def test_document_flow(tmp_path, fake):
    document = tmp_path / 'doc.pdf'
    document.write_bytes(b'%PDF-1.4\n')

    client = make_client(fake)
    task_id = client.doc_upload(str(document), {'doc.extractionMode': 'mixed'})
    assert task_id == 'fake-doc-1'

    status = client.doc_result(task_id)
    assert status['is_done'] is True
    assert status['pages_count'] == 1

    with_text = client.doc_result(task_id, with_data=True)
    assert with_text['data'] == '第 1 页文字'

    artifact = client.doc_download(task_id, ['txtPlain'])
    assert artifact['url'].startswith('/download/')
    saved = client.download(artifact['url'], tmp_path / 'out' / 'result.txt')
    assert saved.read_text(encoding='utf-8') == '下载内容'

    assert client.doc_clear(task_id)['code'] == 100


def test_transport_error_is_retryable():
    client = UmiClient(host='127.0.0.1', port=9, timeout=1, retries=2, retry_backoff=(0, 0))
    with pytest.raises(UmiError) as excinfo:
        client.get_ocr_options()
    assert excinfo.value.retryable is True
    assert excinfo.value.code == 'umi_unavailable'