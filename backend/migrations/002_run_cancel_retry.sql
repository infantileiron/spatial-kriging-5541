-- 运行任务取消/重试能力：新增尝试序号、尝试令牌、历次失败留档与排队/开始/结束时间。
-- 新数据库由 SQLAlchemy metadata 直接建表；已有数据库执行本迁移补齐列。
ALTER TABLE runs
 ADD COLUMN attempt INTEGER NOT NULL DEFAULT 1,
 ADD COLUMN active_token VARCHAR(36) NOT NULL DEFAULT '',
 ADD COLUMN attempts_history JSON NULL,
 ADD COLUMN queued_at DATETIME NULL,
 ADD COLUMN started_at DATETIME NULL,
 ADD COLUMN finished_at DATETIME NULL;
-- 历史在途任务补一个令牌，使其仍可被worker按消息令牌认领。
UPDATE runs SET active_token = UUID() WHERE status IN ('queued','running') AND active_token = '';
-- status 为应用层枚举（VARCHAR），新增 cancelled / retrying 无需变更列定义。
