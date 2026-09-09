# -*- coding: utf-8 -*-
"""
minikv_client.py —— 用 Python 给 C++ 写的 mini_kv_server 当客户端

这个文件解决一个问题：Python 怎么和 C++ 程序通信？
答案：通过网络（TCP/IP），而不是直接调用。

mini_kv_server 是 C++ 写的 TCP 服务端，它监听一个端口（默认 9000）。
我们（Python）用 socket 连上去，然后按它规定的"文本协议"发命令、收回复。
这就是互联网上绝大多数"跨语言通信"的方式：两边只认字节流，不关心对方是什么语言。

-----------------------------------------------------------
协议速查表（对齐 C++ 源码 server.cpp，已核对）：
-----------------------------------------------------------
连接成功后，服务端先发一行欢迎语：
    WELCOME mini_kv_server. Type HELP for commands.

然后一条命令一行（每条都以 \n 结尾）：

    命令              响应
    ----------------  ---------------------------
    PING              PONG
    SET <key> <value> OK
    GET <key>         VALUE <value>    或 NOT_FOUND
    DEL <key>         DELETED          或 NOT_FOUND
    KEYS              KEYS k1 k2 k3 ...（空库时只有 KEYS）
    SIZE              SIZE <n>
    EXIT              BYE（随后服务端关闭连接）
    队列满时服务端可能回 BUSY ...（背压）
-----------------------------------------------------------
"""

import socket


class MiniKVError(Exception):
    """自定义异常：协议对不上时抛出，方便上层捕获处理"""
    pass


class MiniKVClient:
    """mini_kv_server 的 Python 客户端，把"发命令/收回复"封装成普通方法"""

    def __init__(self, host="127.0.0.1", port=9000, timeout=5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock = None
        # pending 缓冲区：处理"半包/粘包"用，见 _recv_line 的注释
        self._pending = bytearray()

    # ---------------- 连接 / 断开 ----------------

    def connect(self):
        """
        建立 TCP 连接，并消费掉服务端发来的 WELCOME 欢迎行。
        socket.create_connection 内部完成了域名解析 + 三次握手。
        """
        self._sock = socket.create_connection(
            (self.host, self.port), timeout=self.timeout)
        welcome = self._recv_line()
        if not welcome.startswith("WELCOME"):
            raise MiniKVError(f"意外的主机名：{welcome!r}")
        return welcome

    def close(self):
        """关闭连接。socket 是系统资源，用完必须关（和你在 C++ 里做的一样）"""
        if self._sock is not None:  # self._sock 不是空指针，socket 对象是存在的。
            try:
                self._sock.close()
            finally:
                self._sock = None

    #`__enter__` / `__exit__` 是专门给`with`上下文管理器准备的两个函数，不是实例化对象自动跑的。
    # 支持 with 写法：with MiniKVClient() as c: ...
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False  # 返回 False = 不吞掉异常，异常照常往上抛

    # ---------------- 核心：按行读取（半包 / 粘包） ----------------

    def _recv_line(self):
        """
        从 socket 读"一行"（直到遇到 \n）。

        为什么这么麻烦？因为 TCP 是【字节流】，不是【消息流】：
          - 半包：一次 recv() 只收到半行，剩下的还在路上 -> 先存进 pending
          - 粘包：一次 recv() 收到好几行 -> 只切出第一行，剩下的留到下次

        这正是你的 C++ 服务端 server.cpp 里 pending 缓冲区在做的事，
        两端处理思路完全一样：先拼缓冲区，找到 \n 才切出一条完整消息。
        """
        while True:
            # 1) 先看缓冲区里有没有完整的一行
            newline = self._pending.find(b"\n")
            if newline != -1:
                line = bytes(self._pending[:newline + 1])
                del self._pending[:newline + 1]      # 消费掉这一行
                return line.decode("utf-8", errors="replace").rstrip("\n")

            # 2) 没有就继续从 socket 读，读到的先塞进缓冲区
            chunk = self._sock.recv(4096)
            if not chunk:
                raise MiniKVError("连接已被服务端关闭")
            self._pending.extend(chunk)

    def _request(self, cmd):
        """发一条命令，并等待返回的一行响应。
        容错：把命令动词统一转成大写再发送，和 C++ 服务端 parse_command()
        里的 to_upper_copy() 行为对齐——这样手写 "set k v" 小写命令也能正常工作。
        响应则保持严格匹配：协议对不上应该立刻报错，而不是猜。"""
        parts = cmd.strip().split(" ", 1)
        verb = parts[0].upper()
        cmd = verb + (" " + parts[1] if len(parts) > 1 else "")
        self._sock.sendall((cmd + "\n").encode("utf-8"))
        return self._recv_line()

    # ---------------- 业务命令 ----------------

    def ping(self):
        return self._request("PING")

    def set(self, key, value):
        resp = self._request(f"SET {key} {value}")
        if resp != "OK":
            raise MiniKVError(f"SET 失败，服务端返回：{resp!r}")
        return True

    def get(self, key):
        resp = self._request(f"GET {key}")
        if resp == "NOT_FOUND":
            return None  # 约定：查不到就返回 None，上层好判断
        if resp.startswith("VALUE "):
            return resp[len("VALUE "):]  # 去掉 "VALUE " 前缀，剩下的就是值
        raise MiniKVError(f"GET 响应无法解析：{resp!r}")

    def delete(self, key):
        resp = self._request(f"DEL {key}")
        return resp == "DELETED"

    def keys(self):
        """返回所有 key 的列表。
        响应格式：KEYS k1 k2 k3（key 之间用空格分隔），空库时只有 KEYS
        """
        resp = self._request("KEYS")
        parts = resp.split(" ")
        return parts[1:] if len(parts) > 1 else []

    def size(self):
        resp = self._request("SIZE")
        # 响应格式：SIZE <n>，取第二个字段转成 int
        return int(resp.split(" ")[1])
