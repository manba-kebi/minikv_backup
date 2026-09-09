# -*- coding: utf-8 -*-
"""
step2_cpp.py —— 热身示例②：Python 连 C++ 的 mini_kv_server（最短代码）

先把这个跑通，再去看完整的 minikv_client.py。

运行前：
    1. mini_kv_server 已启动（在另一个终端；路径换成你本机的实际路径，下面假设与本项目相邻）：
       ../mini_kv_server/build/Release/mini_kv_server.exe --port 9000 --workers 4 --queue 64 --backlog 64
    2. 执行：python examples/step2_cpp.py

和 step1 对比你会发现：连 MySQL 用 pymysql 封装好的 connect，
连 C++ 服务端用的是 Python 标准库 socket —— 因为对方是"我们自己定义的
TCP 文本协议"，没有现成驱动，协议就得自己按文档写。
"""

import socket

# 1) 建立 TCP 连接（这就是一次"三次握手"）
sock = socket.create_connection(("127.0.0.1", 9000), timeout=5)

# 2) 服务端连上后先发一行欢迎语，读出来看看
welcome = sock.recv(1024).decode("utf-8").strip()
print("欢迎语：", welcome)

# 3) 发命令：注意每条命令末尾要带 \n（服务端按行切分）
def ask(cmd):
    sock.sendall((cmd + "\n").encode("utf-8"))
    return sock.recv(1024).decode("utf-8").strip()

print("PING  ->", ask("PING"))
print("SET   ->", ask("SET hello world"))
print("GET   ->", ask("GET hello"))

# 4) 断开（这里直接关 socket，服务端会感知到连接关闭）
sock.close()
print("连接测试通过 ✔")
