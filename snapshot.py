# -*- coding: utf-8 -*-
"""
snapshot.py —— 备份：把 mini_kv_server 里的数据全量备份到 MySQL

一条流水线，三步：
    1. 连上 C++ 服务端（MiniKVClient）
    2. KEYS 拿到所有 key，再 GET 逐个取值（这就是"全量快照"）
    3. 把 (key, value) 列表批量写进 MySQL（KVStore.create_snapshot）

注意：这个"快照"不是原子操作（备份过程中服务端可能还在被写入），
但作为备份工具已经足够——这也是面试可以聊的点（见 README）。
"""

from minikv_client import MiniKVClient
from mysql_store import KVStore


def run_backup(kv_host, kv_port, db):
    """
    kv_host / kv_port：C++ 服务端地址
    db：一个已经创建好的 KVStore 对象（连接信息在里面）
    返回本次备份的 batch_id
    """
    # ---- 第 1、2 步：从 C++ 服务端读全量数据 ----
    with MiniKVClient(kv_host, kv_port) as client:
        keys = client.keys()
        print(f"[1/3] 服务端当前有 {len(keys)} 个 key")

        pairs = []
        for i, k in enumerate(keys, 1):
            v = client.get(k)
            # GET 返回 None 说明 key 在 KEYS 之后被删了，跳过它即可
            if v is not None:
                pairs.append((k, v))
            if i % 1000 == 0:
                print(f"      已读取 {i} 个 key ...")

    # ---- 第 3 步：写入 MySQL ----
    with db:
        batch_id = db.create_snapshot(pairs)

    print(f"[3/3] 备份完成：batch_id = {batch_id}，共 {len(pairs)} 条")
    return batch_id
