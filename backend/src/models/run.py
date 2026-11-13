from sqlalchemy import String,Text,JSON,ForeignKey,Double,Integer,DateTime
from sqlalchemy.orm import Mapped,mapped_column
from .common import RecordMixin,now
from ..config.database import Base
class KrigingRun(RecordMixin,Base):
 __tablename__="runs"
 study_id:Mapped[str]=mapped_column(ForeignKey("studies.id"))
 status:Mapped[str]=mapped_column(String(20),default="queued")
 result:Mapped[dict]=mapped_column(JSON,default=dict)
 error:Mapped[str]=mapped_column(Text,default="")
 # 当前排队/计算尝试的序号与令牌；每次新尝试（首次/重试）都会递增并换令牌
 attempt:Mapped[int]=mapped_column(Integer,default=1)
 active_token:Mapped[str]=mapped_column(String(36),default="")
 # 历次非成功尝试（失败、取消、中断）的原因留档，重试不清空
 attempts_history:Mapped[list]=mapped_column(JSON,default=list)
 queued_at:Mapped["object"]=mapped_column(DateTime,nullable=True)
 started_at:Mapped["object"]=mapped_column(DateTime,nullable=True)
 finished_at:Mapped["object"]=mapped_column(DateTime,nullable=True)
 model_sill:Mapped[float|None]=mapped_column(Double,nullable=True)
 model_range:Mapped[float|None]=mapped_column(Double,nullable=True)
 model_nugget:Mapped[float|None]=mapped_column(Double,nullable=True)
 system_condition:Mapped[float|None]=mapped_column(Double,nullable=True)
