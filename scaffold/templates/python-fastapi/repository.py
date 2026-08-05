# {{中文描述}}数据访问
# ⚠️ ORM 以活代码为准（SQLAlchemy 2.0 / Tortoise / Django ORM…）
from sqlalchemy.orm import Session

from .model import {{ModuleName}}
from .schemas import {{ModuleName}}Create, {{ModuleName}}Update


class {{ModuleName}}Repository:
    def __init__(self, db: Session):
        self.db = db

    def list(self):
        return self.db.query({{ModuleName}}).filter({{ModuleName}}.deleted.is_(False)).all()

    def get(self, id: int):
        return (
            self.db.query({{ModuleName}})
            .filter({{ModuleName}}.id == id, {{ModuleName}}.deleted.is_(False))
            .first()
        )

    def create(self, payload: {{ModuleName}}Create):
        obj = {{ModuleName}}(**payload.model_dump())
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update(self, obj: {{ModuleName}}, payload: {{ModuleName}}Update):
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(obj, k, v)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    # 软删除：deleted 字段约定以活代码为准；若用硬删除直接 delete
    def soft_delete(self, id: int):
        self.db.query({{ModuleName}}).filter({{ModuleName}}.id == id).update({"deleted": True})
        self.db.commit()
