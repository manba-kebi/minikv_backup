# minikv\_backup —— 给 MiniKV Server 的 Python + MySQL 备份 / 恢复组件

![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB) ![License](https://img.shields.io/badge/License-MIT-green) ![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1)

一个**教程性质**的小项目：用 Python 把 C++ 写的 [mini\_kv\_server](https://github.com/manba-kebi/mini_kv_server) 的数据全量备份到 MySQL，
再支持从 MySQL 恢复回服务端。项目体量轻量，但把三个技术点串成了一条线：

```
C++（mini_kv_server 管内存热数据）
        ↓ TCP 文本协议
Python（本项目的备份/恢复逻辑）
        ↓ pymysql
MySQL（存结构化历史快照）
```

**做完这个项目你能学到三件事：**

1. Python 怎么连 MySQL（pymysql：连接、游标、批量写、事务）
2. Python 怎么连 C++ 程序（TCP socket + 文本协议 + 半包粘包处理）
3. 一个 "备份 / 恢复" 工具是怎么设计出来的（批次号、幂等、事务）

**为什么做这个项目（动机）：**
**MiniKV Server 的 Windows 版（线程池版）没有 AOF 持久化，数据只存在内存里，服务端一关就全丢了。**
这个项目给 Windows 端补上 "服务端关闭后数据可恢复" 的能力；并且快照做成**带批次号的历史版本**——
**不只是恢复，还能用 SQL 查询任意批次、回滚到任意时间点。**同时它本身是一次 Python + MySQL 的实际工程练习：
把 C++ 管内存热读写、Python 管持久化恢复、MySQL 管结构化存储串成一个完整小系统。

***

## 快速开始（30 秒）

```
# 1. 装依赖
pip install -r requirements.txt
# 2. 建库建表（在本项目目录下执行；PowerShell 用户见 2.2 节）
mysql -u root -p < schema.sql
# 3. 启动 mini_kv_server 后，备份一次
python main.py backup --db-password 你的密码
# 4. 恢复最近一次备份
python main.py restore --db-password 你的密码
```

> 环境要求：Python 3.8+・pymysql・MySQL 8.0・一个正在运行的
> [mini_kv_server](https://github.com/manba-kebi/mini_kv_server)
> （本项目的备份对象，需先自行启动）

***

## 目录

1. [项目结构](#一项目结构)
2. [环境准备（Anaconda + PyCharm + MySQL）](#二环境准备)
3. [第一课：Python 怎么连 MySQL](#三第一课python-怎么连-mysql)
4. [第二课：Python 怎么连 C++](#四第二课python-怎么连-c)
5. [第三课：逐文件讲解](#五第三课逐文件讲解)
6. [完整运行流程（端到端）](#六完整运行流程端到端)
7. [面试可以聊的点](#七面试可以聊的点)
8. [常见问题 FAQ](#八常见问题-faq)

***

## 一、项目结构

```
minikv_backup/
├── requirements.txt        # 依赖清单（目前只有 pymysql）
├── schema.sql              # 建库建表脚本（先在 MySQL 里执行一次）
├── minikv_client.py        # Python 客户端：和 C++ 服务端通信（TCP 文本协议）
├── mysql_store.py          # MySQL 存储层：备份数据的读写（pymysql）
├── snapshot.py             # 备份逻辑：服务端 -> Python -> MySQL
├── restore.py              # 恢复逻辑：MySQL -> Python -> 服务端
├── main.py                 # 命令行入口：backup / restore / prune
├── examples/               # 两个热身小例子（建议先跑这两个）
│   ├── step1_mysql.py      #   Python 连 MySQL 的最小代码
│   └── step2_cpp.py        #   Python 连 C++ 服务端的最小代码
└── tests/
    ├── test_client.py      # 只测 Python <-> C++ 通信（不需要 MySQL）
    └── test_e2e.py         # 端到端：备份 -> 清空 -> 恢复 -> 校验（需要 MySQL）
```

模块之间的依赖方向（从下往上看）：
`main.py -> snapshot.py / restore.py -> minikv_client.py + mysql_store.py`

***

## 二、环境准备

### 2.1 Python 环境（推荐 Anaconda + PyCharm）

1. 用 PyCharm 打开本项目文件夹。
2. 配置解释器：`File -> Settings -> Project -> Python Interpreter`，选择你本机 Anaconda 自带的 Python（Python 3.8+ 均可，推荐 3.12）。
3. 安装唯一依赖 pymysql。打开 Anaconda Prompt 或 PyCharm 的 Terminal：

```
pip install pymysql
```

> 也可以先建一个独立环境（更规范）：

```
conda create -n minikv_backup python=3.12 -y
conda activate minikv_backup
pip install pymysql
```

### 2.2 MySQL（需自行安装并启动，推荐 8.0 及以上）

1. 确认 MySQL 在运行：`netstat -ano | findstr :3306`，能看到 LISTENING 就是正常的。
2. **建库建表**：在命令行执行（会提示输入你的 root 密码）：

```
mysql -u root -p < schema.sql
```

> ⚠️ 
> **PowerShell 用户注意**
> ：上面这条在 Windows PowerShell 里会报错或中文乱码，
> 因为 PowerShell 的 
> `<`
>  重定向和文件编码和 cmd 不一样。PowerShell 里请用：

```
mysql --default-character-set=utf8mb4 -u root -p -e "source 你的项目绝对路径/schema.sql"
```

> 或者干脆用 Navicat / MySQL Workbench 打开 
> `schema.sql`
>  执行整个脚本，最省事。
> 执行完应该看到输出里有 
> `kv_snapshot`
>  这张表。

3. **建议建一个专用账号**（别让代码里写死 root 密码，安全习惯）：

```
-- 用 root 登录后执行；把 '你的密码' 换成你想设的
CREATE USER 'minikv'@'localhost' IDENTIFIED BY '你的密码';
GRANT ALL PRIVILEGES ON minikv.* TO 'minikv'@'localhost';
FLUSH PRIVILEGES;
```

之后运行项目时用 `--db-user minikv --db-password 你的密码` 即可。

***

## 三、第一课：Python 怎么连 MySQL

### 3.1 为什么需要 pymysql

Python 标准库里**没有**连 MySQL 的模块，需要装第三方驱动。`pymysql` 是其中最
简单的一种：纯 Python 实现、pip 一行装上、用法直观，适合学习。
（实际生产里也有人用 `mysqlclient`/`MySQLdb`，本质差不多。）

### 3.2 连接的四个要素

任何数据库连接，本质上都是回答四个问题：

| 参数       | 含义          | 例子                |
| -------- | ----------- | ----------------- |
| host     | MySQL 在哪台机器 | `127.0.0.1`（本机）   |
| port     | 端口          | `3306`            |
| user     | 账号          | `root` 或 `minikv` |
| password | 密码          | 你安装时设的            |

`database`（库名）是第五个常用参数，告诉 MySQL "我这次要用哪个库"。

### 3.3 最小可用代码

先运行 `examples/step1_mysql.py`（记得把密码改成自己的）：

```
import pymysql
conn = pymysql.connect(
    host="127.0.0.1", port=3306,
    user="root", password="你的密码",
    charset="utf8mb4",
)
cursor = conn.cursor()              # 游标：执行 SQL 的"笔"
cursor.execute("SELECT VERSION()")  # 执行 SQL
row = cursor.fetchone()             # 取第一行结果
print("MySQL 版本：", row[0])
cursor.close()
conn.close()
```

核心就四行：`connect` -> `cursor()` -> `execute()` -> `fetchone()`。

### 3.4 游标、execute 和 fetch

* `conn.cursor()`：创建一个游标。一个连接可以开多个游标，用完各自 `close()`。
* `cursor.execute(sql)`：执行 SQL，结果先存在游标里。
* `cursor.fetchone()`：取一行，返回元组（tuple），如 `('8.0.45',)`。
* `cursor.fetchall()`：取所有行，返回 `[(行1), (行2), ...]`。

### 3.5 参数化查询（防止 SQL 注入，必学）

写 SQL 时**永远不要用字符串拼接**把数据拼进去：

```
# ❌ 错误：如果 key 是 "x'; DROP TABLE kv_snapshot; --" 就完蛋了
cursor.execute(f"SELECT * FROM kv_snapshot WHERE k = '{key}'")
# ✅ 正确：用 %s 占位，数据单独传参，pymysql 帮你转义
cursor.execute("SELECT * FROM kv_snapshot WHERE k = %s", (key,))
```

### 3.6 批量写入 executemany

一条一条 `execute` 慢，批量用 `executemany`：一条 SQL 传一个 "数据列表"，
驱动会复用这条 SQL 执行 N 次（网络往返从 N 次变成 1 次）。

```
data = [(1, "a", "v1"), (1, "b", "v2")]          # [(batch_id, k, v), ...]
cursor.executemany(
    "INSERT INTO kv_snapshot (batch_id, k, v) VALUES (%s, %s, %s)",
    data,
)
```

### 3.7 事务：commit 和 rollback（重点）

pymysql 默认 `autocommit=False`，意思是：你 `execute` 的修改**先不算数**，
要 `conn.commit()` 才真正写进磁盘。这背后是 MySQL 的**事务**：

* `commit()`：确认，把这一批操作一次性落库；
* `rollback()`：反悔，撤销这一批操作，数据回到事务开始前的样子。

好处：要么全成功，要么全失败，不会出现 "插了 50 条，第 51 条失败，留下 50 条半截数据"。
本项目 `mysql_store.py` 里 `create_snapshot` 就是这么写的：

```
try:
    cursor.executemany(sql, data)
    self.conn.commit()     # 全部成功 -> 提交
except Exception:
    self.conn.rollback()   # 出任何错 -> 整体回滚
    raise
```

### 3.8 常见报错对照

| 报错                                             | 原因                 | 解决                                 |
| ---------------------------------------------- | ------------------ | ---------------------------------- |
| `Access denied for user 'root'@'localhost'`    | 密码不对（或该账号没权限）      | 检查密码 / 建专用账号                       |
| `Unknown database 'minikv'`                    | 还没执行 schema.sql    | 先执行建库脚本                            |
| `Can't connect to MySQL server on ... (10061)` | MySQL 没启动 / 端口不对   | 启动 MySQL，检查 3306                   |
| `cryptography package is not installed`        | MySQL 8 的认证插件需要加密库 | `pip install cryptography`（如果遇到再装） |

***

## 四、第二课：Python 怎么连 C++

### 4.1 为什么用 TCP，而不是 "直接调用"

mini\_kv\_server 是 C++ 写的独立进程，Python 是另一个进程。不同进程、不同语言，
不能互相 "调用函数"—— 唯一的通用桥梁就是**网络**。两边约定好：

* 谁先监听（服务端 listen）；
* 用什么协议（本项目的 "单行文本协议"）；
* 数据怎么切分（按 `\n` 换行符）。

这和你 C++ 项目里学的 TCP 完全是一套东西，只是这次客户端换成 Python 写。

### 4.2 协议速查表（已对照 C++ 源码核对）

连接成功，服务端先发一行 `WELCOME mini_kv_server. Type HELP for commands.`，
然后每发一条命令（以 `\n` 结尾），服务端回一行：

| 命令        | 响应                      | 说明                   |
| --------- | ----------------------- | -------------------- |
| `PING`    | `PONG`                  | 探活                   |
| `SET k v` | `OK`                    | 写入                   |
| `GET k`   | `VALUE v` 或 `NOT_FOUND` | 读取                   |
| `DEL k`   | `DELETED` 或 `NOT_FOUND` | 删除                   |
| `KEYS`    | `KEYS k1 k2 k3`         | 列所有 key（空库只有 `KEYS`） |
| `SIZE`    | `SIZE 42`               | 条数                   |
| `EXIT`    | `BYE` 然后断开              | 退出                   |



### 4.3 最小可用代码

先运行 `examples/step2_cpp.py`（前提：服务端已启动）：

```
import socket
sock = socket.create_connection(("127.0.0.1", 9000), timeout=5)
print("欢迎语：", sock.recv(1024).decode().strip())
def ask(cmd):
    sock.sendall((cmd + "\n").encode("utf-8"))
    return sock.recv(1024).decode().strip()
print("PING ->", ask("PING"))
print("SET  ->", ask("SET hello world"))
print("GET  ->", ask("GET hello"))
sock.close()
```

输出：

```
欢迎语： WELCOME mini_kv_server. Type HELP for commands.
PING -> PONG
SET  -> OK
GET  -> VALUE world
```

### 4.4 半包和粘包（最关键的一课）

`socket.recv()` 一次能读多少，**不由你决定**，由网络决定。所以：

* **半包**：你发了 `GET abc\n`，但 recv 一次只收到 `GET a`，剩下 `bc\n` 还在路上；
* **粘包**：你连发两条命令，一次 recv 可能收到 `PONG\nOK\n` 两行粘在一起。

所以读数据不能 "recv 一次就当一条消息"，要**攒进缓冲区，找到 **`\n`** 才切一条**。
这正是你 C++ 服务端 `server.cpp` 里 `pending` 缓冲区做的事。
Python 端 `minikv_client.py` 的 `_recv_line()` 是同一套思路：

```
def _recv_line(self):
    while True:
        newline = self._pending.find(b"\n")      # 1) 缓冲区里有完整行吗？
        if newline != -1:
            line = bytes(self._pending[:newline + 1])
            del self._pending[:newline + 1]      #    有 -> 切出来，剩下的留着
            return line.decode("utf-8").rstrip("\n")
        chunk = self._sock.recv(4096)            # 2) 没有 -> 继续读，先攒着
        if not chunk:
            raise MiniKVError("连接已被服务端关闭")
        self._pending.extend(chunk)
```

**同样的坑、同样的解法，C++ 和 Python 各写一遍**—— 这就是面试官想听的故事。

### 4.5 用 telnet 手动验证协议

服务端开着时，Windows 上可以用 telnet 当 "人肉客户端"：

```
telnet 127.0.0.1 9000
```

输入 `PING` 回车，看到 `PONG`，协议就通了。这也说明文本协议的优点：好调试。

***

## 五、第三课：逐文件讲解

### 5.1 `minikv_client.py` —— Python 与 C++ 的桥

把 "发命令 / 收回复" 封装成 `MiniKVClient` 类，上层只调用 `set()/get()/keys()`。
重点看两个方法：

* `_recv_line()`：上面讲过的半包粘包处理；
* `get()`：把 `NOT_FOUND` 翻译成 Python 的 `None`，调用方判断 "没查到" 就很自然。

```
def get(self, key):
    resp = self._request(f"GET {key}")
    if resp == "NOT_FOUND":
        return None
    if resp.startswith("VALUE "):
        return resp[len("VALUE "):]   # 去掉前缀，剩下的就是值
    raise MiniKVError(f"GET 响应无法解析：{resp!r}")
```

### 5.2 `mysql_store.py` —— Python 与 MySQL 的桥

`KVStore` 类只管数据库读写，不关心网络协议。三个核心方法：

* `create_snapshot(pairs)`：算新批次号 -> executemany 批量插 -> commit。
* `load_snapshot(batch_id)`：按批次号查回所有 `(k, v)`。
* `prune(keep)`：只留最近 N 个批次，删旧的（防止快照无限增长）。

### 5.3 `snapshot.py` 与 `restore.py` —— 业务流水线

```
备份：MiniKVClient.keys() -> GET 逐个取值 -> KVStore.create_snapshot()
恢复：KVStore.load_snapshot() -> MiniKVClient.set() 逐条写回
```

`set()` 是覆盖语义，重复恢复结果一样，所以恢复是**幂等**的。

### 5.4 `main.py` —— 命令行入口

用标准库 `argparse` 做子命令：

```
python main.py backup                  # 备份一次
python main.py backup --interval 60    # 每 60 秒备份一次（Ctrl+C 停）
python main.py restore                 # 恢复最近一次备份
python main.py restore --batch 3       # 恢复第 3 个批次
python main.py prune --keep 5          # 只保留最近 5 个批次
```

所有参数都有默认值；密码等按实际情况追加，例如：
`python main.py backup --db-user minikv --db-password 你的密码`

***

### 5.5 三个功能语义速查

| 命令                    | 做什么                         | 关键语义                                                      |
| --------------------- | --------------------------- | --------------------------------------------------------- |
| `backup`              | 服务端全量数据 → 写入 MySQL **新批次**  | batch\_id = 现存最大批次 + 1；旧批次不清空、不覆盖（只有同一批内 key 重复时才更新该行，幂等） |
| `restore [--batch N]` | MySQL 指定批次（默认最新）→ SET 回写服务端 | 逐条覆盖写，幂等；不删除服务端上 "快照里没有的 key"                             |
| `prune --keep N`      | 删除旧批次，只保留最近 N 批             | 被删的批次编号不回退；下一次 backup 仍是 最大批次 + 1                         |

***

## 六、完整运行流程（端到端）

按顺序做一遍，你会完整看到 "备份 -> 丢数据 -> 恢复" 的全过程。
**第 0 步**：MySQL 已建好库（执行过 schema.sql）。检查：

```
mysql -u root -p -e "USE minikv; SHOW TABLES;"
```

**第 1 步**：启动 C++ 服务端（新开一个终端；把路径换成你本机 mini\_kv\_server 的实际路径，
下面假设 mini\_kv\_server 与本项目克隆在相邻目录）：

```
../mini_kv_server/build/Release/mini_kv_server.exe --port 9000 --workers 4 --queue 64 --backlog 64
```

**第 2 步**：写入一些测试数据（新开一个终端，用我们自己的客户端）：

```
python -c "from minikv_client import MiniKVClient; c=MiniKVClient(); c.connect(); [c.set(f'user:{i}', f'value-{i}') for i in range(20)]; print('size =', c.size()); c.close()"
```

**第 3 步**：备份到 MySQL：

```
python main.py backup --db-password 你的密码
```

看到 `备份完成：batch_id = 1，共 20 条` 就成功了。
可以进 MySQL 看一眼数据：

```
mysql -u root -p -e "USE minikv; SELECT * FROM kv_snapshot LIMIT 5;"
```

**第 4 步**：模拟数据丢失（直接 Ctrl+C 关掉服务端再重启，Windows 版没有 AOF，
重启后数据就没了；或者用 `DEL` 清空）：

```
python -c "from minikv_client import MiniKVClient; c=MiniKVClient(); c.connect(); [c.delete(k) for k in c.keys()]; print('size =', c.size()); c.close()"
```

**第 5 步**：从 MySQL 恢复：

```
python main.py restore --db-password 你的密码
```

**第 6 步**：校验：

```
python -c "from minikv_client import MiniKVClient; c=MiniKVClient(); c.connect(); print('size =', c.size(), '| user:0 =', c.get('user:0')); c.close()"
```

数据回来了，项目就跑通了。
**一键自测**：`tests/test_e2e.py` 把这六步自动跑一遍：

```
python tests/test_e2e.py --db-password 你的密码
```

***

## 七、面试可以聊的点

1. **AOF 和 MySQL 快照是什么关系？谁更强？**

   不是谁更强，而是**解决不同问题**，两者互补：

| 维度   | AOF（C++ 服务端自带）            | MySQL 快照（本项目）              |
| ---- | ------------------------- | -------------------------- |
| 定位   | 崩溃恢复：进程重启自动回放             | 历史快照：可查询、可回滚、可分析           |
| 实时性  | 每次写操作即时追加                 | 定时 / 手动触发，有间隔              |
| 数据形态 | 追加日志文件（机器可读，人不直观）         | 结构化表（SQL 查询 / 聚合 / 报表）     |
| 恢复粒度 | 恢复到最近一次写入的状态              | 恢复到任意批次的时间点                |
| 谁负责  | 服务端内部（append\_only\_file） | Python 外部组件（本项目）           |
| 平台   | 仅 Linux Epoll 版           | 全平台；Windows 版没有 AOF，正好由它补位 |

一句话：**AOF 保证 "崩溃后马上恢复到最新"，快照保证 "任意历史时间点可查可回滚"**。
如果被追问 "快照能不能替代 AOF"—— 不能：快照有触发间隔，崩溃会丢间隔内的写入，
实时恢复仍需日志类机制；两者是并存关系。

2. **快照不是原子的**：备份过程中服务端可能还在写入，KEYS 之后新 SET 的 key
   这次备份里没有。可以怎么改进？（服务端加一个 "只读 dump" 命令 / 或先做一致性标记。）
3. **幂等恢复**：SET 是覆盖写，重复执行恢复结果不变，这是运维友好的重要性质。
4. **批量写 vs 单条写**：executemany 一次网络往返写 N 条，数据量大时差距明显。
5. **半包粘包**：C++ 端和 Python 端用同一套 "缓冲 + 找分隔符" 的思路，
   说明你理解 TCP 是字节流而不是消息流。
6. **事务**：写库要么全成要么全不成，commit/rollback 保证不留半截数据。

***

## 八、常见问题 FAQ

**Q1：pymysql 连不上，报 Access denied？**

密码不对，或者还没建专用账号。先用 root 在命令行确认密码能登录。

**Q2：`Unknown database 'minikv'`？**

没执行 schema.sql，先建库建表。

**Q3：`Can't connect to MySQL server ... (10061)`？**

MySQL 服务没启动。Windows 服务里找到 MySQL80 启动它，或 `net start MySQL80`。

**Q4：连接 MySQL 报 `cryptography package is not installed`？**

MySQL 8 默认认证插件需要加密库，`pip install cryptography` 即可。

**Q5：value 里能存空格吗？**

能。GET 的响应是 `VALUE 后面的全部内容`，所以带空格也能存能读。
但 **key 不能带空格**（KEYS 用空格分隔 key 列表），这是服务端协议的限制。

**Q6：备份时服务端还在写入，会丢数据吗？**

理论上这次快照会漏掉 "备份过程中新写入的 key"。这是快照的一致性边界，
面试时可以主动说出来，并给出改进方向（见第七节第 2 点）。

**Q7：为什么推荐专用账号而不是 root？**

安全习惯：代码里不出现高权限账号；权限最小化，即使泄露也只影响 minikv 库。

**Q8：执行 schema.sql 报 `ERROR 1064 ... syntax error`，或中文变成乱码？**

十有八九是 PowerShell 管道 / 重定向把 UTF-8 文件搞坏了（中文注释的字节被转成 GBK 时可能夹带出引号字符）。
解决办法见 2.2 节：用 `mysql -e "source 路径"`，或直接用 Navicat / MySQL Workbench 执行脚本。

**Q9：Windows 和 Linux 上，这个项目的价值一样吗？**

不一样。MiniKV Server 的 Windows 版（线程池版）没有 AOF 持久化，服务端一关数据就丢，
所以本项目在 Windows 上是恢复数据的 "主力手段"，价值最大；Linux Epoll 版自带 AOF 崩溃恢复，
本项目则侧重 "历史快照 + SQL 查询 + 回滚任意批次"。两者互补，不是替代（详见第七节第 1 点）。