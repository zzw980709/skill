# 配置文件参考

`gen_api_doc.py --config <file>.json` 的完整字段。相对路径以配置文件所在目录为基准。

> 单模块、无需 `fieldDocs`/`enums` 时，可跳过本文件，直接用 `scripts/gen_from_project.sh` 一条命令完成扫描 + 生成；生产基线用 `--base pro`。

## 最小示例

```json
{
  "title": "模块 接口对接清单",
  "out": "./模块-接口对接.html",
  "srcRoots": ["/path/to/project/src/main/java"],
  "modules": [
    { "title": "订单模块（管理端）", "openapi": "orders.json", "note": "响应包装 {success,message,data}" }
  ]
}
```

## 字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `title` | 否 | 文档标题，默认「接口对接清单」 |
| `out` | 否 | 输出 HTML 路径，默认 `./api-doc.html` |
| `srcRoots` | 否 | Java 源码根目录数组，用于提取 DTO 字段 Javadoc；可传多个仓库 |
| `modules` | 是 | 模块数组，见下 |
| `baselineLabel` | 否 | 变更基线显示名，默认「生产环境」；例如「生产环境 pro」 |
| `baselineDate` | 否 | 基线日期，例如 `2026-11-18`；显示在变更摘要和接口页 |
| `heroNotes` | 否 | 顶部说明的 HTML 片段数组（例如 Base URL、响应包装、日期格式） |
| `paramDocs` | 否 | 参数名 → 说明，补充缺失描述；不再内置推测的业务含义 |
| `fieldDocs` | 否 | `"SchemaName.prop": "说明"`，用于补 Javadoc 缺失的字段 |
| `enums` | 否 | 枚举附录，见下 |

## modules

```json
{
  "title": "商品模块（客户端）",
  "openapi": "orders.json",
  "baseline": "orders.production.json",
  "note": "响应包装 {data}；按客户端账号传 user_id",
  "baseUrl": "http://localhost:8080/api"
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `title` | 是 | 模块标题，同时用于侧栏分组与锚点（自动 slug） |
| `openapi` | 是 | 当前 OpenAPI 3 JSON 路径 |
| `baseline` | 否 | 上一版 OpenAPI 3 JSON 路径；用于生成「本次变更」。也可由 `gen_from_project.sh --base` 自动写入 |
| `note` | 否 | 模块说明，显示在模块标题下 |
| `baseUrl` | 否 | 覆盖 `servers[0].url`；用于复制按钮与模块头展示 |

## 变更基线

有三种取法，选一种即可：

1. `gen_from_project.sh --base pro`：取版本最高的 `v*-backend` 生产 tag，导出旧代码契约后对比。
2. `gen_from_project.sh --base <git-ref>`：对比指定分支、tag 或提交。
3. `gen_from_project.sh --baseline <openapi.json>` 或配置 `modules[].baseline`：直接使用已有的旧 OpenAPI 文件。

不传基线时生成完整文档，但没有「本次变更」视图。基线导出与当前导出使用相同的 `--include` / `--exclude` / `--profile`；基线没有接口时脚本会警告，当前范围按新增处理。

变更对比覆盖：

- 接口新增、移除、路径变化；
- 参数新增、移除、类型、必填、枚举和常见约束变化；
- 请求体字段新增、移除、类型、必填、约束变化；
- 响应状态码新增、移除，响应字段新增、移除、类型、必填、约束变化；
- 鉴权声明变化。

说明文字变化不作为契约变更。删除接口、删除字段、类型变化、请求可选变必填、成功响应移除等会标记为破坏性变更。

## enums

```json
"enums": [
  {
    "title": "订单模块",
    "rows": [
      ["status", "1 草稿 / 2 已完成"],
      ["type", "1 普通 / 2 加急"]
    ]
  }
]
```

`rows` 的每一项是 `[字段名, 取值说明]`；字段名会渲染成 `<code>`。

## fieldDocs 示例

```json
"fieldDocs": {
  "SomeResponse.related_items": "关联明细（含明细列表）",
  "SomeDetailVo.records": "操作记录（type 1 新增 / 2 取消 / 3 补偿）"
}
```

优先于 Javadoc；适合注释缺失或语义需要补充说明的场景。

## 命令行等价参数

不想写配置文件时：

```bash
python3 scripts/gen_api_doc.py \
  --title "接口清单" \
  --out out.html \
  --module "标题A=/abs/a.json" \
  --module "标题B=/abs/b.json|模块备注" \
  --src /repo/src/main/java
```

命令行简易模式仅配置标题、输出、模块与源码目录；需要基线、字段补注或枚举时就用配置文件，或使用 `gen_from_project.sh`。

## 面向前端的对接说明

这些信息是对 OpenAPI 契约的补充，应来自需求、源码或已确认的对接约定。未配置时文档展示缺失提示，不会推断业务流程。

| 字段 | 类型 | 用途 |
| --- | --- | --- |
| `description` | 字符串 | 首页简介 |
| `audience` | 字符串 | 阅读对象，如管理后台 / Web 前端 |
| `integration` | 数组 | 项目级约定，每项 `{title, text}`；例如登录态、分页、金额单位、时间、业务错误 |
| `workflows` | 数组 | 页面调用流程，结构见下；按给定顺序展示，不自动从 HTTP 方法推断 |
| `operationDocs` | 对象 | 补充单接口的使用场景 `usage` 和联调提示 `notes`（字符串数组） |

```json
{
  "description": "订单列表与详情页的接口对接手册",
  "audience": "管理后台 / Web 前端",
  "integration": [
    {"title": "分页", "text": "page 从 1 开始。总数读取 total，无记录时 items 为空数组。"}
  ],
  "workflows": [
    {
      "title": "列表 → 详情",
      "description": "订单页的基本浏览流程",
      "steps": [
        {"module": "订单管理", "operationId": "listOrders", "note": "状态筛选变化时重置页码。"},
        {"module": "订单管理", "endpoint": "GET /orders/{orderId}", "note": "使用列表中的 id。"}
      ]
    }
  ],
  "operationDocs": {
    "listOrders": {
      "usage": "列表首次加载、筛选或翻页时调用。",
      "notes": ["不传 status 表示全部；不要传空字符串。"]
    }
  }
}
```

步骤用 `operationId` 或 `endpoint`（`METHOD /path`）定位；跨模块重名时加 `module`（等于模块 title）。
每步必须唯一命中，否则生成失败，避免把页面动作链接到错误接口。

`operationDocs` 支持放在顶层，也可放在 `modules` 的某个模块内，键可为 operationId 或 `METHOD /path`。
推荐把模块专属说明放在模块内。同层 operationId 的优先级高于方法路径；同种键的模块说明覆盖顶层说明。
`usage` / `notes` 均按纯文本渲染。

完整示例见 [examples/doc-config-v2.json](../examples/doc-config-v2.json)，配套数据为虚构的订单 API 与生产基线。

## 契约展示边界

- 字段表展示嵌套路径、必填、枚举、默认值、格式及常见约束。支持本地 `$ref`、`allOf`；联合结构主要展示类型摘要。
- 请求字段过滤 `readOnly`，响应字段过滤 `writeOnly`；保留合法的大写字段，不按命名猜测 Java 常量。
- 递归和过深结构会截断，不代表可直接替代运行时校验或完整类型生成器。外部 `$ref` 需先打包到单文件；未解析引用会展示未知。
- 页面不生成 Fetch / TypeScript / 示例 JSON；前端按自己仓库的请求封装和类型约定实现。
- 文档解析 OpenAPI 声明的 security，包括全局继承与接口级覆盖。未声明时显示待确认，不能从“缺失”推断匿名。
- 旧的 `heroNotes` 保持 HTML 片段行为，只用于你自己维护的可信配置；新说明优先用纯文本 `integration`。
- CSS / JS 源文件位于 `assets/`，生成时内联；最终 HTML 不依赖其它文件或网络资源，复制这一份即可交付。

## Agent 交接配置

```json
"agent": {
  "task": "把本次变更接入已有订单管理页面，沿用项目当前的请求和类型约定。"
}
```

`task` 可选；没有配置时仍会生成「交给 Agent」模块，任务可在 HTML 内临时填写，不会修改源配置或上传资料。

- 默认范围是「本次变更的接口」；也可选择全部、模块、调用流程或单接口。接口页的入口会预选当前接口。
- Markdown 任务包可直接粘贴给前端 Agent，或下载 `.md`；JSON 契约包包含 `schemaVersion`、任务、变更清单、模块内精确 OpenAPI 与待确认项。
- 任务包不包含通用编码约束、验收模板或项目接入约定；接收方 Agent 按其前端仓库规范执行。
- 每个模块独立保留 OpenAPI，避免跨模块相同路径互相覆盖。只导出所选方法，并递归携带被引用的 components；路径级参数合并到接口参数，接口级覆盖仍生效。
- 全局 security 与接口级覆盖保留原语义。未解析引用、未声明鉴权或错误响应会进入待确认项。
- 不注入生成示例或猜测字段。原始示例、说明可能包含业务数据，分享前应核对内容；模块不会读取本机令牌或发出业务请求。
- 下载与复制均在浏览器本地完成，最终仍是一份离线 HTML。
