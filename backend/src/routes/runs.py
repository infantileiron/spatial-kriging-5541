from fastapi import APIRouter,Depends
from ..config.database import get_db
from ..utils.auth import current,write_user
from ..schemas.run import RunCreate
from ..controllers import run_controller as controller
router=APIRouter(prefix="/runs",tags=["runs"])
@router.get("")
def listing(db=Depends(get_db),user=Depends(current)):return controller.list_all(db)
@router.get("/{ident}")
def detail(ident:str,db=Depends(get_db),user=Depends(current)):return controller.detail(db,ident)
@router.post("",status_code=201)
def create(body:RunCreate,db=Depends(get_db),user=Depends(write_user)):return controller.create(db,body)
@router.post("/{ident}/cancel")
def cancel(ident:str,db=Depends(get_db),user=Depends(write_user)):return controller.cancel(db,ident)
@router.post("/{ident}/retry")
def retry(ident:str,db=Depends(get_db),user=Depends(write_user)):return controller.retry(db,ident)
