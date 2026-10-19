# Java Spring Boot（项目版 DDD）模板

本模板集对应 **Java + Spring Boot + JPA、贫血实体 + application 编排** 的仓库，源自实际项目的写法沉淀。
同属本 skill 的其它模板集见 `templates/` 根目录。**注意：仓库的实际分层若与四层模板不一致（例如用 po/repository/service），照它的样，不硬套。**

本目录是生成脚手架的**起点骨架**，不是免检答案。生成前**必须**按 `SKILL.md` 的【生成规范】读取目标领域/模板源的活代码，把模板与当前仓库的真实写法校准一致——尤其下表标注「⚠️ 需校准」的点。

## 模板清单

| 文件 | 对应分层 | 以哪个活代码为基准 |
|---|---|---|
| `entity.java` | `domain/model/entity` | 同域既有实体（含 `BaseEntity`） |
| `repository.java` | `domain/repository` | 同域既有 repository |
| `application.java` | `application/` | 同域既有 application |
| `controller.java` | `interfaces/controller` | 同域既有 controller |
| `dto-request.java` | `interfaces/dto` | 同域既有 request |
| `dto-response.java` | `interfaces/dto` | 同域既有 response |
| `ddl.sql` | `resources/sql/` | 项目的建表约定文档 |

## 占位符

用 `{{PLACEHOLDER}}` 表示待替换变量。**替换时确保名称一致性**：`{{EntityName}}`（UpperCamelCase）与 `{{entityName}}`（lowerCamelCase）必须来自同一个实体名，例如 `CustomerLevel` / `customerLevel`。

| 占位符 | 含义 | 示例 |
|---|---|---|
| `{{basePackage}}` | 根包 | `com.example.demo` |
| `{{domainName}}` | 业务域包名（小写） | `customer`、`customerLevel` |
| `{{EntityName}}` | 实体类名（不含 Entity 后缀时的主语） | `CustomerLevel` |
| `{{entityName}}` | 同上，小驼峰 | `customerLevel` |
| `{{tableName}}` | 表名（蛇形，可带业务前缀） | `app_customer_level` |
| `{{mapping}}` | Controller 的 `@RequestMapping` 路径 | `customer/level` |
| `{{i18nKey}}` | 该资源的中文语义 key | `customer.level` |
| `{{author}}` / `{{date}}` | 类注释作者 / 日期 | `Your Name` / `2025/01/01` |
| `{{中文描述}}` | 类/表的中文注释 | `客户等级` |

## 校准清单（⚠️ 生成前逐项对照活代码）

1. **BaseEntity 位置**：`BaseEntity` 通常定义在公共域（如 `common/domain/model/entity`）。其它域引用它时，import 写 `{{basePackage}}.common.domain.model.entity.BaseEntity`；若目标域有自己的基类，用它。
2. **id 生成策略**：模板抄了 `@GeneratedValue(strategy = GenerationType.IDENTITY)`，与 DDL 里的默认生成函数看似冲突但仓库如此；**以目标表/同域实体的实际注解为准**。
3. **jsonb 字段**：实体含 jsonb 字段时才需要 `@TypeDef(name = "jsonb", typeClass = JsonBinaryType.class)` + 字段上 `@Type(type = "jsonb")`，不需要就删掉。
4. **逻辑删除 SQL**：不同 repository 的 `logicDeleteById` 有的带 `updated_at = now()`、有的不带，以同域写法为准。
5. **Request 是否 extends OperatorRequest**：需要操作人身份（管理端/销售端）时才继承；不需要就删。
6. **i18n**：新增的 key 必须同步 `messages*.properties` 全部 9 个语言文件（`properties/_en/_es/_fr/_it/_pl/_pt/_zh/_zh_CN`）。
7. **实体 update()**：若字段有空值保留约定，用"setter 判空 + 末尾 `super.touch()`"的方式；不保留空值就直接赋值。
8. **DDL 索引**：按查询条件给关键字段加索引；唯一键用 `create unique index ... where deleted = false` 部分唯一索引。

## 禁止

- 不删 `// TODO(需求):` 注释去"假装完成"——它是要交接给业务方确认的标记，见 `SKILL.md` 的 TODO 规则。
- 不为了套模板而生成与活代码结构不同的分层（例如目标包明明用 `po/repository/service`，就不要硬套四层模板）。
