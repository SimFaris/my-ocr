# -*- coding: utf-8 -*-
"""上传文件的接收与校验。

两条原则：
1. 磁盘上的文件名一律用 uuid，绝不使用用户提供的文件名，避免路径穿越与重名覆盖。
2. 类型判断以文件头为准，扩展名只做白名单过滤（扩展名可以随便改，内容不会骗人）。
"""

import logging
from pathlib import Path

log = logging.getLogger(__name__)

IMAGE_EXTENSIONS = ('.jpg', '.jpe', '.jpeg', '.jfif', '.png', '.webp', '.bmp', '.tif', '.tiff')
PDF_EXTENSIONS = ('.pdf',)

_EXTENSION_ALIASES = {'.jpe': '.jpg', '.jfif': '.jpg', '.tif': '.tiff'}

_SIGNATURES = (
    (b'\xff\xd8\xff', 'image'),
    (b'\x89PNG\r\n\x1a\n', 'image'),
    (b'GIF87a', 'image'),
    (b'GIF89a', 'image'),
    (b'BM', 'image'),
    (b'II*\x00', 'image'),
    (b'MM\x00*', 'image'),
)
_WEBP_PREFIX = b'RIFF'
_WEBP_MARK = b'WEBP'
_PDF_MARK = b'%PDF-'


class IngestError(Exception):
    """上传校验失败。"""

    def __init__(self, code, message):
        Exception.__init__(self, message)
        self.code = code
        self.message = message


def normalize_extension(filename):
    """取小写扩展名并归一化别名（.jfif/.jpe 统一成 .jpg）。"""
    suffix = Path(str(filename or '')).suffix.lower()
    return _EXTENSION_ALIASES.get(suffix, suffix)


def detect_kind(head):
    """按文件头判断类型，返回 'image' / 'pdf' / None。"""
    if head.startswith(_PDF_MARK):
        return 'pdf'
    if head.startswith(_WEBP_PREFIX) and len(head) >= 12 and head[8:12] == _WEBP_MARK:
        return 'image'
    for signature, kind in _SIGNATURES:
        if head.startswith(signature):
            return kind
    return None


def accept_upload(storage, data_dir, job_id, item_id, allowed_kinds):
    """校验并保存上传文件。

    返回 (相对路径, 字节数, 类型, 扩展名)。相对路径以数据目录为基准。
    """
    original_name = storage.filename or ''
    extension = normalize_extension(original_name)
    if not extension:
        raise IngestError('unsupported_type', '文件缺少扩展名：%s' % original_name)

    head = storage.stream.read(16)
    try:
        storage.stream.seek(0)
    except (OSError, AttributeError):
        pass

    kind = detect_kind(head)
    if kind is None:
        raise IngestError('unsupported_type', '无法识别的文件内容：%s' % original_name)
    if kind not in allowed_kinds:
        raise IngestError('unsupported_type', '该任务不接受此类文件：%s' % original_name)
    if kind == 'image' and extension not in IMAGE_EXTENSIONS:
        raise IngestError('unsupported_type', '不支持的图片格式：%s' % extension)
    if kind == 'pdf' and extension not in PDF_EXTENSIONS:
        raise IngestError('unsupported_type', '不支持的文档格式：%s' % extension)

    target_dir = Path(data_dir) / 'uploads' / job_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / (item_id + extension)
    storage.save(str(target))

    relpath = 'uploads/%s/%s%s' % (job_id, item_id, extension)
    return relpath, target.stat().st_size, kind, extension


def resolve(data_dir, relpath):
    """把相对路径解析为绝对路径，并确保仍位于数据目录之内。"""
    base = Path(data_dir).resolve()
    target = (base / relpath).resolve()
    if base != target and base not in target.parents:
        raise IngestError('invalid_request', '非法路径：%s' % relpath)
    return target