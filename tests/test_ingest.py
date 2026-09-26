# -*- coding: utf-8 -*-
"""上传校验测试。"""

import io

import pytest
from werkzeug.datastructures import FileStorage

from backend.services.ingest import (IMAGE_EXTENSIONS, IngestError, accept_upload,
                                     detect_kind, normalize_extension, resolve)

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 40
JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 40
PDF = b'%PDF-1.4\n' + b'\x00' * 40
WEBP = b'RIFF' + b'\x00\x00\x00\x00' + b'WEBP' + b'\x00' * 20
TIFF = b'II*\x00' + b'\x00' * 40
BMP = b'BM' + b'\x00' * 40
GIF = b'GIF89a' + b'\x00' * 40
UNKNOWN = b'not an image at all'


def storage(data, filename):
    return FileStorage(stream=io.BytesIO(data), filename=filename)


def test_normalize_extension_aliases():
    assert normalize_extension('a.PNG') == '.png'
    assert normalize_extension('b.jpe') == '.jpg'
    assert normalize_extension('c.JFIF') == '.jpg'
    assert normalize_extension('d.tif') == '.tiff'
    assert normalize_extension('noext') == ''


def test_detect_kind_by_content():
    assert detect_kind(PNG) == 'image'
    assert detect_kind(JPEG) == 'image'
    assert detect_kind(WEBP) == 'image'
    assert detect_kind(TIFF) == 'image'
    assert detect_kind(BMP) == 'image'
    assert detect_kind(PDF) == 'pdf'
    assert detect_kind(UNKNOWN) is None


def test_accept_upload_stores_with_uuid_name(tmp_path):
    relpath, size, kind, extension = accept_upload(
        storage(PNG, '../../evil name.png'), tmp_path, 'job1', 'item1', ('image',))
    assert relpath == 'uploads/job1/item1.png'
    assert kind == 'image'
    assert extension == '.png'
    assert size == len(PNG)
    stored = tmp_path / relpath
    assert stored.is_file()
    # 文件名里不能出现用户提供的路径片段
    assert 'evil' not in str(stored)


def test_accept_upload_rejects_content_mismatch(tmp_path):
    with pytest.raises(IngestError) as excinfo:
        accept_upload(storage(PDF, 'fake.png'), tmp_path, 'job1', 'item1', ('image',))
    assert excinfo.value.code == 'unsupported_type'


def test_accept_upload_rejects_unsupported_extension(tmp_path):
    with pytest.raises(IngestError):
        accept_upload(storage(GIF, 'a.gif'), tmp_path, 'job1', 'item1', ('image',))

    with pytest.raises(IngestError):
        accept_upload(storage(UNKNOWN, 'a.png'), tmp_path, 'job1', 'item1', ('image',))

    with pytest.raises(IngestError):
        accept_upload(storage(PNG, 'noext'), tmp_path, 'job1', 'item1', ('image',))


def test_resolve_rejects_path_traversal(tmp_path):
    with pytest.raises(IngestError):
        resolve(tmp_path, '../../windows/system.ini')
    assert resolve(tmp_path, 'uploads/a.png').parent == (tmp_path / 'uploads').resolve()


def test_image_extension_whitelist_covers_umi_formats():
    for extension in ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'):
        assert extension in IMAGE_EXTENSIONS