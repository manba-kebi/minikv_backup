# -*- coding: utf-8 -*-
"""
main.py —— 命令行入口，把三个功能串起来

用法示例（在 minikv_backup 目录下执行）：
    python main.py backup                  # 备份一次
    python main.py backup --interval 60    # 每 60 秒备份一次（Ctrl+C 停止）
    python main.py restore                 # 恢复最近一次备份
    python main.py restore --batch 3       # 恢复第 3 个批次
    python main.py prune --keep 5          # 只保留最近 5 个批次

所有参数都有默认值，MySQL 密码默认空，如果和你的实际环境不同，
在命令后面追加，例如：
    python main.py backup --db-user root --db-password 你的密码
"""

import argparse
import time

from mysql_store import KVStore
from snapshot import run_backup
from restore import run_restore


def parse_args():
    p = argparse.ArgumentParser(
        description="minikv_backup：mini_kv_server 的 MySQL 备份/恢复工具")
    sub = p.add_subparsers(dest="action", required=True)        # 增加子命令解析器
    #`dest="action"`：把子命令名字（backup/restore/prune）存到`args.action`变量里；
    #`required=True`：必须写子命令，不能只写`python main.py`，必须后面带上 backup/restore/prune。

    # backup / restore / prune 三个子命令共用一组连接参数
    def add_common(sp):
        sp.add_argument("--kv-host", default="127.0.0.1", help="mini_kv_server 地址")
        sp.add_argument("--kv-port", type=int, default=9000, help="mini_kv_server 端口")
        sp.add_argument("--db-host", default="127.0.0.1", help="MySQL 地址")
        sp.add_argument("--db-port", type=int, default=3306, help="MySQL 端口")
        sp.add_argument("--db-user", default="root", help="MySQL 用户名")
        sp.add_argument("--db-password", default="", help="MySQL 密码")
        sp.add_argument("--db-name", default="minikv", help="MySQL 库名")

    # 新建一个叫 backup 的子命令解析器，返回`sp_b`（sp 就是 subparser 简写）。同理 sp_r 是 restore、sp_p 是 prune。
    sp_b = sub.add_parser("backup", help="全量备份到 MySQL")
    add_common(sp_b)
    sp_b.add_argument("--interval", type=int, default=0,
                      help=">0 时每隔 N 秒循环备份，Ctrl+C 结束")

    sp_r = sub.add_parser("restore", help="从 MySQL 恢复到服务端")
    add_common(sp_r)
    sp_r.add_argument("--batch", type=int, default=None,
                      help="恢复指定批次，默认恢复最近一次")

    sp_p = sub.add_parser("prune", help="清理历史快照")
    add_common(sp_p)
    sp_p.add_argument("--keep", type=int, default=10, help="保留最近 N 个批次")

    return p.parse_args()


def main():
    args = parse_args()

    # 把所有 MySQL 参数打包成一个 KVStore 对象，传给各功能模块
    db = KVStore(host=args.db_host, port=args.db_port, user=args.db_user,
                 password=args.db_password, database=args.db_name)

    if args.action == "backup":
        if args.interval > 0:
            print(f"每 {args.interval} 秒备份一次，按 Ctrl+C 停止")
            while True:
                try:
                    run_backup(args.kv_host, args.kv_port, db)
                except Exception as e:
                    print(f"本次备份失败：{e}")
                time.sleep(args.interval)
        else:
            run_backup(args.kv_host, args.kv_port, db)

    elif args.action == "restore":
        run_restore(args.kv_host, args.kv_port, db, batch_id=args.batch)

    elif args.action == "prune":
        with db:
            n = db.prune(keep=args.keep)
        print(f"已清理 {n} 行（只保留最近 {args.keep} 个批次）")


if __name__ == "__main__":
    main()
