---
name: api-exporter
description: 静态扫描 Spring Boot Java 源码，列出或筛选端点、生成 OpenAPI 3.0 JSON，并按用户要求同步 Apifox。适用于导出全部或指定接口、查找后端端点及导入 Apifox；生成可阅读的 HTML 对接文档使用 api-doc-html。
---

# api-exporter

Static scan of Spring Boot source → OpenAPI 3.0 → Apifox import.
tree-sitter based: never start the app, never needs a classpath or Maven/Gradle.

The CLI source ships inside this skill at `tool/`; all paths below are relative to this skill's directory.

## 1. Build the CLI (once)

```bash
cd <skill-dir>/tool && cargo build --release
```

The binary lands at `<skill-dir>/tool/target/release/api-exporter`. Rebuild when `tool/src/` is newer than the binary. Export a shorthand for the rest of the session:

```bash
BIN=<skill-dir>/tool/target/release/api-exporter
"$BIN" --project <target-project> --list
```

- `<target-project>`: any Spring Boot project with `src/main/java` (e.g. `../sample-spring-project`). Ask which project when several are near.
- The tool only reads the target project; it writes there just when you leave `--out` at its default.

## 2. Discover before filtering

```bash
"$BIN" --project <target-project> --list
```

Prints `#  方法  路径  分组  处理器  摘要`. Copy only the method and path into `--include` (for example, `GET /user/{id}`), not the full table row.
`--list` never writes files; combine it with filters to preview an export first.

## 3. Select the specified interfaces

`--include <spec>` (repeatable, OR-ed) and `--exclude <spec>` (wins over include):

| spec | matches |
| --- | --- |
| `path:/user/{id}`、`/user/**` | exact path, or glob with `*`/`**`/`?` |
| `controller:<类名关键词>` | controller simple name / FQN (substring, case-insensitive) |
| `tag:<分组关键词>` | `@Api(tags)` / `@ApiOperation(tags)` group (substring, case-insensitive) |
| `http:GET` | HTTP method |
| `name:<方法名关键词>` | Java method name / operationId (substring, case-insensitive) |
| `GET /user/{id}` | HTTP method + path, i.e. exactly one endpoint |
| `GET` | bare HTTP method, same as `http:GET` |

Rules that bite:

- **Quote any spec containing `*`** — zsh expands it before the tool sees it: `--include 'path:/user/**'`.
- A path spec without wildcards is an **exact match**; a prefix needs `/**` (`/user` matches only `/user`; `/user/**` also matches `/user` and everything below).
- Long lists: `--endpoints-file endpoints.txt`, one spec per line, `#` comments allowed.
- Legacy `--include-tag <tag>` still works, same as `--include tag:<tag>`.

## 4. Generate and verify

```bash
"$BIN" --project <target-project> --dry-run --profile dev \
  --include 'path:/order/**' --exclude 'http:DELETE' \
  --out /tmp/openapi.json
```

- Always pass `--dry-run` for file-only generation: the CLI reads `APIFOX_TOKEN` and `APIFOX_PROJECT_ID` from the environment and otherwise may push automatically. This flag still writes the output file.
- Default output: `<project>/build/apifox/openapi.json`; pass `--out` when the target repo must stay clean.
  `--out` takes a file path, or a directory (existing, or ending with `/`) to write `<dir>/openapi.json`; missing directories are created.
- Read the summary block: `接口数量` is the count **after** filtering, plus `数据模型`, `context-path`, `servers`. Zero interfaces requires checking filters, source root and scanner support — go back to `--list`, and do not claim a complete export.
- `context-path` / `port` are read from `src/main/resources/**/application{-profile}.*`; override with `--profile`, `--context-path`, `--port`, `--base-url`.
- Verify the document before shipping:

```bash
python3 <skill-dir>/scripts/check_document.py /tmp/openapi.json
```

It reports paths/operations/schemas and fails on dangling `$ref`, duplicate `operationId`, missing 2xx responses, or path parameters not in the path template.

## 5. Push to Apifox

Only when the user asked for Apifox (plain 生成/导出 means generate the file only). First generate with `--dry-run`, verify that document and inspect the target project, filters and merge mode. Reuse those same export arguments for the push:

```bash
"$BIN" --project <target-project> --out /tmp/openapi.json \
  --include 'path:/order/**' \
  --apifox-project <id> --apifox-mode AUTO_MERGE \
  [--apifox-folder <id>] [--apifox-branch <id>]
```

- Prefer an existing `$APIFOX_TOKEN`; do not echo credentials or place a real token in logged commands. Token: `--apifox-token` or `$APIFOX_TOKEN`; project: `--apifox-project` or `$APIFOX_PROJECT_ID`. Both are required, otherwise it just writes the file.
- Modes: `AUTO_MERGE` (default, matches by method+path), `OVERWRITE_EXISTING`, `KEEP_EXISTING`, `CREATE_NEW`.
- `--delete-unmatched` deletes remote endpoints/models missing from the scan. Use only with explicit authorization for that deletion; a subset export can make unrelated remote endpoints look unmatched.
- If a push fails, inspect the failure before retrying. Do not blindly repeat `CREATE_NEW` or destructive imports, which may duplicate or delete resources.
- `--dry-run` skips the push but still writes the file.
- Success: `[apifox] HTTP 200 | 新增接口 …`; failure: `[error] 推送失败: …` with the raw response body — usually a bad token, project id, or folder id.

## Gotchas

- Static analysis is not runtime verification. Scanner limitations, parse failures and incomplete schemas must be disclosed; do not invent missing types or claim all runtime routes were found.

- Nothing matched after filtering: path specs are exact — retry with `--list` and `'path:/prefix/**'`.
- `ResponseEntity<Object>` and friends produce no response schema unless the method carries `@ApiResponse(response = X.class)` — expected, not a bug.
- Full flag table, import options, and what the scanner does/does not recognize: [references/cli.md](references/cli.md).
- `tool/` is a snapshot of the api-exporter project; keep both in sync when either side changes.
