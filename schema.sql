-- ============================================================
-- minikv_backup 数据库初始化脚本
--
-- 怎么执行这个文件（三种方式任选）：
--   1) 命令行：  mysql -u root -p < schema.sql
--      （会提示输入 root 密码；注意 -p 和密码之间不要写空格）
--   2) MySQL Workbench / Navicat：打开本文件 -> 执行整个脚本
--   3) 在 mysql 命令行里逐句粘贴
--
-- 脚本做了三件事：建库 -> 建表 -> 验证
-- ============================================================

-- 1. 创建数据库
--    utf8mb4 支持中文、emoji 等字符；如果只要英文，utf8 也够
CREATE DATABASE IF NOT EXISTS minikv
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE minikv;

-- 2. 创建快照表
--    设计思路：
--      - 每次"备份"生成一个新的 batch_id（批次号），例如第 1 次备份 batch_id=1
--      - 同一批里，每个 key 一行
--      - 联合主键 (batch_id, k)：保证同一批次里同一个 key 不会出现两行
--      - 因此可以保留多个历史快照，想恢复哪个批次就查哪个批次
CREATE TABLE IF NOT EXISTS kv_snapshot (
  batch_id   BIGINT       NOT NULL COMMENT '快照批次号（每次备份 +1）',
  k          VARCHAR(255) NOT NULL COMMENT 'key',
  v          TEXT         NULL     COMMENT 'value',
  updated_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '写入时间',
  PRIMARY KEY (batch_id, k),
  KEY idx_batch (batch_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = 'mini_kv_server 全量快照表';

-- 3. 验证：应该能查到刚创建的 kv_snapshot 表
SHOW TABLES;
