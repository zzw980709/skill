# 约定快照模板

第 0 步识别的结果，写下来供生成与复审引用。生成前填完以下字段；拿不准的标「❓假设」，在确认闸门时向用户确认。

```yaml
language/runtime:    # e.g. Java 11 / Node 18 / Python 3.12
template_set:        # e.g. java-springboot-ddd / node-ts-express / python-fastapi / go-gin（见 templates/README.md）
framework:           # e.g. Spring Boot 2.7 + JPA / Express 4 + Prisma / FastAPI + SQLAlchemy
build_command:       # e.g. ./gradlew build / npm run build / go build ./...
test_command:        # e.g. ./gradlew test / npm test / pytest
architecture:        # 分层形态 + 每层目录
  - <层>: <目录>      # e.g. entry -> src/controllers
  - <层>: <目录>
entry_registration:  # 注解 / 路由文件 / routes.rb… 新端点加在哪
model_base:          # 基类名 + 位置；公共字段
id_strategy:         # 自增 / uuid / cuid / 自定义
data_access:         # ORM 名 + repository 写法 + 事务声明位置
error_convention:    # 错误基类/中间件 + 消息来源（i18n key / 错误码 / 文案）
response_wrapper:    # 成功响应包装（或裸数据）
migration:           # 方式 + 目录 + 命名
i18n:                # 语言文件位置 / 是否需要多语言
style:               # 缩进 / casing / 注释语言 / 注入方式
tests:               # 框架 + 受影响模块怎么跑
```

## 校准清单（生成前逐项对照活代码）

1. 模型/实体是否继承基类，基类 import 路径；若目标模块有自己的基类，用它的。
2. id 生成策略与迁移里的默认值是否一致。
3. 特殊类型字段（jsonb、枚举、数组、JSON 列）要不要专门类型映射，以同模块写法为准。
4. 软删除/审计字段（deleted / updated_at / created_at）有没有、在哪一层维护。
5. 需要操作人身份的接口，入口/服务层有没有既有的取身份工具（如 ContextService、request context、auth 中间件）。
6. i18n：新增的 key 要同步哪些文件。
7. 更新方法若有空值保留约定，按同模块写法实现。
8. 数据访问层关键查询给索引 / 迁移，按同模块惯例。

## 快照用途

- 生成前：作为「模板」的替代，回答"这个仓库的规矩是什么"。
- 复审时：第 1 / 3 / 4 / 5 / 6 / 8 条直接对照快照逐项核验。
- 快照不是免检答案——任何一项与读到的新代码冲突，以活代码为准并更新快照。
