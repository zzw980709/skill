#!/usr/bin/env bash
# 一条命令：api-exporter 扫描 Spring Boot 源码 -> 生成单文件 HTML 接口文档。
# 适合日常“给我导一份接口对接文档”的场景；复杂配置仍可直接用 gen_api_doc.py --config。
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT=""
OUT=""
TITLE="接口对接文档"
PROFILE=""
BASE_URL=""
NOTE=""
EXPORTER="${API_EXPORTER_BIN:-}"
KEEP_OPENAPI=""
ALL=0
SRC_DIRS=()
INCLUDES=()
EXCLUDES=()
BASE_REF=""
BASE_FILE=""
BASELINE_LABEL=""
BASELINE_DATE=""

usage() {
  cat <<'EOF'
用法:
  gen_from_project.sh --project <repo> --out <file.html> [选项] --include <spec>...

必填:
  --project <dir>        Spring Boot 项目根目录（含 src/main/java）
  --out <file>           输出 HTML 路径
  --include <spec>       api-exporter 过滤条件，可重复；--all 表示全部接口
                        例: 'controller:OrderController'、'GET /orders/{orderId}'

可选:
  --all                  导出全部接口（等价于不加 include）
  --exclude <spec>       排除条件，可重复
  --title <text>         文档标题
  --src <dir>            Java 源码根目录，可重复；默认 <project>/src/main/java
  --profile <name>       读取 application-<name>.yaml 的 context-path/port
  --base-url <url>       覆盖文档中的 Base URL
  --note <text>          模块说明
  --exporter <path>      api-exporter 可执行文件（默认自动查找/环境变量 API_EXPORTER_BIN）
  --keep-openapi <file>  保留中间 OpenAPI JSON 到指定路径
  --base <ref>           变更基线 git ref；'pro' 表示最近一个 v*-backend 生产 tag
  --baseline <file>      变更基线 OpenAPI JSON（与 --base 二选一）
  --baseline-label <text> 基线显示名，默认生产环境 pro 或 基线 <ref>
  --baseline-date <text> 基线日期，默认取 ref 提交日期
  -h, --help             显示帮助
EOF
}

die() { echo "[error] $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project|--out|--title|--src|--profile|--base-url|--note|--exporter|--keep-openapi|--include|--exclude|--base|--baseline|--baseline-label|--baseline-date)
      [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || die "$1 缺少参数值"
      ;;
  esac
  case "$1" in
    --project) PROJECT="${2:-}"; shift 2 ;;
    --out) OUT="${2:-}"; shift 2 ;;
    --title) TITLE="${2:-}"; shift 2 ;;
    --src) SRC_DIRS+=("${2:-}"); shift 2 ;;
    --profile) PROFILE="${2:-}"; shift 2 ;;
    --base-url) BASE_URL="${2:-}"; shift 2 ;;
    --note) NOTE="${2:-}"; shift 2 ;;
    --exporter) EXPORTER="${2:-}"; shift 2 ;;
    --keep-openapi) KEEP_OPENAPI="${2:-}"; shift 2 ;;
    --include) INCLUDES+=("${2:-}"); shift 2 ;;
    --exclude) EXCLUDES+=("${2:-}"); shift 2 ;;
    --base) BASE_REF="${2:-}"; shift 2 ;;
    --baseline) BASE_FILE="${2:-}"; shift 2 ;;
    --baseline-label) BASELINE_LABEL="${2:-}"; shift 2 ;;
    --baseline-date) BASELINE_DATE="${2:-}"; shift 2 ;;
    --all) ALL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "未知参数: $1（--help 查看用法）" ;;
  esac
done

[[ -n "$PROJECT" ]] || die "缺少 --project"
[[ -n "$OUT" ]] || die "缺少 --out"
if [[ "$ALL" -eq 1 && ${#INCLUDES[@]} -gt 0 ]]; then
  die "--all 与 --include 不能同时使用"
fi
[[ "$ALL" -eq 1 || ${#INCLUDES[@]} -gt 0 ]] || die "请指定 --include，或用 --all 明确导出全部接口"
CALLER_PWD="$(pwd)"
PROJECT="$(cd "$PROJECT" && pwd)" || die "项目目录不存在: $PROJECT"
[[ "$OUT" = /* ]] || OUT="$CALLER_PWD/$OUT"
[[ -n "$KEEP_OPENAPI" && "$KEEP_OPENAPI" != /* ]] && KEEP_OPENAPI="$CALLER_PWD/$KEEP_OPENAPI"
for i in "${!SRC_DIRS[@]}"; do
  [[ "${SRC_DIRS[$i]}" = /* ]] || SRC_DIRS[$i]="$CALLER_PWD/${SRC_DIRS[$i]}"
done
[[ -d "$PROJECT/src/main/java" ]] || die "$PROJECT 下找不到 src/main/java"

if [[ -n "$BASE_REF" && -n "$BASE_FILE" ]]; then
  die "--base 与 --baseline 不能同时使用"
fi
BASE_KIND=""
if [[ -n "$BASE_REF" ]]; then
  if [[ "$BASE_REF" = "pro" ]]; then
    BASE_KIND="pro"
    BASE_REF="$(git -C "$PROJECT" tag --list 'v*-backend' --sort=-v:refname | sed -n '1p')"
    [[ -n "$BASE_REF" ]] || die "找不到形如 v*-backend 的生产 tag"
  fi
  git -C "$PROJECT" rev-parse --verify "$BASE_REF^{commit}" >/dev/null 2>&1 || die "git ref 不存在: $BASE_REF"
  [[ -n "$BASELINE_DATE" ]] || BASELINE_DATE="$(git -C "$PROJECT" log -1 --format=%cs "$BASE_REF" 2>/dev/null || true)"
  if [[ -z "$BASELINE_LABEL" ]]; then
    if [[ "$BASE_KIND" = "pro" ]]; then
      BASELINE_LABEL="生产环境 pro"
    else
      BASELINE_LABEL="基线 $BASE_REF"
    fi
  fi
fi
if [[ -n "$BASE_FILE" ]]; then
  [[ "$BASE_FILE" = /* ]] || BASE_FILE="$CALLER_PWD/$BASE_FILE"
  [[ -f "$BASE_FILE" ]] || die "基线文件不存在: $BASE_FILE"
  [[ -n "$BASELINE_LABEL" ]] || BASELINE_LABEL="基线 $(basename "$BASE_FILE")"
  [[ -n "$BASELINE_DATE" ]] || BASELINE_DATE="$(date -r "$BASE_FILE" +%F 2>/dev/null || date +%F)"
fi

if [[ -z "$EXPORTER" ]]; then
  for candidate in \
    "$SKILL_DIR/../api-exporter/tool/target/release/api-exporter" \
    "$HOME/.codex/skills/api-exporter/tool/target/release/api-exporter" \
    "$HOME/.claude/skills/api-exporter/tool/target/release/api-exporter" \
    "$HOME/.agents/skills/api-exporter/tool/target/release/api-exporter" \
    "$HOME/.config/opencode/skills/api-exporter/tool/target/release/api-exporter"; do
    if [[ -x "$candidate" ]]; then EXPORTER="$candidate"; break; fi
  done
fi
if [[ -z "$EXPORTER" ]]; then
  EXPORTER="$(command -v api-exporter || true)"
fi
[[ -n "$EXPORTER" && -x "$EXPORTER" ]] || die "找不到 api-exporter，可设置 API_EXPORTER_BIN 或 --exporter"

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/api-doc-html.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT
OPENAPI_JSON="$TMP_DIR/openapi.json"

EXPORT_ARGS=(--project "$PROJECT" --out "$OPENAPI_JSON" --dry-run)
[[ -n "$PROFILE" ]] && EXPORT_ARGS+=(--profile "$PROFILE")
if [[ ${#INCLUDES[@]} -gt 0 ]]; then
  for spec in "${INCLUDES[@]}"; do EXPORT_ARGS+=(--include "$spec"); done
fi
if [[ ${#EXCLUDES[@]} -gt 0 ]]; then
  for spec in "${EXCLUDES[@]}"; do EXPORT_ARGS+=(--exclude "$spec"); done
fi

echo "[1/2] 扫描项目生成 OpenAPI ..."
"$EXPORTER" "${EXPORT_ARGS[@]}" >/dev/null

if [[ -n "$KEEP_OPENAPI" ]]; then
  mkdir -p "$(dirname "$KEEP_OPENAPI")"
  cp "$OPENAPI_JSON" "$KEEP_OPENAPI"
fi

BASELINE_JSON=""
if [[ -n "$BASE_REF" ]]; then
  echo "[baseline] 导出基线 $BASE_REF ..."
  BASE_DIR="$TMP_DIR/base"
  mkdir -p "$BASE_DIR"
  git -C "$PROJECT" archive "$BASE_REF" | tar -x -C "$BASE_DIR"
  [[ -d "$BASE_DIR/src/main/java" ]] || die "基线 $BASE_REF 下找不到 src/main/java"
  BASELINE_JSON="$TMP_DIR/baseline.json"
  BASE_EXPORT_ARGS=(--project "$BASE_DIR" --out "$BASELINE_JSON" --dry-run)
  [[ -n "$PROFILE" ]] && BASE_EXPORT_ARGS+=(--profile "$PROFILE")
  if [[ ${#INCLUDES[@]} -gt 0 ]]; then
    for spec in "${INCLUDES[@]}"; do BASE_EXPORT_ARGS+=(--include "$spec"); done
  fi
  if [[ ${#EXCLUDES[@]} -gt 0 ]]; then
    for spec in "${EXCLUDES[@]}"; do BASE_EXPORT_ARGS+=(--exclude "$spec"); done
  fi
  "$EXPORTER" "${BASE_EXPORT_ARGS[@]}" >/dev/null
  python3 - "$BASELINE_JSON" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1], encoding='utf-8'))
if not (doc.get('paths') or {}):
    print('[warn] 基线契约没有接口；当前范围将全部视为新增。', file=sys.stderr)
PY
fi
if [[ -n "$BASE_FILE" ]]; then
  BASELINE_JSON="$BASE_FILE"
fi

if [[ ${#SRC_DIRS[@]} -eq 0 ]]; then
  SRC_DIRS=("$PROJECT/src/main/java")
fi

CONFIG_JSON="$TMP_DIR/config.json"
PROJECT="$PROJECT" OUT="$OUT" TITLE="$TITLE" NOTE="$NOTE" BASE_URL="$BASE_URL" \
OPENAPI_JSON="$OPENAPI_JSON" CONFIG_JSON="$CONFIG_JSON" \
BASELINE_JSON="$BASELINE_JSON" BASELINE_LABEL="$BASELINE_LABEL" BASELINE_DATE="$BASELINE_DATE" \
SRC_JSON="$(printf '%s\n' "${SRC_DIRS[@]}")" \
python3 - <<'PY'
import json
import os

srcs = [line for line in os.environ["SRC_JSON"].splitlines() if line.strip()]
module = {
    "title": os.environ["TITLE"],
    "openapi": os.environ["OPENAPI_JSON"],
}
if os.environ.get("NOTE"):
    module["note"] = os.environ["NOTE"]
if os.environ.get("BASE_URL"):
    module["baseUrl"] = os.environ["BASE_URL"]
if os.environ.get("BASELINE_JSON"):
    module["baseline"] = os.environ["BASELINE_JSON"]

config = {
    "title": os.environ["TITLE"],
    "out": os.environ["OUT"],
    "srcRoots": srcs,
    "modules": [module],
}
if os.environ.get("BASELINE_JSON"):
    config["baselineLabel"] = os.environ.get("BASELINE_LABEL") or "生产环境"
    config["baselineDate"] = os.environ.get("BASELINE_DATE") or ""
with open(os.environ["CONFIG_JSON"], "w", encoding="utf-8") as f:
    json.dump(config, f, ensure_ascii=False, indent=2)
PY

echo "[2/2] 渲染 HTML ..."
python3 "$SKILL_DIR/scripts/gen_api_doc.py" --config "$CONFIG_JSON"
