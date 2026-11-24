---
name: api-doc-html
description: 将 OpenAPI 3 JSON 生成为单文件、离线可用的 HTML 接口对接文档，含接入约定、页面调用流程、功能导航、字段约束、错误响应、生产环境变更对比与可复制的前端 Agent 交接包。用户要 HTML 或便于前端阅读的接口清单时使用；仅导出 OpenAPI、查询端点或同步 Apifox 时使用 api-exporter。
---

# api-doc-html

生成面向前端实施的对接手册：先看本次相对生产环境改了什么，再查完整契约。OpenAPI 是契约输入，业务接入说明通过配置补充。已有 OpenAPI JSON 时直接渲染，不必扫描 Spring Boot 源码。
所有脚本路径相对本 skill 目录；从目标项目执行时使用 skill 的绝对路径。需要 Python 3，仅用标准库。

## 选择输入方式

**已有 OpenAPI JSON**：直接运行渲染器；`--src` 可选，用于补充 Java 字段注释。

```bash
python3 <skill-dir>/scripts/gen_api_doc.py --title "订单接口" --out ./orders.html \
  --module "订单=/path/to/orders.json" \
  --src /path/to/repo/src/main/java
```

**本地 Spring Boot 源码**：先按同库 `api-exporter/SKILL.md` 准备 CLI，再一条命令扫描并渲染：

```bash
bash <skill-dir>/scripts/gen_from_project.sh \
  --project /path/to/repo --out ./orders.html --title "订单接口" \
  --include 'controller:OrderController' \
  --base pro
```

明确要全量接口时用 `--all`；其它过滤用 `--include` / `--exclude`。
支持 `--profile`、`--base-url`、`--src`、`--note`、`--keep-openapi`。
脚本优先使用 `--exporter` / `API_EXPORTER_BIN`，再查找同库及常见安装位置或 PATH；不会自动编译。
若只单独安装了本 skill，使用已有 JSON 或通过 `--exporter` 指向可用 CLI 即可。
扫描只用于生成文件，不能因环境里配置了 Apifox 凭据而执行导入。

**变更基线**（可选，用于生成「本次变更」）：

- `--base pro`：取仓库中版本最高的 `v*-backend` 生产 tag，`git archive` 旧代码后用同一套过滤条件再导出旧契约。当前工作区与生产 tag 的契约差异会显示在页面上。
- `--base <git-ref>`：对比指定分支、tag 或提交。
- `--baseline <openapi.json>`：直接使用已有的旧契约文件（例如线上导出的 JSON），不需要 git。

不传基线时仍会生成完整接口文档，只是没有「本次变更」视图。基线与当前范围使用相同的 `--include` / `--exclude` / `--profile`。

**多模块、字段补注或枚举附录**：读 [配置说明](references/config.md)，使用配置文件。
配置中的相对路径以配置文件目录为基准；命令行路径以当前目录为基准。

```json
{
  "title": "订单接口",
  "out": "./orders.html",
  "baselineLabel": "生产环境 pro",
  "baselineDate": "2026-11-18",
  "modules": [{"title": "管理端", "openapi": "./orders.json", "baseline": "./orders.production.json"}],
  "fieldDocs": {"Order.status": "状态，取值以业务定义为准"}
}
```

```bash
python3 <skill-dir>/scripts/gen_api_doc.py --config doc-config.json
```

## 页面结构

生成结果是单文件离线 HTML，包含：

- 开始对接：接入约定、页面调用流程、接口目录；有基线时顶部先展示本次变更摘要。
- 本次变更（有基线时）：新增、修改、移除的接口，以及参数、请求体字段、响应状态码和响应字段的新旧对比；支持按类型筛选、只看破坏性、复制变更清单。
- 接口详情：使用说明、请求、成功响应、异常响应；右侧「本次变更」栏显示该接口的请求/响应变化，字段表中直接标记新增或变更。
- 交给 Agent：按全部、本次变更、模块、调用流程或单接口导出任务包。
- 枚举速查（配置 `enums` 时）。

页面不生成 Fetch / TypeScript / 示例 JSON，前端按自己仓库的请求封装和类型约定实现。

## 按前端任务组织内容

生成前读取相关需求和实现，在有依据时补充配置：

- `integration`：登录态来源、分页与空值、金额单位、时间格式、统一错误等项目级约定。
- `workflows`：按页面动作排列真实调用链，每步关联唯一接口，并说明前一步哪些数据供下一步使用。
- `operationDocs`：接口的使用时机、状态驱动的按钮、成功后刷新范围、错误提示与重试注意事项。

不强制每个接口写全套说明。无法确定的约定保留缺失提示，用户只要格式转换时直接生成，不为补齐文案扩大调查。
配置结构与类型限制见 [配置说明](references/config.md)；风格与完整演示见 [示例配置](examples/doc-config-v2.json)。

## 交给前端 Agent

「交给 Agent」模块默认选择「本次变更的接口」，任务包只包含：

- 本次任务（可在页面临时填写）；
- 本次接口变更清单（与生产环境对比）；
- 所选接口的最新 OpenAPI 契约（含引用模型与继承鉴权）；
- 真实的契约缺口（未声明鉴权、未声明成功/异常响应、未解析引用等）。

不再生成通用「工作方式」「验收要求」或约束模板；接收方 Agent 应先读其前端仓库指令，复用现有请求、类型和错误封装。
用户有明确任务时，用配置 `agent.task` 预填；接口专属说明放在 `operationDocs`。
交接文件只包含资料与任务，不授权发布、提交代码或调用真实业务接口。
保留单文件离线能力，`assets/` 中的 CSS 与 JS 生成时内联，不使用 CDN 或外部字体。

## 内容准确性

- 根据用户范围选择接口；不明确时先从现有上下文或 `api-exporter --list` 定位，不自动扩大到全项目。
- 字段说明可来自配置 `fieldDocs`、Java Javadoc 或 OpenAPI description。没有依据的说明保留空缺，不编造枚举、权限或业务包装。
- `srcRoots` 可省略；只有补充 Java 注释才需要。参数描述优先 OpenAPI，其次 `paramDocs`；不从参数名自动推断业务含义。
- 每个模块默认取 `servers[0].url`，可用模块 `baseUrl` 覆盖；核对 context-path 没有与 path 重复。
- `enums` 是人工配置的附录；以源码或用户提供的定义为依据，不承诺自动推导 Java 枚举。
- 保留契约中的大写字段；请求过滤 readOnly，响应过滤 writeOnly。递归、深层结构和联合类型结合原始契约检查。
- 变更对比基于新旧两版 OpenAPI 的契约结构：接口增删、参数、请求体字段、响应状态码与字段、类型、必填、枚举和常见约束。说明文字变化不作为契约变更。
- 不提供基线时不得声称「本次无变更」；页面会显示未提供基线。基线文件缺失或为空时，脚本会警告，当前范围按新增处理。
- 无响应 schema 只说明静态信息不足，不能直接推断接口没有响应体或一定是文件下载。

## 验证与交付

检查命令退出码、每模块接口数量及脚本自检结果，发现零接口或自检异常时先处理。
自检覆盖 HTML 标签、锚点和重复 ID，不等同于完整 OpenAPI 或业务语义校验。
有浏览器预览能力时，抽查本次变更卡片与筛选、接口跳转、搜索与方法筛选、详情标签、嵌套字段、窄屏布局、打印，以及 Agent 范围选择、任务复制与下载；未预览时如实说明。

交付 HTML 路径、接口覆盖范围、Base URL、使用的变更基线和未能确定的描述。发布或同步属于额外动作，按用户要求执行。
