---
name: api-doc-html
description: 把 OpenAPI 3 JSON 渲染成给前端对接用的单文件 HTML 接口文档（左侧导航+搜索、请求/响应字段表、嵌套结构、示例 JSON、枚举附录、按模块分 Base URL、可打印）。当用户要"导出/生成接口对接文档""给前端一份接口清单""按模块/控制器导出 API 文档""把 OpenAPI 变成 HTML"，或要求接口文档包含字段说明、示例、枚举取值时使用。通常先用 api-exporter 扫描 Spring Boot 项目产出 OpenAPI JSON，再用本 skill 渲染 HTML。
---

# api-doc-html

把 OpenAPI 3 JSON 渲染成**单文件、离线可用**的 HTML 接口对接文档。

## 前置：拿到 OpenAPI JSON

优先用 `api-exporter` skill 扫描 Spring Boot 源码（不启动应用）。典型命令：

```bash
BIN=<api-exporter-skill>/tool/target/release/api-exporter
# 按控制器导出全部接口
"$BIN" --project /path/to/repo --include 'controller:OrderController' --out /tmp/orders.json
# 只要其中几条（每行一条 spec）
"$BIN" --project /path/to/repo --endpoints-file endpoints.txt --out /tmp/subset.json
```

也可以直接用任何现成的 OpenAPI 3 JSON。

## 工作流

1. **确认范围**：要哪些模块/接口、给谁看（管理端/下单端/客户端）、输出路径、是否需要枚举附录。
   - 多个模块（如管理端 + 下单端）→ 每个模块一份 JSON，文档里按模块分节、各自 Base URL。
2. **导出 JSON**（见上，按需过滤接口）。
3. **写配置**：推荐配置文件，便于复现和以后更新；字段见 [references/config.md](references/config.md)。
   最小配置：

   ```json
   {
     "title": "订单模块 接口对接清单",
     "out": "./订单模块-接口对接.html",
     "srcRoots": ["/path/to/repo/src/main/java"],
     "modules": [
       {"title": "订单模块（管理端）", "openapi": "/tmp/orders.json", "note": "响应包装 {success,message,data}"}
     ],
     "paramDocs": {"status": "1 草稿 / 2 已完成"},
     "enums": [{"title": "订单模块", "rows": [["status", "1 草稿 / 2 已完成"]]}]
   }
   ```

4. **生成**：

   ```bash
   python3 scripts/gen_api_doc.py --config doc-config.json
   ```

   临时用也可以不开配置文件：

   ```bash
   python3 scripts/gen_api_doc.py --title "订单接口" --out /tmp/order.html \
     --module "订单=/tmp/order.json|下单端" \
     --module "商品=/tmp/product.json" \
     --src /path/to/repo/src/main/java
   ```

5. **交付**：脚本会打印每个模块的接口数、总数和自检结果（锚点/标签/`$ref`）。把 HTML 路径给用户，并说明覆盖范围、Base URL、未包含的模块。

## 关键点

- **字段说明来自 Java Javadoc**：`srcRoots` 必填（可多个仓库）。脚本会按 `@JsonProperty("x")` 或字段名映射；没有注释的字段显示 `—`。
- **Base URL 自动取 OpenAPI 的 `servers[0].url`**；同一份文档里不同模块可以用不同 Base，复制按钮会拼对应模块的地址。需要覆盖时在模块里加 `baseUrl`。
- **自动跳过 Java 常量**：api-exporter 会把 `static final` 字段也扫成属性（如 `DATE_FORMATTER`），脚本已过滤。
- **无响应体的接口**（文件下载、`ResponseEntity<Object>`）会显示"文件流 / 无 JSON 响应体"或只显示类型，不报错。
- **分页/包装**：脚本不猜业务包装，包装结构以 JSON 为准；在模块 `note` 或 `heroNotes` 里写清楚（例如 `{success,message,data}` 与 `{total,data,page,pageSize}`）。
- **参数说明**：OpenAPI 里没有描述时，用 `paramDocs` 补（脚本内置少量通用项：page/pageSize/companyId/operator_id 等）。
- **枚举/取值**：`enums` 手写，按模块分卡片；不要指望从 Java 枚举自动推导。

## 输出特性

> 生成的 HTML 含接口路径、字段与业务语义，默认只放本地/内部分享；不要提交到公开仓库。

左侧导航 + 关键词过滤、每个接口复制完整 URL、请求参数表、请求/响应字段表（嵌套展开 3 层）、请求/响应示例 JSON、枚举附录、打印样式、无外部依赖（可直接发给前端）。

## 常见问题

- **字段说明全是 `—`**：`srcRoots` 没传或路径不对；确认指向 `src/main/java`。
- **接口数不对**：`--include` 的 path 是精确匹配，前缀要用 `path:/xxx/**`；先用 api-exporter `--list` 预览。
- **模块标题里的中文 id**：脚本会把标题 slug 化生成锚点，无需手动处理。
