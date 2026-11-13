import time,logging
from pathlib import Path
from .config.database import Session
from .utils.queue import client,QUEUE,parse_message
from .services.run_service import compute,recover_pending
heartbeat=Path("/artifacts/worker-heartbeat")
def touch():
 try:heartbeat.touch()
 except OSError:pass
with Session() as db:
 try:recover_pending(db,requeue=True)
 except Exception:logging.exception("Startup recovery failed")
while True:
 touch()
 try:
  item=client().blpop(QUEUE,timeout=2)
  if item:
   parsed=parse_message(item[1])
   if parsed is not None:
    run_id,token=parsed
    with Session() as db:compute(db,run_id,token)
  else:
   # 空转周期巡检：把超过时限仍在running的中断任务转回failed，等待用户重试，不重复入队
   with Session() as db:recover_pending(db,requeue=False)
 except Exception:logging.exception("Worker error");time.sleep(2)
