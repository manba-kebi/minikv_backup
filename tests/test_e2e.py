# -*- coding: utf-8 -*-
"""
test_e2e.py —— 端到端测试：完整走一遍 备份 -> 清空 -> 恢复 -> 校验

前置条件（三个都要满足）：
    1. mini_kv_server 正在运行（同 test_client.py 的启动命令）
    2. MySQL 已启动，且已经执行过 schema.sql 建好 minikv 库
    3. 下面的 DB 参数和你的 MySQL 一致（尤其密码）

运行：
    python tests/test_e2e.py --db-password 你的密码

这个脚本演示了本项目最核心的价值：
    C++ 服务端的数据 -> 备份到 MySQL -> 模拟丢失 -> 从 MySQL 恢复 -> 数据回来了
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from minikv_client import MiniKVClient
from mysql_store import KVStore
from snapshot import run_backup
from restore import run_restore

HOST, PORT = "127.0.0.1", 9000
N = 50  # 造多少条测试数据


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db-password", default="", help="MySQL 密码")
    p.add_argument("--db-user", default="root")
    args = p.parse_args()

    db = KVStore(host="127.0.0.1", port=3306, user=args.db_user,
                 password=args.db_password, database="minikv")

    # ---- 1) 造一批数据 ----
    print(f"[1/5] 向服务端写入 {N} 条数据 ...")
    with MiniKVClient(HOST, PORT) as c:
        for i in range(N):
            c.set(f"user:{i}", f"value-{i}")
        n0 = c.size()
    print(f"      当前服务端 size = {n0}")

    # ---- 2) 备份到 MySQL ----
    print("[2/5] 备份到 MySQL ...")
    batch = run_backup(HOST, PORT, db)
    print(f"      备份批次号 = {batch}")

    # ---- 3) 清空服务端（模拟数据丢失）----
    print("[3/5] 清空服务端（模拟数据丢失）...")
    with MiniKVClient(HOST, PORT) as c:
        for k in c.keys():
            c.delete(k)
        assert c.size() == 0, "清空服务端失败"
    print("      服务端已清空")

    # ---- 4) 从 MySQL 恢复 ----
    print("[4/5] 从 MySQL 恢复 ...")
    run_restore(HOST, PORT, db)

    # ---- 5) 校验 ----
    print("[5/5] 校验数据是否完整 ...")
    with MiniKVClient(HOST, PORT) as c:
        n1 = c.size()
        ok = all(c.get(f"user:{i}") == f"value-{i}" for i in range(N))
        assert n1 == n0, f"条数不一致：备份前 {n0}，恢复后 {n1}"
        assert ok, "有数据内容对不上！"
    print(f"端到端测试通过 ✔（{n1} 条数据完整恢复）")


if __name__ == "__main__":
    main()
