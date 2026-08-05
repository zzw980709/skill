# Go（Gin + sqlx）模板

本模板集对应 **Go + Gin + sqlx** 的仓库。若目标仓库用 echo / chi / gorm / sqlc / database/sql，
**以活代码为准**，只借鉴本集的骨架形态。

本目录是生成脚手架的**起点骨架**，不是免检答案。生成前**必须**按 `SKILL.md` 的【生成规范】读取目标模块/最相近模块的
活代码，把模板与当前仓库的真实写法校准一致——尤其下表标注「⚠️ 需校准」的点。

## 模板清单

| 文件 | 对应层 | 以哪个活代码为基准 |
|---|---|---|
| `handler.go` | HTTP 层 | 既有 handler（路由注册、响应包装） |
| `service.go` | 服务层 | 既有 service（事务/错误抛出位置） |
| `repository.go` | 数据访问 | 既有 repository（ORM 写法、软删除） |
| `model.go` | 模型 | 既有 model（db 标签、id 策略、审计字段） |
| `dto.go` | 请求/响应 | 既有 dto（json 标签、validator） |

## 占位符

| 占位符 | 含义 | 示例 |
|---|---|---|
| `{{ModuleName}}` | 模块名（PascalCase，类型/结构体名） | `Customer` |
| `{{moduleName}}` | 模块名（camelCase，包名/变量/文件名） | `customer` |
| `{{mapping}}` | 路由路径 | `customers` |
| `{{tableName}}` | 表名（snake_case） | `customers` |
| `{{i18nKey}}` | 错误消息 key | `customer.not_found` |
| `{{中文描述}}` | 模块中文注释 | `客户` |

## 校准清单（⚠️ 生成前逐项对照活代码）

1. 路由注册：gin RouterGroup / echo / chi，注册方式与中间件链。
2. 响应包装：成功/错误响应有无统一包装（`gin.H{"code":..., "data":...}` 或独立 helper）。
3. 错误约定：哨兵错误 / 错误码 / 包装 error，消息从哪来。
4. 参数绑定与校验：`binding` 标签 / validator 版本。
5. 事务：`sqlx` 手动 / `gorm.Transaction` / `sqlc`，还是无。
6. 软删除：有无 `deleted` 字段约定、Repository 里怎么实现。
7. id 生成：`gen_random_uuid()` / snowflake / 自增。
8. 风格：缩进（gofmt）、命名、注释语言。

## 禁止

- 不删 `// TODO(需求):` 注释去"假装完成"。
- 不为了套模板而生成与活代码结构不同的分层。
