# -*- coding: utf-8 -*-
"""启动前自检：报告运行环境、关键路径与端口占用情况。

用法：
    python tools/check_env.py
返回码：0 表示可以启动；1 表示存在硬性阻塞（数据目录不可写或端口被占用）。
"""

import argparse
import socket
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import load_config  # noqa: E402


def force_utf8_output():
    """保留平台控制台编码，只把无法编码的字符替换掉。

    与批处理脚本的输出编码保持一致，重定向到同一个文件时不会出现两种编码混排。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None:
                stream.reconfigure(errors='replace')
        except (AttributeError, ValueError, OSError):
            pass

def port_free(host, port):
    """尝试绑定端口判断是否空闲。

    这里故意不设置 SO_REUSEADDR：Windows 上它会导致已占用的端口也能绑定成功，
    检查就失去意义。
    """
    if not port:
        return True
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        bind_host = '' if host in ('0.0.0.0', '::') else host
        probe.bind((bind_host, int(port)))
    except OSError:
        return False
    finally:
        probe.close()
    return True


def writable(path):
    probe = Path(path) / '.write_probe'
    try:
        probe.write_text('ok', encoding='utf-8')
        probe.unlink()
        return True
    except OSError:
        return False


def build_parser():
    parser = argparse.ArgumentParser(description='启动前环境自检')
    parser.add_argument('--base-dir', help='项目根目录，默认自动探测')
    parser.add_argument('--config', help='config.json 路径')
    parser.add_argument('--host', help='监听地址')
    parser.add_argument('--http-port', type=int, help='http 端口')
    parser.add_argument('--https-port', type=int, help='https 端口')
    parser.add_argument('--no-https', action='store_true', help='不启用 https')
    return parser


def main(argv=None):
    force_utf8_output()
    args = build_parser().parse_args(argv)

    # 必须与 run.py 用同一套覆盖规则：否则启动脚本传了 --http-port，
    # 自检却还去检查 config.json 里的旧端口，会误报"端口被占用"而不让启动。
    overrides = {}
    if args.host:
        overrides['host'] = args.host
    if args.http_port is not None:
        overrides['http_port'] = args.http_port
    if args.https_port is not None:
        overrides['https_port'] = args.https_port
    if args.no_https:
        overrides['enable_https'] = False

    config = load_config(base_dir=args.base_dir, config_path=args.config,
                         overrides=overrides or None)
    blocked = False

    print('Python 版本    : %s' % sys.version.split()[0])
    print('项目根目录     : %s' % PROJECT_ROOT)
    print('数据目录       : %s' % config.data_dir)

    data_ok = writable(config.data_dir)
    print('数据目录可写   : %s' % ('是' if data_ok else '否'))
    if not data_ok:
        blocked = True

    cert = config.cert_path('server.crt')
    print('自签证书       : %s' % ('已存在' if cert.is_file() else '未生成，启动时会自动生成'))

    umi_exe = config.umi_exe
    print('Umi-OCR 路径   : %s' % umi_exe)
    print('Umi-OCR 可执行 : %s' % ('存在' if umi_exe.is_file() else '未找到，引擎会显示不可用'))

    dist = Path(config['frontend_dist_dir'])
    built = (dist / 'index.html').is_file()
    print('前端产物       : %s' % ('已构建' if built else '未构建，页面会显示后端占位页'))

    http_port = int(config['http_port'])
    https_port = int(config['https_port']) if config['enable_https'] else 0
    print('监听配置       : http %s，https %s' % (http_port or '关闭', https_port or '关闭'))

    for label, port in (('http', http_port), ('https', https_port)):
        if not port:
            continue
        free = port_free(config['host'], port)
        print('端口 %-8s : %s' % (label, '可用' if free else '被占用'))
        if not free:
            blocked = True

    print('')
    print('自检结果       : %s' % ('可以启动' if not blocked else '存在阻塞项，请先处理'))
    return 1 if blocked else 0


if __name__ == '__main__':
    sys.exit(main())