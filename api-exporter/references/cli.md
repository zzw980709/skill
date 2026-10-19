# api-exporter CLI reference

## Full flag list

| flag | default | meaning |
| --- | --- | --- |
| `--project <dir>` | `.` | project root; must contain `src/main/java` |
| `--profile <name>` | `dev` | reads `application-{profile}.yaml\|yml\|properties` |
| `--config <file>` | – | extra yaml/properties, applied after profile config |
| `--context-path <p>` | from config | override `server.servlet.context-path` |
| `--base-url <url>` | – | override `servers.url` entirely (top priority) |
| `--scheme` / `--host` / `--port` | `http` / `localhost` / from config (8080) | build `servers.url` |
| `--out <path>` | `<project>/build/apifox/openapi.json` | file path, or a directory (existing / trailing `/`) → writes `<dir>/openapi.json`; missing dirs are created |
| `--title <t>` | project folder name | `info.title` |
| `--api-version <v>` | `1.0.0` | `info.version` |
| `--prepend-context-path` | off | put context-path into every path instead of the server URL |
| `--list` | off | print the endpoint inventory and exit (no files written) |
| `--include <spec>` | – | keep matching endpoints (repeatable, OR) |
| `--exclude <spec>` | – | drop matching endpoints (repeatable, OR, wins over include) |
| `--endpoints-file <file>` | – | read `--include` specs from a file |
| `--include-tag <tag>` | – | legacy shortcut for `--include tag:<tag>` |
| `--apifox-token` | `$APIFOX_TOKEN` | Apifox system token |
| `--apifox-project` | `$APIFOX_PROJECT_ID` | Apifox project id |
| `--apifox-mode` | `AUTO_MERGE` (`$APIFOX_MODE`) | `OVERWRITE_EXISTING` / `AUTO_MERGE` / `KEEP_EXISTING` / `CREATE_NEW` |
| `--apifox-folder <id>` | – | target endpoint folder (`targetEndpointFolderId`) |
| `--apifox-branch <id>` | – | target branch (`targetBranchId`) |
| `--delete-unmatched` | off | `deleteUnmatchedResources: true` — deletes remote items missing from the scan |
| `--dry-run` | off | generate the file, skip the Apifox push |
| `-v, --verbose` | off | extra logs + full error chain; also prints the parsed filter |

## Spec grammar

```
SPEC := [HTTP_METHOD whitespace] (PREFIX ":" VALUE | VALUE)
HTTP_METHOD := GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|TRACE|CONNECT   (case-insensitive)
PREFIX := path|url | controller|class | tag|group | http|method | name
```

- No recognized prefix ⇒ the whole spec is a **path** pattern. Unknown prefixes (e.g. `/a:b/c`) are also treated as paths, never errors.
- `http:`/`method:` value must be a real HTTP method, otherwise the run aborts with the allowed list.
- A known prefix with an empty value (`tag:`) aborts.
- Bare `GET` ≡ `http:GET` (matches all paths).
- Matching kinds: `path` exact-or-glob; `controller`/`tag`/`name` case-insensitive substring; `*` in those three means "any"; `http` is exact.

### Path globs

- No `*` / `?` ⇒ exact string equality after normalization (leading `/` added, trailing `/` trimmed).
- `*` matches within one segment (never crosses `/`); `**` crosses segments; `?` is one non-`/` char.
- `/user/**` additionally matches `/user` itself.

## endpoints-file format

```
# full-line comment
// also a full-line comment
GET  /user/{id}          # inline comment needs the space before '#'
path:/order/**
tag:支付
```

- Blank lines are skipped. Errors report `file 第 N 行`.
- `--include`, `--exclude` and the file may be combined; `only` entries are OR-ed, excludes always win.

## Apifox push details

- `POST https://api.apifox.com/v1/projects/{projectId}/import-openapi?locale=zh-CN`, header `X-Apifox-Api-Version: 2024-03-28`.
- `--apifox-mode` sets both `endpointOverwriteBehavior` and `schemaOverwriteBehavior`.
- Honors `HTTPS_PROXY` / `https_proxy` for the request.
- Success prints `[apifox] HTTP 200 | 新增接口 N, 更新接口 N, 忽略 N, 失败 N | 新增模型 N, 更新模型 N` and exits 0 even when some items failed — check the counters.
- Non-2xx prints `[error] 推送失败: <raw body>` and exits 1. Common causes: invalid token, wrong project id, wrong folder/branch id, no permission.

## What the scanner recognizes

- `@RestController`/`@Controller`, class-level `@RequestMapping`, method mappings `@GetMapping/PostMapping/PutMapping/PatchMapping/DeleteMapping/RequestMapping` (multi-value, multi-method).
- `server.servlet.context-path` and `server.port` from `application{,-profile}.yaml|yml|properties` (multi-doc `spring.config.activate.on-profile` supported).
- Params: `@RequestParam`, `@PathVariable`, `@RequestHeader`, `@RequestPart`, `@RequestBody`, `@ModelAttribute` and bare DTO query objects (DTO fields are flattened into query params).
- Bodies: JSON, `multipart/form-data` (`MultipartFile`/`Part`), non-GET `@ModelAttribute` → `application/x-www-form-urlencoded`.
- Models: field types, `List/Map/array/enum`, generics (`DataResponse<T>` inlined), superclass fields, `@NotNull` etc. → required, `@JsonProperty` names, `@ApiModelProperty` description/example, `@JsonIgnore`/`static`/`transient` skipped.
- Javadoc/Swagger: `@Api(tags)`, `@ApiOperation(value, notes, tags)`, `@ApiImplicitParam(s)`, `@ApiResponse(response = X.class)`, `@Deprecated`.
- Output only keeps `components.schemas` reachable from the exported endpoints.

## Known limits (do not "fix" by hand)

- `ResponseEntity<Object>` / erased generics have no response schema unless `@ApiResponse(response = ...)` is present.
- `@RequestMapping` without `method` is treated as GET.
- Custom composed annotations (meta-annotated `@GetMapping`) and Spring functional routes are not recognized.
- Generic wrapper classes are inlined, not emitted as separate models.
