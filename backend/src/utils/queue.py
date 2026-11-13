import json
from redis import Redis
from ..config.settings import REDIS_URL
QUEUE="spatial-kriging:runs"
def client(): return Redis.from_url(REDIS_URL,decode_responses=True)
def enqueue(run_id,token):
 # 消息携带尝试令牌；迟到的旧令牌结果在worker侧被拒绝，不能覆盖新尝试
 client().rpush(QUEUE,json.dumps({"run_id":run_id,"token":token},ensure_ascii=False))
def parse_message(raw):
 # 兼容旧格式（裸run_id）；无法解析的消息返回None由worker丢弃
 try:
  payload=json.loads(raw)
  if isinstance(payload,dict) and payload.get("run_id"):return str(payload["run_id"]),str(payload.get("token",""))
 except (TypeError,ValueError):pass
 if isinstance(raw,str) and raw:return raw,""
 return None
