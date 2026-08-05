# {{中文描述}}路由
# ⚠️ 挂载位置与既有路由一致（如 app.include_router(router, prefix="/{{mapping}}", tags=["{{中文描述}}"])）
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from . import service as {{module_name}}_service
from .schemas import {{ModuleName}}Create, {{ModuleName}}Update, {{ModuleName}}Response
# ⚠️ 会话获取方式以活代码为准
from ...core.db import get_db

router = APIRouter()


@router.get("/", response_model=list[{{ModuleName}}Response])
def list_{{module_name}}(db: Session = Depends(get_db)):
    return {{module_name}}_service.list_{{module_name}}(db)


@router.post("/", response_model={{ModuleName}}Response, status_code=201)
def create_{{module_name}}(payload: {{ModuleName}}Create, db: Session = Depends(get_db)):
    return {{module_name}}_service.create_{{module_name}}(db, payload)


@router.put("/{id}", response_model={{ModuleName}}Response)
def update_{{module_name}}(id: int, payload: {{ModuleName}}Update, db: Session = Depends(get_db)):
    return {{module_name}}_service.update_{{module_name}}(db, id, payload)


@router.delete("/{id}", status_code=204)
def delete_{{module_name}}(id: int, db: Session = Depends(get_db)):
    {{module_name}}_service.delete_{{module_name}}(db, id)
