# {{中文描述}}服务
# ⚠️ 错误类型以活代码为准（HTTPException / 自定义 AppError / 错误码）
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .model import {{ModuleName}}
from .repository import {{ModuleName}}Repository
from .schemas import {{ModuleName}}Create, {{ModuleName}}Update


class {{ModuleName}}Service:
    def __init__(self, db: Session):
        self.db = db
        self.repo = {{ModuleName}}Repository(db)

    def list(self):
        return self.repo.list()

    def create(self, payload: {{ModuleName}}Create):
        # TODO(需求): 幂等/唯一性校验，命中时抛 HTTPException(409, "{{i18nKey}}.exists")
        # TODO(需求): 若跨表写，用 with self.db.begin(): 包事务
        return self.repo.create(payload)

    def update(self, id: int, payload: {{ModuleName}}Update):
        obj = self.repo.get(id)
        if obj is None:
            raise HTTPException(404, "{{i18nKey}}.not_found")
        # TODO(需求): 字段映射 / 空值保留约定
        return self.repo.update(obj, payload)

    def delete(self, id: int):
        self.repo.soft_delete(id)  # ⚠️ 是否软删除以活代码为准
