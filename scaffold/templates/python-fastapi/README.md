# Python（FastAPI + SQLAlchemy）模板

本模板集对应 **Python + FastAPI + SQLAlchemy** 的仓库。若目标仓库用 Django / Flask / Tortoise ORM，
**以活代码为准**，只借鉴本集的骨架形态。

本目录是生成脚手架的**起点骨架**，不是免检答案。生成前**必须**按 `SKILL.md` 的【生成规范】读取目标模块/最相近模块的
活代码，把模板与当前仓库的真实写法校准一致——尤其下表标注「⚠️ 需校准」的点。

## 模板清单

| 文件 | 对应层 | 以哪个活代码为基准 |
|---|---|---|
| `router.py` | 路由层 | 既有 router（prefix/tags 挂载） |
| `service.py` | 服务层 | 既有 service（事务/错误抛出位置） |
| `repository.py` | 数据访问 | 既有 repository（ORM 写法、软删除） |
| `schemas.py` | 请求/响应 | 既有 Pydantic schema / 校验 |
| `model.py` | 模型 | 既有模型（基类、id 策略、审计字段） |
| `migration.sql` | 迁移 | 既有 migration（Alembic / SQL 脚本） |

## 占位符

| 占位符 | 含义 | 示例 |
|---|---|---|
| `{{ModuleName}}` | 模块名（PascalCase，类名） | `Customer` |
| `{{module_name}}` | 模块名（snake_case，文件名/变量） | `customer` |
| `{{mapping}}` | 路由 prefix | `customers` |
| `{{table_name}}` | 表名（snake_case） | `customers` |
| `{{i18nKey}}` | 错误消息 key | `customer.not_found` |
| `{{中文描述}}` | 模块中文注释 | `客户` |

## 校准清单（⚠️ 生成前逐项对照活代码）

1. 依赖注入：FastAPI `Depends(get_db)` 还是别的会话获取方式。
2. 路由挂载：`app.include_router(router, prefix="/{{mapping}}", tags=...)` 的位置与写法。
3. 响应包装：直接返回模型还是统一 `{ code, data, message }` 包装。
4. 校验：Pydantic v1/v2 写法（`model_dump` vs `dict`）、`from_attributes` vs `orm_mode`。
5. 事务：`with db.begin()` / 装饰器 / 手动 commit，以活代码为准。
6. 软删除：有无 `deleted` 字段约定、Repository 里怎么实现。
7. 迁移：Alembic 目录与命名、还是 SQL 脚本。
8. 风格：缩进、引号、类型注解风格。

## 禁止

- 不删 `# TODO(需求):` 注释去"假装完成"。
- 不为了套模板而生成与活代码结构不同的分层。
