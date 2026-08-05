# {{中文描述}}模型
# ⚠️ 是否继承公共基类、id 策略、审计字段以活代码为准（SQLAlchemy 版本写法见同域活代码）
from sqlalchemy import Boolean, Column, DateTime, Integer, String, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class {{ModuleName}}(Base):
    __tablename__ = "{{table_name}}"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted = Column(Boolean, nullable=False, default=False)
