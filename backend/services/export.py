# -*- coding: utf-8 -*-
"""识别结果导出：txt 与 csv。"""

import csv
import logging
from pathlib import Path

from ..utils import now_iso

log = logging.getLogger(__name__)

class ExportError(Exception):
    """导出失败。"""

    def __init__(self, message):
        Exception.__init__(self, message)
        self.message = message


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


def export_xlsx(data_dir, job, items, path):
    """导出 Excel；openpyxl 是纯 Python 依赖，目标机不需要装 Office。"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font
    except ImportError:
        raise ExportError('服务端缺少 openpyxl，无法导出 Excel；可改用 csv，'
                          '或执行 pip install -r requirements.txt')

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = '识别结果'
    sheet.append(['序号', '文件名', '状态', '字符数', '耗时(秒)', '识别文本'])
    for item in items:
        sheet.append([
            item['seq'],
            item['original_name'],
            status_label(item['status']),
            item['char_count'] or 0,
            round((item['duration_ms'] or 0) / 1000.0, 2),
            read_text(data_dir, item),
        ])

    for cell in sheet[1]:
        cell.font = Font(bold=True)
    sheet.freeze_panes = 'A2'
    sheet.column_dimensions['B'].width = 32
    sheet.column_dimensions['F'].width = 60
    for row in sheet.iter_rows(min_row=2, min_col=6, max_col=6):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical='top')

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(str(target))
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