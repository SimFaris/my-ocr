# -*- coding: utf-8 -*-
"""命令行重置用户密码（忘记管理员密码时用）。

在服务机上执行：

    python tools/reset_admin.py --list
    python tools/reset_admin.py --username admin
    python tools/reset_admin.py --username admin --password 新密码

不带 --password 时会生成一个随机密码并打印出来。执行后会删除初始密码文件，
并写一条审计记录。注意：已经登录的会话在过期前仍然有效（默认 7 天）；如果是因为
账号疑似泄露而重置，建议同时删除 data\\session.key 并重启服务，强制所有人重新登录。
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend import security                      # noqa: E402
from backend.config import load_config            # noqa: E402
from backend.db import Database                   # noqa: E402
from backend.repositories import audit            # noqa: E402
from backend.repositories import users as users_repo  # noqa: E402


def force_utf8_output():
    """输出到管道/文件时用 UTF-8，避免中文乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None:
                stream.reconfigure(errors='replace')
        except (AttributeError, ValueError, OSError):
            pass


def build_parser():
    parser = argparse.ArgumentParser(description='重置用户密码')
    parser.add_argument('--username', help='要重置的用户名')
    parser.add_argument('--password', help='指定新密码；不填则随机生成')
    parser.add_argument('--list', action='store_true', help='列出所有用户')
    parser.add_argument('--base-dir', help='项目根目录，默认自动探测')
    parser.add_argument('--data-dir', help='数据目录，默认读取配置')
    return parser


def main(argv=None):
    force_utf8_output()
    args = build_parser().parse_args(argv)

    overrides = {}
    if args.data_dir:
        overrides['data_dir'] = args.data_dir
    config = load_config(base_dir=args.base_dir, overrides=overrides or None)
    db = Database(config.db_path)
    db.init_schema()

    if args.list or not args.username:
        rows = users_repo.list_all(db)
        if not rows:
            print('数据库里还没有用户（服务首次启动时会自动创建管理员）')
            return 0
        print('用户列表：')
        for row in rows:
            print('  %-16s %-10s %s' % (row['username'],
                                       '管理员' if row['role'] == 'admin' else '普通用户',
                                       '启用' if row['is_active'] else '停用'))
        if not args.username:
            print('')
            print('用法：--username 用户名 [--password 新密码]')
        return 0

    user = users_repo.get_by_username(db, args.username)
    if user is None:
        print('[错误] 用户不存在：%s' % args.username)
        return 1

    password = args.password or security.generate_password()
    if len(password) < 8:
        print('[错误] 密码至少 8 位')
        return 1

    users_repo.set_password(db, user['id'], password)
    users_repo.drop_initial_password_file(config.data_dir)
    audit.write(db, 'password_reset_by_cli', user_id=None, target=user['username'],
                detail={'by': 'tools/reset_admin.py'})
    print('已重置用户 %s 的密码：%s' % (user['username'], password))
    print('请立即登录并在「修改密码」页面改成自己的密码。')
    return 0


if __name__ == '__main__':
    sys.exit(main())