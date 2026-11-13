from sqlalchemy import select
from ..services import run_service
from ..models.run import KrigingRun
from ..models.common import serialize
from .common import require
def list_all(db):
 ids=db.scalars(select(KrigingRun.id).order_by(KrigingRun.created_at.desc()).limit(200)).all()
 rows=[]
 for ident in ids:
  row=db.get(KrigingRun,ident)
  payload=serialize(row)
  payload["stale"]=run_service.is_stale(row)
  rows.append(payload)
 return rows
def detail(db,ident):
 row=require(db,KrigingRun,ident)
 payload=serialize(row)
 payload["stale"]=run_service.is_stale(row)
 return payload
def create(db,body):return serialize(run_service.create(db,body))
def cancel(db,ident):return serialize(run_service.cancel(db,ident))
def retry(db,ident):return serialize(run_service.retry(db,ident))
