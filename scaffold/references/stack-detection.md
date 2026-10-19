# 技术栈识别

第 0 步的判据速查。目的：从工作目录的构建清单与源码布局，判断"这是什么语言 / 框架 / 分层 / 横切约定"，产出约定快照。

## 1. 从构建清单判语言与运行时

| 清单文件 | 语言 | 常见框架 |
|---|---|---|
| `package.json` | Node.js / TypeScript | express / nestjs / nextjs / fastify / koa / strapi…（看 `dependencies` / `devDependencies`） |
| `pom.xml` / `build.gradle(.kts)` | Java / Kotlin | spring-boot / quarkus / micronaut / mybatis… |
| `pyproject.toml` / `requirements.txt` / `setup.py` / `Pipfile` | Python | fastapi / django / flask… |
| `go.mod` | Go | gin / echo / chi / fiber… |
| `Cargo.toml` | Rust | axum / actix-web / rocket… |
| `composer.json` | PHP | laravel / symfony / lumen… |
| `*.csproj` / `*.sln` | C# / .NET | ASP.NET Core (MVC / Web API) / EF Core… |
| `Gemfile` | Ruby | rails / sinatra / hanami… |
| `pubspec.yaml` | Dart | shelf / serverpod… |

判断框架时读清单里的实际依赖，不要凭目录名或文件扩展名脑补。识别出语言/框架后，从 `templates/` 选对应的模板集
（清单见 `templates/README.md`）；仓库没有对应模板集的栈，以最相近的既有模块为镜像基准，不硬套别栈模板。

## 2. 从源码布局判分层形态

- 按目录/文件结构推断：`src/controllers + src/services + src/repositories`、`src/routes/`、`interfaces/application/
  domain/infrastructure`、`app/models + app/controllers`（Rails）、clean architecture… **以实际目录为准**。
- 入口如何注册：注解（`@RestController` / `@Controller`）还是路由文件（Express `router.get(...)`、FastAPI
  `@router.get(...)`、Rails `routes.rb`、Go 的路由注册）？新端点该加在哪，从既有端点找同款。
- 数据访问：ORM 实体/模型文件在哪，repository/service 有没有，事务在哪儿声明（`@Transactional` / `transaction()` /
  `async with session` / unit of work）。

## 3. 横切约定（每项都去读一两个真实文件确认）

- 错误处理：全局异常处理器 / 错误中间件 / 统一错误基类 / 错误码表 / i18n message 文件在哪。
- 统一响应：成功响应有没有统一包装（`{ code, data, message }` / `DataResponse` / 直接返回裸数据）。
- 模型基类：实体/模型是否继承公共基类（BaseEntity / BaseModel / ActiveRecord 基类），公共字段
  （id / created_at / updated_at / deleted）怎么来的。
- id 策略：自增 / UUID / cuid / 自定义生成器（如数据库函数 / 雪花算法）。
- 迁移：SQL 脚本目录、ORM migration（Prisma / Alembic / Flyway / Liquibase / EF Core Migrations）、还是 code-first 建表。
- 测试：测试框架（JUnit / Vitest / Jest / Pytest / Go test / cargo test…）与跑测试的命令、CI 里实际跑什么。
- 风格：缩进与宽度、命名（camelCase / snake_case）、注释语言、依赖注入方式（构造器 / field / 手动 new）。

## 4. 判据顺序（别跳过）

清单文件 → 源码目录 → 每个横切约定读 1~2 个真实文件 → 汇总成约定快照。任何一个判据拿不准就标**假设**，
不要为了"看起来确定"而编造。快照模板见 `conventions-snapshot.md`。
