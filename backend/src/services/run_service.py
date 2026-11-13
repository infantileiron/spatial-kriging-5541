import json,hashlib
from datetime import timedelta
from uuid import uuid4
import numpy as np
from sqlalchemy import select,update,delete
from fastapi import HTTPException
from ..models.run import KrigingRun
from ..models.study import KrigingStudy
from ..models.dataset import SpatialDataset
from ..models.spec import VariogramSpec
from ..models.sampling_point import SamplingPoint
from ..models.query_point import QueryPoint
from ..models.prediction import Prediction
from ..models.kriging_weight import KrigingWeight
from ..models.variogram_bin import VariogramBin
from ..models.curve_point import CurvePoint
from ..constants.enums import STALE_RUN_SECONDS
from ..models.common import now
from ..utils.queue import enqueue
from .variogram import empirical_variogram,fit_exponential,semivariance
from .ordinary_kriging import ordinary_kriging
SPEC_FIELDS=["mode","n_bins","min_pairs","max_distance","nugget","fixed_sill","fixed_range","sill_min","sill_max","range_min","range_max","condition_limit","negative_tolerance"]
ACTIVE=("queued","running","retrying")
CHILD_TABLES=(VariogramBin,CurvePoint,Prediction)

def _history(row,outcome,reason):
 history=list(row.attempts_history or [])
 history.append({"attempt":row.attempt,"status":outcome,"reason":reason or "","at":now().isoformat()+"Z"})
 return history

def _active_for_study(db,study_id):
 return db.scalar(select(KrigingRun).where(KrigingRun.study_id==study_id,KrigingRun.status.in_(ACTIVE)).order_by(KrigingRun.created_at.desc()))

def _dispatch(db,row):
 # 沿用原输入：研究/采样/口径均不改变，仅递增尝试序号并更换令牌，旧消息从此失效
 row.attempt=(row.attempt or 0)+1
 row.active_token=str(uuid4())
 row.status="retrying" if row.attempt>1 else "queued"
 row.error=""
 row.result={}
 row.queued_at=now();row.started_at=None;row.finished_at=None
 row.model_sill=None;row.model_range=None;row.model_nugget=None;row.system_condition=None
 db.commit()
 try:enqueue(row.id,row.active_token)
 except Exception:
  row.status="failed";row.error="Redis队列不可用，请稍后重试";row.finished_at=now()
  row.attempts_history=_history(row,"failed",row.error);db.commit()
  raise HTTPException(503,row.error)
 return row

def create(db,body):
 if not db.get(KrigingStudy,body.study_id):raise HTTPException(422,"空间推断研究不存在")
 # 重复点击/重复投递：同一研究已有排队或计算中的任务时直接返回该任务，不重复产生结果
 existing=_active_for_study(db,body.study_id)
 if existing is not None:return existing
 row=KrigingRun(id=str(uuid4()),study_id=body.study_id,status="queued",result={},error="",attempt=0,active_token="",attempts_history=[],queued_at=None)
 db.add(row);db.commit()
 return _dispatch(db,row)

def retry(db,ident):
 row=db.get(KrigingRun,ident)
 if row is None:raise HTTPException(404,"记录不存在")
 if row.status in ACTIVE:
  if row.status=="running" and not is_stale(row):raise HTTPException(409,"任务仍在计算中，请先取消或等待结束")
  if row.status in ("queued","retrying"):return row
 if row.status=="completed":raise HTTPException(409,"已完成的运行无需重试")
 if row.status=="running":
  # 计算中断：running已失去worker支撑，先把中断原因留档再重新排队
  reason="worker中断：计算超过%d秒未完成，已转入重试"%STALE_RUN_SECONDS
  row.attempts_history=_history(row,"interrupted",reason)
  db.commit()
  db.refresh(row)
 return _dispatch(db,row)

def cancel(db,ident):
 row=db.get(KrigingRun,ident)
 if row is None:raise HTTPException(404,"记录不存在")
 if row.status=="cancelled":return row
 if row.status=="completed":raise HTTPException(409,"已完成的运行不能取消")
 if row.status=="failed":raise HTTPException(409,"已失败的运行不能取消，可直接重试")
 # queued/retrying：消息还在列表里，worker取到后凭令牌识别；running：迟到结果在提交时被令牌/状态拦截
 row.attempts_history=_history(row,"cancelled","用户取消排队/计算任务")
 row.status="cancelled";row.error="";row.finished_at=now()
 db.commit()
 return row

def is_stale(row,reference=None):
 if row.status!="running" or not row.started_at:return False
 reference=reference or now()
 return (reference-row.started_at).total_seconds()>STALE_RUN_SECONDS

def recover_pending(db,requeue=True):
 # worker启动时重投可能丢失的排队消息；周期巡检只处理中断running，避免重复入队
 requeued=recovered=0
 if requeue:
  for row in db.scalars(select(KrigingRun).where(KrigingRun.status.in_(("queued","retrying")))).all():
   try:enqueue(row.id,row.active_token);requeued+=1
   except Exception:pass
 cutoff=now()-timedelta(seconds=STALE_RUN_SECONDS)
 stale=db.scalars(select(KrigingRun).where(KrigingRun.status=="running",KrigingRun.started_at<cutoff)).all()
 for row in stale:
  reason="worker中断：计算超过%d秒未完成，可在运行底稿重试"%STALE_RUN_SECONDS
  db.execute(update(KrigingRun).where(KrigingRun.id==row.id,KrigingRun.status=="running").values(status="failed",error=reason,finished_at=now(),attempts_history=_history(row,"interrupted",reason)))
  recovered+=1
 db.commit()
 return {"requeued":requeued,"recovered":recovered}

def _claim(db,run_id,token):
 # 条件更新抢占：只有令牌匹配且处于排队状态的尝试才能进入running，旧尝试/被取消尝试拿不到
 expected=("queued",) if not token else ("queued","retrying")
 result=db.execute(update(KrigingRun).where(KrigingRun.id==run_id,KrigingRun.status.in_(expected),KrigingRun.active_token==token).values(status="running",started_at=now(),finished_at=None,error=""))
 db.commit()
 return result.rowcount==1

def _clear_children(db,run_id):
 for table in CHILD_TABLES:
  db.execute(delete(table).where(table.run_id==run_id))
 db.commit()

def compute(db,run_id,token=""):
 row=db.get(KrigingRun,run_id)
 if row is None:return
 if not token:
  # 兼容旧版本裸run_id消息：仅首次排队（无令牌）的运行可认领，running不允许重复进入
  if row.status!="queued" or row.active_token:return
  token=run_id
 if not _claim(db,run_id,token):return
 _clear_children(db,run_id)
 try:
  study=db.get(KrigingStudy,row.study_id);dataset=db.get(SpatialDataset,study.dataset_id);spec=db.get(VariogramSpec,study.spec_id)
  samples=db.scalars(select(SamplingPoint).where(SamplingPoint.dataset_id==dataset.id).order_by(SamplingPoint.point_id)).all();query_rows=db.scalars(select(QueryPoint).where(QueryPoint.study_id==study.id).order_by(QueryPoint.query_id)).all()
  points=[{"point_id":p.point_id,"x":p.x,"y":p.y,"value":p.value} for p in samples];queries=[{"query_id":p.query_id,"x":p.x,"y":p.y} for p in query_rows]
  config={k:getattr(spec,k) for k in SPEC_FIELDS}
  empirical=empirical_variogram(points,spec.n_bins,spec.max_distance,spec.min_pairs)
  model=fit_exponential(empirical,spec.nugget,(spec.sill_min,spec.sill_max),(spec.range_min,spec.range_max)) if spec.mode=="fit" else {"mode":"fixed","sill":spec.fixed_sill,"range":spec.fixed_range,"nugget":spec.nugget,"weighted_sse":None,"at_boundary":False,"warnings":[],"active_bins":sum(b["used"] for b in empirical["bins"])}
  distances=np.concatenate(([0.],np.linspace(spec.max_distance*1e-6,spec.max_distance,100,dtype=np.float64)))
  model["curve"]=[{"distance":float(h),"semivariance":float(g)} for h,g in zip(distances,semivariance(distances,model["sill"],model["range"],model["nugget"]))]
  kriging=ordinary_kriging(points,queries,model["sill"],model["range"],model["nugget"],spec.condition_limit,spec.negative_tolerance)
  warnings=list(model["warnings"])
  if any(p["prediction"]<0 or p["prediction"]>100 for p in kriging["predictions"]):warnings.append("部分线性预测超出0–100%，未截断，需现场与模型复核")
  fingerprint=hashlib.sha256(json.dumps({"points":points,"queries":queries,"config":config},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  result={"dataset_name":dataset.name,"spec_name":spec.name,"study_name":study.name,"coordinate_system":"local_meters","value_unit":"%","variance_unit":"percentage_points_squared","points":points,"queries":queries,"empirical":empirical,"model":model,"kriging":kriging,"config":config,"warnings":warnings,"input_sha256":fingerprint,"validation_note":"未输出LOO或真实误差；模型参数与预测结果在本次运行中锁定。"}
  for b in empirical["bins"]:db.add(VariogramBin(id=str(uuid4()),run_id=row.id,bin_index=b["index"],lower=b["lower"],upper=b["upper"],distance=b["distance"],semivariance=b["semivariance"],count=b["count"],used=b["used"]))
  for p in model["curve"]:db.add(CurvePoint(id=str(uuid4()),run_id=row.id,**p))
  for predicted in kriging["predictions"]:
   fields={k:predicted[k] for k in ["query_id","x","y","prediction","variance","raw_variance","standard_deviation","mu","weight_sum","variance_clipped"]}
   record=Prediction(id=str(uuid4()),run_id=row.id,**fields);db.add(record);db.flush()
   for weight in predicted["weights"]:db.add(KrigingWeight(id=str(uuid4()),prediction_id=record.id,**weight))
  # 终局条件更新：取消、重试换新令牌后的旧尝试均无法把结果写成成功
  outcome=db.execute(update(KrigingRun).where(KrigingRun.id==run_id,KrigingRun.status=="running",KrigingRun.active_token==token).values(status="completed",result=result,error="",finished_at=now(),model_sill=model["sill"],model_range=model["range"],model_nugget=model["nugget"],system_condition=kriging["condition_number"]))
  if outcome.rowcount!=1:db.rollback()
  else:db.commit()
 except Exception as error:
  db.rollback()
  row=db.get(KrigingRun,run_id)
  if row is None:return
  reason=str(error)[:1000]
  history=_history(row,"failed",reason)
  outcome=db.execute(update(KrigingRun).where(KrigingRun.id==run_id,KrigingRun.status=="running",KrigingRun.active_token==token).values(status="failed",error=reason,finished_at=now(),attempts_history=history))
  if outcome.rowcount==1:db.commit()
  else:db.rollback()
