# -*- coding: utf-8 -*-
"""
restore.py —— 恢复：把 MySQL 里的快照数据写回 mini_kv_server

流程三步：
    1. 从 MySQL 读指定批次（不指定就读最近一批）的数据
    2. 用 SET 命令逐条写回 C++ 服务端
    3. 因为是全量覆盖写，重复执行结果一样 —— 这就是"幂等"

恢复与备份是对称的：
    备份 = C++ -> Python -> MySQL
    恢复 = MySQL -> Python -> C++

顺便说一句：SET 是覆盖语义，所以恢复前服务端里已有的、但快照里没有的 key
不会被删掉（我们没有做"先清空再恢复"）。简单场景够用，README 里有讨论。
"""

from minikv_client import MiniKVClient
from mysql_store import KVStore


def run_restore(kv_host, kv_port, db, batch_id=None):
    """
    kv_host / kv_port：C++ 服务端地址
    db：KVStore 对象
    batch_id：恢复哪个批次；None = 恢复最近一次备份
    """
    # ---- 第 1 步：从 MySQL 读数据 ----
    with db:
        if batch_id is None:
            batch_id = db.latest_batch_id()
            if batch_id is None:
                print("MySQL 里还没有任何快照，无法恢复")
                return
        pairs = db.load_snapshot(batch_id)
    print(f"[1/3] 从 MySQL 读到 batch_id={batch_id}，共 {len(pairs)} 条")

    # ---- 第 2 步：写回 C++ 服务端 ----
    with MiniKVClient(kv_host, kv_port) as client:
        for k, v in pairs:
            client.set(k, v)

    print(f"[3/3] 恢复完成：已把 {len(pairs)} 条数据写回服务端")
