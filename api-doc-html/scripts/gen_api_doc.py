#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenAPI 3 JSON -> 单文件 HTML 接口对接文档。

用法：
    python3 gen_api_doc.py --config doc.json
    python3 gen_api_doc.py --title "xx 接口清单" --out out.html \
        --module "模块A=/path/a.json" --module "模块B=/path/b.json|模块备注" \
        --src /repo/src/main/java

配置文件字段见 references/config.md。
"""
import argparse
import html
import json
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

METHOD_ORDER = {"GET": 0, "POST": 1, "PUT": 2, "PATCH": 3, "DELETE": 4}

# 通用查询参数说明（可按需在配置里 paramDocs 覆盖/扩展）
DEFAULT_PARAM_DOCS = {
    "page": "页码，从 1 开始",
    "pageSize": "每页条数",
    "per_page": "每页条数",
    "companyId": "账套",
    "company_id": "账套",
    "operator_id": "操作人 id（写操作日志）",
    "activityId": "活动 id",
    "orderId": "订单 id",
    "status": "状态（取值见接口说明/附录）",
    "itemNo": "货号（模糊，不分大小写）",
    "searchVal": "编号 / 名称（模糊）",
    "user": "用户 id（客户端）",
    "user_id": "客户端/小程序：账号 id（后端聚合该账号绑定的所有客户）",
    "erp_user_no": "销售端：指定单个 ERP 客户号",
}

PLACEHOLDERS = {"string": "string", "integer": 0, "number": 0, "boolean": True}

FIELD_DOCS = {}
PARAM_DOCS = dict(DEFAULT_PARAM_DOCS)
EXTRA_FIELD_DOCS = {}
MODULES = []
TITLE = "接口对接清单"
OUT = Path("api-doc.html")
HERO_NOTES = []
ENUMS = []


# ------------------------------------------------------------------ 源码注释

def clean_doc(lines):
    text = "\n".join(lines)
    text = re.sub(r"^\s*/\*\*", "", text)
    text = re.sub(r"\*/\s*$", "", text)
    out = []
    for line in text.splitlines():
        line = re.sub(r"^\s*\*\s?", "", line).strip()
        if not line or line.startswith("@author") or line.startswith("@date"):
            continue
        out.append(line)
    return " ".join(out).strip()


def extract_field_docs(src_roots):
    """扫描 Java 源码：class -> {jsonProperty: javadoc}。"""
    docs = {}
    for root in src_roots:
        root = Path(root)
        if not root.exists():
            print(f"[warn] 源码目录不存在，字段说明将缺失: {root}", file=sys.stderr)
            continue
        for path in root.rglob("*.java"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            current_class = None
            pending_doc = None
            pending_json = None
            in_doc = False
            doc_lines = []
            for raw in text.splitlines():
                line = raw.strip()
                if in_doc:
                    doc_lines.append(line)
                    if "*/" in line:
                        in_doc = False
                        pending_doc = clean_doc(doc_lines)
                    continue
                if line.startswith("/**"):
                    if line.endswith("*/"):
                        pending_doc = clean_doc([line])
                    else:
                        in_doc = True
                        doc_lines = [line]
                    continue
                m = re.search(r"\b(?:class|enum)\s+(\w+)", line)
                if m:
                    current_class = m.group(1)
                    docs.setdefault(current_class, {})
                    pending_doc = None
                    pending_json = None
                    continue
                m = re.search(r'@JsonProperty\("([^"]+)"\)', line)
                if m:
                    pending_json = m.group(1)
                    continue
                m = re.match(r"(?:private|public|protected)\s+[^;=()]+?\s+(\w+)\s*(?:=|;)", line)
                if m and current_class:
                    prop = pending_json or m.group(1)
                    if pending_doc:
                        docs[current_class].setdefault(prop, pending_doc)
                    pending_doc = None
                    pending_json = None
    return docs


def is_constant(name):
    """跳过 Java 常量：api-exporter 会把 static final 字段也扫成属性。"""
    return bool(re.fullmatch(r"[A-Z][A-Z0-9_]*", name or ""))


def field_desc(schema_name, prop):
    return EXTRA_FIELD_DOCS.get(f"{schema_name}.{prop}") or FIELD_DOCS.get(schema_name, {}).get(prop, "")


# ------------------------------------------------------------------ schema

def ref_name(schema):
    return schema["$ref"].split("/")[-1] if isinstance(schema, dict) and "$ref" in schema else None


def type_label(schema):
    if not schema:
        return "any"
    if "$ref" in schema:
        return ref_name(schema)
    t = schema.get("type")
    if t == "array":
        return f"array&lt;{type_label(schema.get('items', {}))}&gt;"
    if t in ("integer", "number") and schema.get("format"):
        return f"{t}({schema['format']})"
    if t == "string" and schema.get("format") == "binary":
        return "file"
    if schema.get("enum"):
        return f"{t} · enum"
    return t or "object"


def example(schema, comps, depth=0, stack=(), prop=""):
    if not schema or depth > 8:
        return None
    if "$ref" in schema:
        name = ref_name(schema)
        if name in stack:
            return "{}"
        return example(comps.get(name, {}), comps, depth + 1, stack + (name,), prop)
    if schema.get("enum"):
        return schema["enum"][0]
    t = schema.get("type")
    if t == "array":
        item = example(schema.get("items", {}), comps, depth + 1, stack, prop)
        return [] if item is None else [item]
    if t == "object" or "properties" in schema:
        props = schema.get("properties") or {}
        return {k: example(v, comps, depth + 1, stack, k)
                for k, v in props.items() if not is_constant(k)} if props else {}
    if t == "string" and re.search(r"(date|time)", prop or "", re.I):
        return "2026-10-01T00:00:00+08:00"
    return PLACEHOLDERS.get(t, "string")


def pretty(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------ html

def esc(text):
    return html.escape(str(text), quote=True)


def render_fields(schema, comps, schema_name, depth=0, stack=()):
    if not schema:
        return ""
    if "$ref" in schema:
        name = ref_name(schema)
        if name in stack:
            return ""
        return render_fields(comps.get(name, {}), comps, name, depth, stack + (name,))
    props = schema.get("properties") or {}
    if not props:
        return ""
    required = set(schema.get("required") or [])
    rows = []
    for prop, pschema in props.items():
        if is_constant(prop):
            continue
        desc = field_desc(schema_name, prop) or (pschema.get("description") if isinstance(pschema, dict) else "")
        desc_html = esc(desc) if desc else '<span class="muted">—</span>'
        nested = ""
        target = pschema
        if isinstance(target, dict) and target.get("type") == "array":
            target = target.get("items", {})
        tname = ref_name(target)
        if tname and tname not in stack and depth < 3:
            nested = render_fields(comps.get(tname, {}), comps, tname, depth + 1, stack + (tname,))
        rows.append(
            f'<div class="frow d{depth}">'
            f'<div class="fname"><code>{esc(prop)}</code>'
            + ('<span class="req">*</span>' if prop in required else "")
            + "</div>"
            f'<div class="ftype">{type_label(pschema)}</div>'
            f'<div class="fdesc">{desc_html}</div>'
            "</div>"
            + (f'<div class="nested">{nested}</div>' if nested else "")
        )
    head = ('<div class="frow fhead"><div class="fname">字段</div>'
            '<div class="ftype">类型</div><div class="fdesc">说明</div></div>')
    return f'<div class="fields">{head}{"".join(rows)}</div>'


def render_params(params, comps):
    if not params:
        return ""
    rows = []
    for p in params:
        sch = p.get("schema") or {}
        desc = p.get("description") or PARAM_DOCS.get(p.get("name"), "")
        rows.append(
            "<tr>"
            f'<td><code>{esc(p.get("name"))}</code></td>'
            f'<td>{esc(p.get("in"))}</td>'
            f'<td>{type_label(sch)}</td>'
            f'<td>{"是" if p.get("required") else "否"}</td>'
            f'<td>{esc(desc) if desc else "<span class=\'muted\'>—</span>"}</td>'
            "</tr>"
        )
    return ('<h4>请求参数</h4><table class="grid"><thead><tr>'
            "<th>参数</th><th>位置</th><th>类型</th><th>必填</th><th>说明</th>"
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table>')


def response_section(op, comps):
    parts = []
    for code in sorted(op.get("responses") or {}):
        r = op["responses"][code]
        desc = r.get("description") or ""
        schema = (((r.get("content") or {}).get("application/json") or {}).get("schema"))
        if not schema:
            parts.append(f'<div class="resp-code"><b>{esc(code)}</b> {esc(desc)} '
                         '<span class="muted">（文件流 / 无 JSON 响应体）</span></div>')
            continue
        sname = ref_name(schema) or "响应"
        body = render_fields(schema, comps, sname)
        if not body:
            body = f'<div class="note">响应类型：<code>{type_label(schema)}</code></div>'
        ex = example(schema, comps)
        ex_html = (f'<details class="example"><summary>响应示例</summary><pre>{esc(pretty(ex))}</pre></details>'
                   if ex is not None else "")
        parts.append(f'<div class="resp-code"><b>{esc(code)}</b> {esc(desc)}</div>{body}{ex_html}')
    return "<h4>响应</h4>" + "".join(parts)


def render_endpoint(op, method, path, comps, anchor, base_url):
    summary = op.get("summary") or ""
    desc = op.get("description") or ""
    parts = []
    for ctype, content in ((op.get("requestBody") or {}).get("content") or {}).items():
        schema = content.get("schema") or {}
        sname = ref_name(schema) or "请求体"
        if ctype == "multipart/form-data":
            if schema.get("properties"):
                parts.append(f"<h4>请求体 <span class='muted'>multipart/form-data</span></h4>")
                parts.append(render_fields(schema, comps, sname))
            else:
                parts.append('<h4>请求体</h4><div class="note">multipart/form-data 文件上传'
                             f'<div class="muted">{esc(desc)}</div></div>')
            continue
        parts.append(f"<h4>请求体 <span class='muted'>{esc(ctype)}</span></h4>")
        parts.append(render_fields(schema, comps, sname))
        ex = example(schema, comps)
        if ex is not None:
            parts.append(f'<details class="example" open><summary>请求示例</summary>'
                         f'<pre>{esc(pretty(ex))}</pre></details>')
    return f"""
<section class="api" id="{anchor}" data-base="{esc(base_url)}" data-search="{esc((method + ' ' + path + ' ' + summary).lower())}">
  <div class="api-head">
    <span class="method m-{method.lower()}">{method}</span>
    <code class="path">{esc(path)}</code>
    <button class="copy" data-url="{esc(path)}" title="复制完整 URL">复制</button>
  </div>
  <div class="api-summary">{esc(summary)}</div>
  {f'<div class="api-desc">{esc(desc)}</div>' if desc else ''}
  {render_params(op.get("parameters") or [], comps)}
  {''.join(parts)}
  {response_section(op, comps)}
</section>
"""


def slug(text):
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()


def render_module(module):
    data = json.loads(Path(module["openapi"]).read_text(encoding="utf-8"))
    title = module["title"]
    base_url = module.get("baseUrl") or (data.get("servers") or [{"url": ""}])[0].get("url", "")
    comps = data.get("components", {}).get("schemas", {})
    ops = []
    for path, methods in data["paths"].items():
        for method, op in methods.items():
            if method.lower() not in ("get", "post", "put", "patch", "delete", "head", "options"):
                continue
            ops.append((path, method.upper(), op))
    ops.sort(key=lambda x: (x[0], METHOD_ORDER.get(x[1], 9)))
    sections, nav = [], []
    for path, method, op in ops:
        anchor = "ep-" + slug(method + "-" + path)
        summary = op.get("summary") or ""
        nav.append(
            f'<a class="nav-item" href="#{anchor}" data-search="{esc((method + " " + path + " " + summary).lower())}">'
            f'<span class="method mini m-{method.lower()}">{method}</span>'
            f'<span class="nav-path">{esc(path)}</span></a>'
        )
        sections.append(render_endpoint(op, method, path, comps, anchor, base_url))
    note = module.get("note") or ""
    header = (
        f'<h2 class="module" id="mod-{slug(title)}">{esc(title)}</h2>'
        f'<div class="module-meta"><code>{esc(base_url)}</code> 共 {len(sections)} 个接口'
        + (f" · {esc(note)}" if note else "")
        + "</div>"
    )
    return title, nav, [header] + sections


def render_enums():
    if not ENUMS:
        return "", ""
    cards = []
    for block in ENUMS:
        rows = "".join(
            f"<tr><td>{'<code>%s</code>' % esc(r[0]) if len(r) > 0 else ''}</td>"
            f"<td>{esc(r[1]) if len(r) > 1 else ''}</td></tr>"
            for r in block.get("rows", [])
        )
        cards.append(
            f'<div class="enum-card"><h3>{esc(block.get("title", ""))}</h3>'
            f'<table class="grid small"><tr><th>字段</th><th>取值</th></tr>{rows}</table></div>'
        )
    body = (f'<h2 class="module" id="enums">附录：关键枚举 / 取值</h2>'
            f'<div class="enum-grid">{"".join(cards)}</div>')
    nav = ('<div class="nav-group"><div class="nav-title">附录</div>'
           '<a class="nav-item" href="#enums">关键枚举 / 取值</a></div>')
    return nav, body


CSS = """
:root { --bg:#f6f7f9; --panel:#fff; --text:#1f2328; --muted:#6b7280; --line:#e5e7eb;
  --get:#0f9d58; --post:#2563eb; --put:#d97706; --patch:#7c3aed; --delete:#dc2626; }
* { box-sizing:border-box; }
body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  color:var(--text); background:var(--bg); font-size:14px; line-height:1.6; }
code { font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:12.5px; }
.layout { display:flex; min-height:100vh; }
aside { width:330px; flex:0 0 330px; background:var(--panel); border-right:1px solid var(--line);
  position:sticky; top:0; height:100vh; overflow:auto; padding:16px 12px 40px; }
aside h1 { font-size:16px; margin:4px 8px 12px; }
aside .sub { color:var(--muted); font-size:12px; margin:0 8px 12px; }
#search { width:100%; padding:8px 10px; border:1px solid var(--line); border-radius:8px; margin:0 0 12px; font-size:13px; }
.nav-group { margin-bottom:14px; }
.nav-title { font-size:12px; color:var(--muted); margin:8px; font-weight:600; letter-spacing:.04em; }
.nav-item { display:flex; gap:8px; align-items:center; padding:5px 8px; border-radius:6px; color:var(--text); text-decoration:none; font-size:12.5px; }
.nav-item:hover { background:#f0f2f5; }
.nav-path { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
main { flex:1; min-width:0; padding:24px 32px 80px; }
.hero { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:20px 24px; margin-bottom:24px; }
.hero h1 { margin:0 0 6px; font-size:22px; }
.hero p { margin:6px 0; color:var(--muted); }
.hero code { background:#f3f4f6; padding:2px 6px; border-radius:4px; }
h2.module { margin:36px 0 8px; font-size:20px; padding-bottom:8px; border-bottom:2px solid var(--line); scroll-margin-top:16px; }
.module-meta { color:var(--muted); font-size:12.5px; margin:0 0 16px; }
.api { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:18px 20px; margin:0 0 16px; scroll-margin-top:16px; }
.api-head { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.method { color:#fff; font-weight:700; font-size:11px; padding:3px 8px; border-radius:5px; letter-spacing:.04em; }
.method.mini { font-size:9.5px; padding:2px 5px; min-width:44px; text-align:center; }
.m-get { background:var(--get); } .m-post { background:var(--post); }
.m-put { background:var(--put); } .m-patch { background:var(--patch); } .m-delete { background:var(--delete); }
.path { font-size:14px; font-weight:600; }
.copy { margin-left:auto; border:1px solid var(--line); background:#fff; border-radius:6px; padding:3px 10px; font-size:12px; color:var(--muted); cursor:pointer; }
.copy:hover { background:#f3f4f6; }
.api-summary { font-weight:600; margin-top:8px; }
.api-desc { color:var(--muted); margin-top:4px; white-space:pre-wrap; }
h4 { margin:16px 0 8px; font-size:13px; color:#374151; }
.note { background:#fffbeb; border:1px solid #fde68a; border-radius:8px; padding:8px 10px; }
table.grid { width:100%; border-collapse:collapse; font-size:12.5px; }
table.grid th, table.grid td { border:1px solid var(--line); padding:6px 8px; text-align:left; vertical-align:top; }
table.grid th { background:#f9fafb; font-weight:600; }
table.small td, table.small th { font-size:12px; }
.fields { border:1px solid var(--line); border-radius:8px; overflow:hidden; }
.frow { display:grid; grid-template-columns:220px 150px 1fr; gap:8px; padding:6px 10px; border-top:1px solid var(--line); }
.frow:first-child { border-top:none; }
.fhead { background:#f9fafb; font-weight:600; color:#374151; }
.fhead .ftype, .fhead .fdesc { font-weight:600; }
.fname code { font-weight:600; }
.req { color:#dc2626; margin-left:2px; }
.ftype { color:#6b7280; font-size:12px; }
.fdesc { font-size:12.5px; }
.nested { background:#fcfcfd; border-top:1px solid var(--line); padding:0 0 0 18px; }
.nested .fields { border:none; border-radius:0; }
.d1 { padding-left:6px; } .d2 { padding-left:12px; } .d3 { padding-left:18px; }
.resp-code { font-size:12.5px; margin:6px 0; }
details.example { margin:8px 0 4px; }
details.example summary { cursor:pointer; color:#2563eb; font-size:12.5px; }
pre { background:#0f172a; color:#e2e8f0; padding:12px 14px; border-radius:8px; overflow:auto; font-size:12px; line-height:1.5; max-height:520px; }
.muted { color:var(--muted); font-weight:400; }
.enum-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(420px,1fr)); gap:16px; }
.enum-card { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:16px; }
.enum-card h3 { margin:0 0 10px; font-size:15px; }
footer { color:var(--muted); font-size:12px; margin-top:40px; }
@media print { aside { display:none; } main { padding:0; } .api { break-inside:avoid; page-break-inside:avoid; } .copy { display:none; } }
"""


class _Checker(HTMLParser):
    VOID = {"br", "img", "hr", "meta", "link", "input", "source"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass
        else:
            self.errors.append(tag)


def verify(doc):
    checker = _Checker()
    checker.feed(doc)
    ids = set(re.findall(r'id="([^"]+)"', doc))
    broken = sorted(set(re.findall(r'href="#([^"]+)"', doc)) - ids)
    return {
        "unclosed": checker.stack,
        "bad_tags": checker.errors,
        "broken_anchors": broken,
        "unresolved_ref": doc.count("$ref"),
    }


def build():
    nav_parts, body_parts, total, stats = [], [], 0, []
    for module in MODULES:
        title, nav, sections = render_module(module)
        count = len(sections) - 1
        total += count
        stats.append((title, count))
        nav_parts.append(f'<div class="nav-group"><div class="nav-title">{esc(title)} · {count}</div>{"".join(nav)}</div>')
        body_parts.append("".join(sections))
    enum_nav, enum_body = render_enums()
    hero_extra = "".join(f"<p>{n}</p>" for n in HERO_NOTES)
    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(TITLE)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="layout">
<aside>
  <h1>{esc(TITLE)}</h1>
  <div class="sub">{' · '.join(esc(t) for t, _ in stats)}<br>共 {total} 个接口</div>
  <input id="search" placeholder="搜索路径 / 名称">
  {''.join(nav_parts)}
  {enum_nav}
</aside>
<main>
  <div class="hero">
    <h1>{esc(TITLE)}</h1>
    {hero_extra}
    <p>本文档由后端接口定义自动生成，字段说明取自 DTO 注释；标记 <span class="req">*</span> 为必填。</p>
  </div>
  {''.join(body_parts)}
  {enum_body}
  <footer>生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M")} · 共 {total} 个接口</footer>
</main>
</div>
<script>
const search = document.getElementById('search');
search.addEventListener('input', () => {{
  const q = search.value.trim().toLowerCase();
  document.querySelectorAll('.api').forEach(el => {{
    el.style.display = !q || el.dataset.search.includes(q) ? '' : 'none';
  }});
  document.querySelectorAll('.nav-item').forEach(el => {{
    el.style.display = !q || (el.dataset.search || '').includes(q) || el.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
}});
document.querySelectorAll('.copy').forEach(btn => {{
  btn.addEventListener('click', async () => {{
    const base = btn.closest('.api').dataset.base || '';
    const url = base + btn.dataset.url;
    try {{ await navigator.clipboard.writeText(url); btn.textContent = '已复制'; }}
    catch (e) {{ btn.textContent = url; }}
    setTimeout(() => btn.textContent = '复制', 1200);
  }});
}});
</script>
</body>
</html>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")
    result = verify(doc)
    print(f"生成: {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
    for t, c in stats:
        print(f"  - {t}: {c} 个接口")
    print(f"  合计: {total} 个接口")
    bad = {k: v for k, v in result.items() if v}
    if bad:
        print(f"[warn] 自检异常: {bad}")
        return 1
    print("  自检: 通过（锚点/标签/引用）")
    return 0


def load_config(path):
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    base = Path(path).resolve().parent
    for m in cfg.get("modules", []):
        p = Path(m["openapi"])
        m["openapi"] = str(p if p.is_absolute() else (base / p))
    out = Path(cfg.get("out", "api-doc.html"))
    cfg["out"] = str(out if out.is_absolute() else (base / out))
    if "srcRoots" in cfg:
        cfg["srcRoots"] = [str(Path(s) if Path(s).is_absolute() else (base / s)) for s in cfg["srcRoots"]]
    return cfg


def apply_config(cfg):
    global TITLE, OUT, HERO_NOTES, ENUMS, MODULES, PARAM_DOCS, EXTRA_FIELD_DOCS, FIELD_DOCS
    TITLE = cfg.get("title", TITLE)
    OUT = Path(cfg.get("out", OUT))
    HERO_NOTES = cfg.get("heroNotes", [])
    ENUMS = cfg.get("enums", [])
    MODULES = cfg.get("modules", [])
    PARAM_DOCS = {**DEFAULT_PARAM_DOCS, **(cfg.get("paramDocs") or {})}
    EXTRA_FIELD_DOCS = dict(cfg.get("fieldDocs") or {})
    FIELD_DOCS = extract_field_docs(cfg.get("srcRoots") or [])


def parse_module_arg(raw):
    """标题=path 或 标题=path|备注"""
    title, rest = raw.split("=", 1)
    note = ""
    if "|" in rest:
        rest, note = rest.split("|", 1)
    return {"title": title.strip(), "openapi": rest.strip(), "note": note.strip()}


def main():
    parser = argparse.ArgumentParser(description="OpenAPI 3 JSON -> 单文件 HTML 接口对接文档")
    parser.add_argument("--config", help="配置文件（JSON）")
    parser.add_argument("--title", help="文档标题")
    parser.add_argument("--out", help="输出 HTML 路径")
    parser.add_argument("--module", action="append", default=[], help='模块，格式 "标题=openapi.json" 或 "标题=openapi.json|备注"')
    parser.add_argument("--src", action="append", default=[], help="Java 源码根目录（用于提取字段注释），可重复")
    args = parser.parse_args()

    if args.config:
        cfg = load_config(args.config)
    else:
        if not args.module:
            parser.error("需要 --config 或至少一个 --module")
        cfg = {
            "title": args.title or "接口对接清单",
            "out": args.out or "api-doc.html",
            "modules": [parse_module_arg(m) for m in args.module],
            "srcRoots": args.src,
        }
    if not cfg.get("modules"):
        parser.error("没有任何模块")
    for m in cfg["modules"]:
        if not Path(m["openapi"]).exists():
            parser.error(f"OpenAPI 文件不存在: {m['openapi']}")
    apply_config(cfg)
    sys.exit(build())


if __name__ == "__main__":
    main()
