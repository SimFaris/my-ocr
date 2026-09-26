# -*- coding: utf-8 -*-
"""识别结果导出：txt 与 csv。"""

import csv
import logging
from pathlib import Path

from ..utils import now_iso

log = logging.getLogger(__name__)

STATUS_LABELS = {
    'pending': '待提交',
    'queued': '排队中',
    'running': '识别中',
    'done': '成功',
    'empty': '无文字',
    'failed': '失败',
    'skipped': '已跳过',
}


def status_label(status):
    return STATUS_LABELS.get(status, status)


def read_text(data_dir, item):
    """读取单项识别文本；没有结果时返回空串。"""
    if not item['text_relpath']:
        return ''
    path = Path(data_dir) / item['text_relpath']
    try:
        return path.read_text(encoding='utf-8')
    except OSError as exc:
        log.warning('读取识别文本失败 %s：%s', item['text_relpath'], exc)
        return ''


def export_txt(data_dir, job, items, path):
    """导出合并 txt：每个文件一段，带文件名与状态。"""
    lines = [
        '# %s' % job['title'],
        '# 任务编号：%s' % job['id'],
        '# 导出时间：%s' % now_iso(),
        '# 共 %d 个文件' % len(items),
        '',
    ]
    for item in items:
        lines.append('===== %s（%s）=====' % (item['original_name'], status_label(item['status'])))
        if item['status'] == 'failed' and item['error_message']:
            lines.append('（识别失败：%s）' % item['error_message'])
            lines.append('')
            continue
        text = read_text(data_dir, item)
        lines.append(text if text.strip() else '（无文字）')
        lines.append('')
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('\n'.join(lines), encoding='utf-8')
    return target


def export_csv(data_dir, items, path):
    """导出 csv；使用 utf-8-sig 以便 Excel 直接打开不乱码。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(str(target), 'w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['序号', '文件名', '状态', '字符数', '耗时(秒)', '识别文本'])
        for item in items:
            writer.writerow([
                item['seq'],
                item['original_name'],
                status_label(item['status']),
                item['char_count'] or 0,
                round((item['duration_ms'] or 0) / 1000.0, 2),
                read_text(data_dir, item),
            ])
    return target