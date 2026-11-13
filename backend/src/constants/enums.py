from enum import StrEnum
class Role(StrEnum):
 ADMIN="admin"
 ANALYST="analyst"
 VIEWER="viewer"
class RunStatus(StrEnum):
 QUEUED="queued"
 RUNNING="running"
 RETRYING="retrying"
 COMPLETED="completed"
 FAILED="failed"
 CANCELLED="cancelled"
# 运行超过该秒数仍停留在 running，视为worker中断，可恢复重试
STALE_RUN_SECONDS=120
class ModelMode(StrEnum):
 FIT="fit"
 FIXED="fixed"
COORDINATE_SYSTEM="local_meters"
