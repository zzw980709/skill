# Node.js / TypeScript（Express + Prisma）模板

本模板集对应 **Node.js + TypeScript + Express + Prisma** 的仓库。若目标仓库用 NestJS / TypeORM / Knex / Fastify，
**以活代码为准**，只借鉴本集的骨架形态。

本目录是生成脚手架的**起点骨架**，不是免检答案。生成前**必须**按 `SKILL.md` 的【生成规范】读取目标模块/最相近模块的
活代码，把模板与当前仓库的真实写法校准一致——尤其下表标注「⚠️ 需校准」的点。

## 模板清单

| 文件 | 对应层 | 以哪个活代码为基准 |
|---|---|---|
| `router.ts` | 路由层 | 既有 router（挂载位置、路径命名） |
| `service.ts` | 服务层 | 既有 service（事务/错误抛出位置） |
| `repository.ts` | 数据访问 | 既有 repository（ORM 写法、软删除） |
| `dto.ts` | 请求/响应 | 既有 zod schema / 校验方式 |
| `migration.sql` | 迁移 | 既有 migration（Prisma schema / SQL 脚本） |

## 占位符

| 占位符 | 含义 | 示例 |
|---|---|---|
| `{{ModuleName}}` | 模块名（PascalCase，类型/类名） | `Customer` |
| `{{moduleName}}` | 模块名（camelCase/kebab，文件名与变量） | `customer` |
| `{{mapping}}` | 路由路径 | `customers` |
| `{{tableName}}` | 表名（snake_case） | `customers` |
| `{{i18nKey}}` | 错误消息 key | `customer.not_found` |
| `{{中文描述}}` | 模块中文注释 | `客户` |

## 校准清单（⚠️ 生成前逐项对照活代码）

1. 依赖注入：构造器注入 / 容器（tsyringe/Nest）还是手动 new。
2. 路由注册：本 router 如何挂到 app（`app.use('/{{mapping}}', {{moduleName}}Router)` 的位置）。
3. 响应包装：成功/错误响应有无统一包装、HTTP 状态码约定。
4. 校验：zod / class-validator / joi，错误消息格式。
5. 事务：Prisma `$transaction` / TypeORM `dataSource.transaction` / Knex `.transaction`，还是手动。
6. 软删除：有无 `deleted` 字段约定、Repository 里怎么实现。
7. 迁移：用什么工具、schema 文件在哪。
8. 风格：缩进、命名、分号、引号、注释语言。

## 禁止

- 不删 `// TODO(需求):` 注释去"假装完成"。
- 不为了套模板而生成与活代码结构不同的分层。
