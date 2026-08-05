# {{中文描述}}请求/响应
# ⚠️ Pydantic v1/v2 写法以活代码为准
from pydantic import BaseModel, Field


class {{ModuleName}}Create(BaseModel):
    # TODO(需求): 按接口字段补全
    name: str = Field(min_length=1, description="{{中文描述}}名称")


class {{ModuleName}}Update(BaseModel):
    # TODO(需求): 按接口字段补全；空值保留约定以活代码为准
    name: str | None = None


class {{ModuleName}}Response(BaseModel):
    id: int
    name: str | None = None

    class Config:
        from_attributes = True
