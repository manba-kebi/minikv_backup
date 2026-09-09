# -*- coding: utf-8 -*-
"""
step1_mysql.py —— 热身示例①：Python 连 MySQL（最短代码）

先把这个跑通，再去看完整的 mysql_store.py。

运行前：
    1. MySQL 服务已启动（未启动请先启动 MySQL 服务）
    2. 把下面 password 改成你自己的 MySQL 密码
    3. 执行：python examples/step1_mysql.py

它会做三件事：连接 -> 查版本 -> 断开。就这三行核心逻辑。
"""

import pymysql

# 1) 建立连接：四个要素 = 地址 + 端口 + 账号 + 密码
#    不指定 database 也行，先连上服务器再说
conn = pymysql.connect(
    host="127.0.0.1",   # MySQL 在哪台机器上（本机）
    port=3306,          # MySQL 默认端口
    user="root",        # 用户名
    password="124563987qazw",  # 改成你自己的
    charset="utf8mb4",  # 字符集
)

# 2) 拿游标（cursor）：可以理解成"执行 SQL 的笔"
cursor = conn.cursor()

# 3) 执行 SQL 并取结果
cursor.execute("SELECT VERSION()")
row = cursor.fetchone()          # fetchone 取第一行
print("MySQL 版本：", row[0])

# 4) 收尾：关游标、关连接（和 C++ 关文件/关 socket 一个道理）
cursor.close()
conn.close()
print("连接测试通过 ✔")
