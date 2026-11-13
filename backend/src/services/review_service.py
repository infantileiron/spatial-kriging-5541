from uuid import uuid4
from fastapi import HTTPException
from ..models.review import FieldReview
from ..models.run import KrigingRun

def create(db,body):
 run=db.get(KrigingRun,body.run_id)
 if run is None:raise HTTPException(404,"运行记录不存在")
 # 复核只接纳最终成功的结果；取消、失败、重试中的运行一律不进入签批流程
 if run.status!="completed":raise HTTPException(409,"仅最终成功（completed）的运行可提交复核，当前状态：%s"%run.status)
 row=FieldReview(id=str(uuid4()),**body.model_dump(),state="submitted",reviewer="");db.add(row);db.commit();return row

def approve(db,row,user):
 if row.state!="submitted":raise HTTPException(409,"复核已处理")
 row.state="approved";row.reviewer=user.email;db.commit();return row
