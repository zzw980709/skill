---
name: api-doc-html
description: 将 OpenAPI 3 JSON 生成为单文件、离线可用的 HTML 接口对接文档，含接入约定、页面调用流程、功能导航、字段约束、错误响应、Fetch / TypeScript 示例与可复制的前端 Agent 交接包。用户要 HTML 或便于前端阅读的接口清单时使用；仅导出 OpenAPI、查询端点或同步 Apifox 时使用 api-exporter。
---

# api-doc-html

生成面向前端实施的对接手册：从页面动作找到接口，明确请求、响应、错误和调用方式。OpenAPI 是契约输入，业务接入说明通过配置补充。已有 OpenAPI JSON 时直接渲染，不必扫描 Spring Boot 源码。
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
  --include 'controller:OrderController'
```

明确要全量接口时用 `--all`；其它过滤用 `--include` / `--exclude`。
支持 `--profile`、`--base-url`、`--src`、`--note`、`--keep-openapi`。
脚本优先使用 `--exporter` / `API_EXPORTER_BIN`，再查找同库及常见安装位置或 PATH；不会自动编译。
若只单独安装了本 skill，使用已有 JSON 或通过 `--exporter` 指向可用 CLI 即可。
扫描只用于生成文件，不能因环境里配置了 Apifox 凭据而执行导入。

**多模块、字段补注或枚举附录**：读 [配置说明](references/config.md)，使用配置文件。
配置中的相对路径以配置文件目录为基准；命令行路径以当前目录为基准。

```json
{
  "title": "订单接口",
  "out": "./orders.html",
  "modules": [{"title": "管理端", "openapi": "./orders.json"}],
  "fieldDocs": {"Order.status": "状态，取值以业务定义为准"}
}
```

```bash
python3 <skill-dir>/scripts/gen_api_doc.py --config doc-config.json
```

## 按前端任务组织内容

生成前读取相关需求和实现，在有依据时补充配置：

- `integration`：登录态来源、分页与空值、金额单位、时间格式、统一错误等项目级约定。
- `workflows`：按页面动作排列真实调用链，每步关联唯一接口，并说明前一步哪些数据供下一步使用。
- `operationDocs`：接口的使用时机、状态驱动的按钮、成功后刷新范围、错误提示与重试注意事项。

不强制每个接口写全套说明。无法确定的约定保留缺失提示，用户只要格式转换时直接生成，不为补齐文案扩大调查。
配置结构与类型限制见 [配置说明](references/config.md)；风格与完整演示见 [示例配置](examples/doc-config.json)。

生成结果包含接入首页、功能名称导航、接口详情和并排代码示例；接口的请求、成功响应、异常响应分别查看。

## 交给前端 Agent

文档的「交给 Agent」模块支持按全部、模块、调用流程或单接口复制 Markdown 任务、下载 `.md` 或 JSON 契约包。
每个接口页也有单接口交接入口。任务包包括原始 OpenAPI、引用模型、继承鉴权、接入约定、业务说明和待确认项；不把推导的 TypeScript 当成原始契约。

用户已有明确的前端任务时，可用配置 `agent.task`、`agent.constraints` 和 `agent.acceptanceCriteria` 补充任务、约束和验收条件；没有依据时保持空缺。
任务与验收要求应适用于可选接口范围；专属规则放在接口 `operationDocs`，或明确适用条件，避免单接口导出夹带其它页面任务。
接收方 Agent 应先读其前端仓库指令，复用现有请求、类型与错误封装；未指定的页面、权限和行为不能从接口名推断。
交接文件只包含资料与任务，不授权发布、提交代码或调用真实业务接口。
保留单文件离线能力，`assets/` 中的 CSS 与 JS 生成时内联，不使用 CDN 或外部字体。

## 内容准确性

- 根据用户范围选择接口；不明确时先从现有上下文或 `api-exporter --list` 定位，不自动扩大到全项目。
- 字段说明可来自配置 `fieldDocs`、Java Javadoc 或 OpenAPI description。没有依据的说明保留空缺，不编造枚举、权限或业务包装。
- `srcRoots` 可省略；只有补充 Java 注释才需要。参数描述优先 OpenAPI，其次 `paramDocs`；不从参数名自动推断业务含义。
- 每个模块默认取 `servers[0].url`，可用模块 `baseUrl` 覆盖；核对 context-path 没有与 path 重复。
- `enums` 是人工配置的附录；以源码或用户提供的定义为依据，不承诺自动推导 Java 枚举。
- 保留契约中的大写字段；请求过滤 readOnly，响应过滤 writeOnly。递归、深层结构和联合类型需结合 TypeScript 检查。
- 标注示例来源：优先接口提供的示例，否则注明按 Schema 生成并需替换占位值。Fetch 是调用骨架，TypeScript 是契约推导，不替代项目封装与运行时校验。
- 无响应 schema 只说明静态信息不足，不能直接推断接口没有响应体或一定是文件下载。

## 验证与交付

检查命令退出码、每模块接口数量及脚本自检结果，发现零接口或自检异常时先处理。
自检覆盖 HTML 标签、锚点和重复 ID，不等同于完整 OpenAPI 或业务语义校验。
有浏览器预览能力时，抽查调用流程跳转、搜索与方法筛选、详情标签、嵌套字段、代码切换与复制、窄屏布局、打印，以及 Agent 范围选择、任务复制与下载；未预览时如实说明。

交付 HTML 路径、接口覆盖范围、Base URL 和未能确定的描述。发布或同步属于额外动作，按用户要求执行。
