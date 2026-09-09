# -*- coding: utf-8 -*-
"""
mysql_store.py —— Python 怎么连 MySQL（用 pymysql）

先记住整个流程，只有四步：
    1. 用 pymysql.connect(...) 建立连接，得到一个 conn
    2. 用 conn.cursor() 拿到"游标"cursor（可以理解成执行 SQL 的句柄）
    3. 用 cursor.execute(sql, 参数) 执行 SQL
    4. 改数据的操作，最后必须 conn.commit() 提交，事务才真正落库

为什么有第 4 步？因为 pymysql 默认 autocommit=False，
MySQL 的 InnoDB 引擎有"事务"概念：你做的修改先在一个事务里，
commit() = 确认生效；rollback() = 反悔、全部撤销。
这保证了数据不会写到一半留下半截（要么全成功，要么全失败）。

本模块把"备份/恢复"用到的数据库操作封装成 KVStore 类：
  - create_snapshot(pairs)  写入一批数据，自动生成新批次号
  - latest_batch_id()       查最近一次备份的批次号
  - load_snapshot(batch_id) 按批次读回数据
  - prune(keep)             只保留最近 keep 个批次（清理历史）
"""

import pymysql


class KVStore:
    """MySQL 存储层：只关心"数据怎么存进 MySQL / 怎么从 MySQL 读出"，
    不关心 mini_kv_server 的网络协议（那是 minikv_client.py 的事）。"""

    def __init__(self, host="127.0.0.1", port=3306, user="root",
                 password="123456", database="minikv"):
        # 连接四要素 + 两个常用参数，都存进 dict，connect 时一次性传入
        self.config = dict(
            host=host,          # MySQL 所在机器 IP（本机就是 127.0.0.1）
            port=port,          # MySQL 默认端口 3306
            user=user,          # 用户名（建议用专用账号，别用 root 跑业务）
            password=password,  # 密码
            database=database,  # 要用的库名（schema.sql 里建好的 minikv）
            charset="utf8mb4",  # 字符集，和建库时保持一致
            autocommit=False,   # 关掉自动提交，手动控制事务（教学重点）
        )
        self.conn = None

    # ---------------- 连接管理 ----------------

    def connect(self):
        """真正建立连接。pymysql.connect 失败会抛异常，
        常见原因：MySQL 没启动 / 密码错（Access denied）/ 库不存在（Unknown database）"""
        self.conn = pymysql.connect(**self.config)
        return self.conn

    def _cursor(self):
        """拿到一个可用的游标：没连接就先连接。
        注意：conn.open 表示连接还活着；连接断开会自动重连。"""
        if self.conn is None or not self.conn.open:
            self.connect()
        return self.conn.cursor()

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    # ---------------- 写：批量插入一张快照 ----------------

    def create_snapshot(self, pairs):
        """
        把 [(key, value), ...] 写进 MySQL，作为"第 N 个批次"的快照。
        返回本次生成的 batch_id。

        实现三步：
          1) SELECT MAX(batch_id) 看现在到第几批了，+1 就是新批次号
          2) executemany 批量插入（比 for 循环 execute 快很多）
          3) commit 提交事务
        """
        cursor = self._cursor()
        try:
            # 第 1 步：算新批次号
            cursor.execute("SELECT COALESCE(MAX(batch_id), 0) FROM kv_snapshot")
            # COALESCE：如果表是空的，MAX 是 NULL，用 0 兜底
            batch_id = cursor.fetchone()[0] + 1

            # 第 2 步：批量插入
            #   - %s 是占位符，数据通过第二个参数传进去，
            #     pymysql 会帮我们转义，避免 SQL 注入（千万别用字符串拼接）
            #   - ON DUPLICATE KEY UPDATE：如果同一批次里 key 重复了，
            #     就更新而不是报错（幂等，重复执行也不出错）
            sql = (
                "INSERT INTO kv_snapshot (batch_id, k, v) "
                "VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE v = VALUES(v)"
            )
            data = [(batch_id, k, v) for k, v in pairs]
            cursor.executemany(sql, data)

            # 第 3 步：提交。不 commit 的话，进程退出数据就丢了！
            self.conn.commit()
            return batch_id
        except Exception:
            # 任何一步出错：整体回滚，不留半截数据
            self.conn.rollback()
            raise
        finally:
            cursor.close()  # 游标也要记得关（和 C++ 里 RAII 一个道理）

    # ---------------- 读 ----------------

    def latest_batch_id(self):
        """查最近的批次号；一张快照都没有时返回 None"""
        cursor = self._cursor()
        try:
            cursor.execute("SELECT MAX(batch_id) FROM kv_snapshot")
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            cursor.close()

    def load_snapshot(self, batch_id):
        """按批次读回 [(key, value), ...]。
        ORDER BY k 让顺序稳定，方便对比和调试"""
        cursor = self._cursor()
        try:
            cursor.execute(
                "SELECT k, v FROM kv_snapshot WHERE batch_id = %s ORDER BY k",
                (batch_id,))
            return list(cursor.fetchall())  # fetchall 返回 [(k, v), ...]
        finally:
            cursor.close()

    def prune(self, keep=10):
        """
        只保留最近 keep 个批次，删掉更老的。
        返回被删除的行数。
        （MySQL 不允许 DELETE 直接引用同一张表的子查询，
         所以先包一层派生表，这是 MySQL 的固定写法）
        """
        cursor = self._cursor()
        try:
            cursor.execute(
                "DELETE FROM kv_snapshot WHERE batch_id NOT IN ("
                "  SELECT batch_id FROM ("
                "    SELECT DISTINCT batch_id FROM kv_snapshot"
                "    ORDER BY batch_id DESC LIMIT %s"
                "  ) t"
                ")",
                (keep,))
            self.conn.commit()
            return cursor.rowcount
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cursor.close()
