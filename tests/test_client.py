# -*- coding: utf-8 -*-
"""
test_client.py —— 只测 Python 客户端与 C++ 服务端的通信（不需要 MySQL）

前置条件：mini_kv_server 已经在运行，例如（路径换成你本机的实际路径）：
    ../mini_kv_server/build/Release/mini_kv_server.exe --port 9000 --workers 4 --queue 64 --backlog 64

运行（在项目目录下）：
    python tests/test_client.py
"""

import sys
import os

# 让 Python 能找到上级目录里的 minikv_client.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from minikv_client import MiniKVClient


def main():
    with MiniKVClient("127.0.0.1", 9000) as c:
        # 1) 基本命令
        assert c.ping() == "PONG", "PING 测试失败"
        assert c.set("hello", "world") is True, "SET 测试失败"
        assert c.get("hello") == "world", "GET 测试失败"
        assert c.get("不存在的key") is None, "GET 不存在 key 应返回 None"

        # 2) KEYS / SIZE
        assert "hello" in c.keys(), "KEYS 应包含刚写入的 hello"
        assert c.size() >= 1, "SIZE 应 >= 1"

        # 3) DEL
        assert c.delete("hello") is True, "DEL 测试失败"
        assert c.get("hello") is None, "删除后 GET 应返回 None"

        # 4) 删除不存在的 key 返回 False（服务端回 NOT_FOUND）
        assert c.delete("hello") is False, "删除不存在的 key 应返回 False"

        # 5) 大小写容错：手写小写命令一样能用（对应 C++ 端 to_upper_copy）
        assert c._request("ping") == "PONG", "小写 ping 应返回 PONG"
        assert c._request("set casekey value") == "OK", "小写 set 应返回 OK"
        assert c._request("get casekey") == "VALUE value", "小写 get 应返回 VALUE"
        assert c.delete("casekey") is True, "清理 casekey"

    print("test_client 全部通过 ✔（Python <-> C++ TCP 通信正常）")


if __name__ == "__main__":
    main()
