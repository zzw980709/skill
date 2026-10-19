# 配置文件参考

`gen_api_doc.py --config <file>.json` 的完整字段。相对路径以配置文件所在目录为基准。

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
| `srcRoots` | 强烈建议 | Java 源码根目录数组，用于提取 DTO 字段 Javadoc；可传多个仓库 |
| `modules` | 是 | 模块数组，见下 |
| `heroNotes` | 否 | 顶部说明的 HTML 片段数组（例如 Base URL、响应包装、日期格式） |
| `paramDocs` | 否 | 参数名 → 说明，覆盖/扩展内置默认 |
| `fieldDocs` | 否 | `"SchemaName.prop": "说明"`，用于补 Javadoc 缺失的字段 |
| `enums` | 否 | 枚举附录，见下 |

## modules

```json
{
  "title": "商品模块（客户端）",
  "openapi": "altamira.json",
  "note": "响应包装 {data}；按客户端账号传 user_id",
  "baseUrl": "http://localhost:8080/api"
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `title` | 是 | 模块标题，同时用于侧栏分组与锚点（自动 slug） |
| `openapi` | 是 | OpenAPI 3 JSON 路径 |
| `note` | 否 | 模块说明，显示在模块标题下 |
| `baseUrl` | 否 | 覆盖 `servers[0].url`；用于复制按钮与模块头展示 |

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

命令行模式不支持 `heroNotes` / `paramDocs` / `fieldDocs` / `enums`；需要这些就用配置文件。
