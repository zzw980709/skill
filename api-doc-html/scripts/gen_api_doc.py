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
import hashlib
import re
import sys
from datetime import datetime
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path

METHOD_ORDER = {"GET": 0, "POST": 1, "PUT": 2, "PATCH": 3, "DELETE": 4}

CLASS_RE = re.compile(r"\b(?:class|enum)\s+(\w+)")
JSON_PROP_RE = re.compile(r'@JsonProperty\(\s*(?:value\s*=\s*)?"([^"]+)"\s*\)')
FIELD_RE = re.compile(r"(?:private|public|protected)\s+[^;=()]+?\s+(\w+)\s*(?:=|;)")
DOC_OPEN_RE = re.compile(r"^\s*/\*\*")
DOC_CLOSE_RE = re.compile(r"\*/\s*$")
DOC_STAR_RE = re.compile(r"^\s*\*\s?")

# 通用查询参数说明（可按需在配置里 paramDocs 覆盖/扩展）
DEFAULT_PARAM_DOCS = {}  # 不从参数名推断业务语义。


FIELD_DOCS = {}
PARAM_DOCS = dict(DEFAULT_PARAM_DOCS)
EXTRA_FIELD_DOCS = {}
MODULES = []
TITLE = "接口对接清单"
OUT = Path("api-doc.html")
HERO_NOTES = []
ENUMS = []
CONFIG = {}


# ------------------------------------------------------------------ 源码注释

def clean_doc(lines):
    text = "\n".join(lines)
    text = DOC_OPEN_RE.sub("", text)
    text = DOC_CLOSE_RE.sub("", text)
    out = []
    for line in text.splitlines():
        line = DOC_STAR_RE.sub("", line).strip()
        if not line or line.startswith("@author") or line.startswith("@date"):
            continue
        out.append(line)
    return " ".join(out).strip()


def extract_field_docs(src_roots, target_classes=None):
    """扫描 Java 源码：class -> {jsonProperty: javadoc}。

    target_classes 非空时只解析包含这些类名的文件（OpenAPI components.schemas），
    避免每次都对整棵源码树做逐行正则解析。
    """
    docs = {}
    target_names = {n.split("$")[0].split(".")[0] for n in (target_classes or ()) if n}
    target_re = None
    needles = ()
    if target_names:
        if len(target_names) <= 80:
            needles = tuple(f"{kw} {name}" for name in target_names for kw in ("class", "enum"))
        else:
            target_re = re.compile(
                r"\b(?:class|enum)\s+(?:" + "|".join(map(re.escape, sorted(target_names))) + r")\b")
    for root in src_roots:
        root = Path(root)
        if not root.exists():
            print(f"[warn] 源码目录不存在，字段说明将缺失: {root}", file=sys.stderr)
            continue
        for path in root.rglob("*.java"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if target_names:
                if target_re is not None:
                    if not target_re.search(text):
                        continue
                elif not any(needle in text for needle in needles):
                    continue
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
                m = CLASS_RE.search(line)
                if m:
                    current_class = m.group(1)
                    docs.setdefault(current_class, {})
                    pending_doc = None
                    pending_json = None
                    continue
                m = JSON_PROP_RE.search(line)
                if m:
                    pending_json = m.group(1)
                    continue
                m = FIELD_RE.match(line)
                if m and current_class:
                    prop = pending_json or m.group(1)
                    if pending_doc:
                        docs[current_class].setdefault(prop, pending_doc)
                    pending_doc = None
                    pending_json = None
    return docs


@lru_cache(maxsize=32)
def load_openapi(path):
    """同一份 OpenAPI 只解析一次（字段名收集和渲染共用）。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def collect_schema_names(modules):
    names = set()
    for module in modules:
        data = load_openapi(module["openapi"])
        names.update((data.get("components") or {}).get("schemas", {}).keys())
    return names


def field_desc(schema_name, prop):
    return EXTRA_FIELD_DOCS.get(f"{schema_name}.{prop}") or FIELD_DOCS.get(schema_name, {}).get(prop, "")


# ------------------------------------------------------------------ contract model
HTTP_METHODS = {'get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace'}
ASSETS = Path(__file__).resolve().parents[1] / 'assets'
MISSING = object()


def esc(value):
    return html.escape(str(value), quote=True)


def pretty(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def resolve(node, doc):
    """Resolve local object refs, keeping siblings and stopping circular chains."""
    seen = set()
    while isinstance(node, dict) and '$ref' in node:
        ref = node['$ref']
        if not ref.startswith('#/') or ref in seen:
            return {**node, 'x-unresolved': ref}
        seen.add(ref)
        target = doc
        try:
            for key in ref[2:].split('/'):
                target = target[key.replace('~1', '/').replace('~0', '~')]
        except (KeyError, TypeError):
            return {**node, 'x-unresolved': ref}
        if not isinstance(target, dict):
            return {'x-unresolved': ref}
        node = {**target, **{k: v for k, v in node.items() if k != '$ref'}}
    return node if isinstance(node, dict) else {}


def shape(schema, doc, depth=0, seen=()):
    ref = schema.get('$ref') if isinstance(schema, dict) else None
    if depth > 12 or (ref and ref in seen):
        return {'x-unresolved': ref or 'recursive allOf'}
    seen = seen + ((ref,) if ref else ())
    node = resolve(schema, doc)
    if 'allOf' not in node:
        return node
    merged = {k: v for k, v in node.items() if k != 'allOf'}
    props, required = dict(merged.get('properties', {})), list(merged.get('required', []))
    # allOf composition can be recursive; avoid expanding a self-referential member.
    for part in node['allOf']:
        part = shape(part, doc, depth + 1, seen)
        props.update(part.get('properties', {}))
        required.extend(part.get('required', []))
    if props:
        merged.update(type='object', properties=props, required=list(dict.fromkeys(required)))
    return merged


def schema_type(schema, doc):
    node = shape(schema, doc)
    if 'x-unresolved' in node:
        return '未知引用'
    for union in ('oneOf', 'anyOf'):
        if union in node:
            return ' | '.join(schema_type(s, doc) for s in node[union])
    typ = node.get('type', 'object' if 'properties' in node else 'unknown')
    if typ == 'array':
        return schema_type(node.get('items', {}), doc) + '[]'
    if isinstance(typ, list):
        return ' | '.join(typ)
    return 'file' if node.get('format') == 'binary' else typ


def sample(schema, doc, direction='response', depth=0, seen=()):
    if depth > 7:
        return None
    ref = schema.get('$ref') if isinstance(schema, dict) else None
    if ref and ref in seen:
        return None
    seen = seen + ((ref,) if ref else ())
    node = shape(schema, doc)
    for key in ('example', 'default', 'const'):
        if key in node:
            return node[key]
    if node.get('examples') and isinstance(node['examples'], list):
        return node['examples'][0]
    if node.get('enum'):
        return node['enum'][0]
    for union in ('oneOf', 'anyOf'):
        if node.get(union):
            return sample(node[union][0], doc, direction, depth + 1, seen)
    typ = node.get('type')
    if typ == 'array':
        return [sample(node.get('items', {}), doc, direction, depth + 1, seen)]
    if typ == 'object' or 'properties' in node:
        return {key: sample(value, doc, direction, depth + 1, seen)
                for key, value in node.get('properties', {}).items()
                if not shape(value, doc).get('readOnly' if direction == 'request' else 'writeOnly')}
    if typ in ('integer', 'number'):
        return node.get('minimum', 0)
    if typ == 'boolean':
        return True
    if typ == 'null' or 'x-unresolved' in node:
        return None
    return {'date': '2026-01-01', 'date-time': '2026-01-01T00:00:00Z',
            'email': 'user@example.com', 'binary': '<file>'}.get(node.get('format'), 'string')


def media_example(media, doc, direction):
    if 'example' in media:
        return media['example'], '接口提供的示例'
    for entry in (media.get('examples') or {}).values():
        entry = resolve(entry, doc)
        if 'value' in entry:
            return entry['value'], '接口提供的示例'
    return sample(media.get('schema', {}), doc, direction), '按 Schema 生成 · 请替换占位值'


def constraints(node):
    bits = []
    if 'enum' in node:
        names = node.get('x-enumNames') or node.get('x-enum-varnames') or []
        bits.append('可选值 ' + ' / '.join(
            json.dumps(v, ensure_ascii=False) + (f' ({names[i]})' if i < len(names) else '')
            for i, v in enumerate(node['enum'])))
    for key, label in [('format', '格式'), ('default', '默认'), ('minimum', '最小值'),
                       ('maximum', '最大值'), ('minLength', '最短'), ('maxLength', '最长'),
                       ('minItems', '最少项'), ('maxItems', '最多项'), ('pattern', '匹配')]:
        if key in node:
            bits.append(f'{label} {json.dumps(node[key], ensure_ascii=False)}')
    if node.get('nullable') or (isinstance(node.get('type'), list) and 'null' in node['type']):
        bits.append('允许 null')
    for key, label in [('readOnly', '只读'), ('writeOnly', '只写'), ('deprecated', '已弃用')]:
        if node.get(key):
            bits.append(label)
    if node.get('oneOf') or node.get('anyOf'):
        bits.append('联合结构，见 TypeScript')
    return bits


def ts_type(schema, doc, direction, depth=0, seen=()):
    ref = schema.get('$ref') if isinstance(schema, dict) else None
    if depth > 10 or (ref and ref in seen):
        return 'unknown /* recursive */'
    seen = seen + ((ref,) if ref else ())
    node = resolve(schema, doc)
    if 'x-unresolved' in node:
        return 'unknown /* unresolved reference */'
    for union, sep in [('oneOf', ' | '), ('anyOf', ' | '), ('allOf', ' & ')]:
        if node.get(union):
            base = {k: v for k, v in node.items() if k != union}
            members = [ts_type(s, doc, direction, depth + 1, seen) for s in node[union]]
            if base.get('properties'):
                members.append(ts_type(base, doc, direction, depth + 1, seen))
            result = '(' + sep.join(members) + ')'
            return result + (' | null' if node.get('nullable') else '')
    if 'enum' in node:
        result = ' | '.join(json.dumps(v, ensure_ascii=False) for v in node['enum']) or 'never'
    elif 'const' in node:
        result = json.dumps(node['const'], ensure_ascii=False)
    elif node.get('type') == 'array':
        result = 'Array<' + ts_type(node.get('items', {}), doc, direction, depth + 1, seen) + '>'
    elif node.get('type') == 'object' or 'properties' in node:
        rows = []
        for key, value in node.get('properties', {}).items():
            v = shape(value, doc)
            if v.get('readOnly' if direction == 'request' else 'writeOnly'):
                continue
            desc = v.get('description', '').replace('*/', '* /').replace('\n', ' ')
            if desc:
                rows.append('  /** ' + desc + ' */')
            optional = '' if key in node.get('required', []) else '?'
            rows.append('  ' + json.dumps(key, ensure_ascii=False) + optional + ': ' +
                        ts_type(value, doc, direction, depth + 1, seen).replace('\n', '\n  ') + ';')
        additional = node.get('additionalProperties', MISSING)
        if not rows:
            value = ts_type(additional, doc, direction, depth + 1, seen) if isinstance(additional, dict) else 'unknown'
            result = 'Record<string, ' + ('never' if additional is False else value) + '>'
        else:
            # Named properties may differ from additionalProperties; unknown avoids an invalid index signature.
            if additional is not False:
                rows.append('  [key: string]: unknown;')
            result = '{\n' + '\n'.join(rows) + '\n}'
    else:
        types = node.get('type', 'unknown')
        result = ' | '.join({'integer': 'number', 'number': 'number', 'string': 'string',
                             'boolean': 'boolean', 'null': 'null'}.get(t, 'unknown')
                            for t in (types if isinstance(types, list) else [types]))
        if node.get('format') == 'binary':
            result = 'Blob'
    if node.get('nullable') and 'null' not in result.split(' | '):
        result += ' | null'
    return result


def contract_rows(schema, doc, direction, prefix='', depth=0, seen=(), schema_name=''):
    ref = schema.get('$ref') if isinstance(schema, dict) else None
    if depth > 6 or (ref and ref in seen):
        return '<tr><td colspan="4" class="muted">递归或深层结构，请结合 TypeScript 查看。</td></tr>'
    seen = seen + ((ref,) if ref else ())
    if ref:
        schema_name = ref.split('/')[-1]
    node = shape(schema, doc)
    if node.get('type') == 'array':
        return contract_rows(node.get('items', {}), doc, direction, prefix + '[]', depth + 1, seen, schema_name)
    rows = []
    for key, value in node.get('properties', {}).items():
        v = shape(value, doc)
        if v.get('readOnly' if direction == 'request' else 'writeOnly'):
            continue
        path = prefix + ('.' if prefix else '') + key
        desc = field_desc(schema_name, key) or v.get('description', '')
        required = key in node.get('required', [])
        chips = ''.join(f'<span>{esc(c)}</span>' for c in constraints(v))
        rows.append(f'<tr><td><code>{esc(path)}</code></td><td><code class="type">{esc(schema_type(value, doc))}</code></td>'
                    f'<td><span class="{"required" if required else "optional"}">{"必填" if required else "可选"}</span></td>'
                    f'<td>{esc(desc) if desc else "<span class=muted>暂无说明</span>"}<div class="constraints">{chips}</div></td></tr>')
        if v.get('properties') or v.get('type') == 'array':
            rows.append(contract_rows(value, doc, direction, path, depth + 1, seen, schema_name))
    return ''.join(rows)


def field_table(schema, doc, direction):
    rows = contract_rows(schema, doc, direction)
    if not rows:
        return f'<p class="empty-inline">类型 <code>{esc(schema_type(schema, doc))}</code>，具体结构见示例与 TypeScript。</p>'
    return ('<div class="table-scroll"><table><thead><tr><th>字段路径</th><th>类型</th><th>必填</th>'
            '<th>说明 / 约束</th></tr></thead><tbody>' + rows + '</tbody></table></div>')


def parameter_table(params, doc):
    if not params:
        return '<p class="empty-inline">未声明路径、查询或请求头参数。</p>'
    rows = []
    for p in params:
        sch = shape(p.get('schema', {}), doc)
        desc = p.get('description') or PARAM_DOCS.get(p.get('name'), '')
        chips = ''.join(f'<span>{esc(c)}</span>' for c in constraints(sch))
        rows.append(f'<tr><td><code>{esc(p.get("name", ""))}</code><small>{esc(p.get("in", ""))}</small></td>'
                    f'<td><code class="type">{esc(schema_type(sch, doc))}</code></td>'
                    f'<td><span class="{"required" if p.get("required") or p.get("in") == "path" else "optional"}">'
                    f'{"必填" if p.get("required") or p.get("in") == "path" else "可选"}</span></td>'
                    f'<td>{esc(desc) if desc else "<span class=muted>暂无说明</span>"}'
                    f'<div class="constraints">{chips}</div></td></tr>')
    return '<div class="table-scroll"><table><thead><tr><th>参数 / 位置</th><th>类型</th><th>必填</th><th>说明 / 约束</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'


def auth_text(op, doc):
    security = op.get('security', doc.get('security', MISSING))
    if security is MISSING:
        return '待确认', 'OpenAPI 未声明鉴权，不能据此认定为公开接口。'
    if not security or any(not requirement for requirement in security):
        return '可匿名', 'OpenAPI 允许匿名访问；业务权限仍以服务端校验为准。'
    schemes = doc.get('components', {}).get('securitySchemes', {})
    choices = []
    for requirement in security:
        parts = []
        for name, scopes in requirement.items():
            scheme = resolve(schemes.get(name, {}), doc)
            typ = scheme.get('type')
            label = (scheme.get('scheme', name).title() if typ == 'http' else
                     f'{scheme.get("name", name)} · {scheme.get("in", "header")}' if typ == 'apiKey' else name)
            parts.append(label + (f' ({", ".join(scopes)})' if scopes else ''))
        choices.append(' + '.join(parts))
    return '需鉴权', ' 或 '.join(choices)


def collect_operations():
    records = []
    for index, module in enumerate(MODULES):
        doc = load_openapi(module['openapi'])
        base = module.get('baseUrl', (doc.get('servers') or [{'url': ''}])[0].get('url', ''))
        for path, item in doc.get('paths', {}).items():
            item = resolve(item, doc)
            for method, raw in item.items():
                if method.lower() not in HTTP_METHODS or not isinstance(raw, dict):
                    continue
                op = resolve(raw, doc)
                key = method.upper() + ' ' + path
                params = {}
                for raw_param in item.get('parameters', []) + op.get('parameters', []):
                    p = resolve(raw_param, doc)
                    params[(p.get('name'), p.get('in'))] = p
                hints = {**CONFIG.get('operationDocs', {}).get(key, {}),
                         **module.get('operationDocs', {}).get(key, {})}
                if op.get('operationId'):
                    hints.update(CONFIG.get('operationDocs', {}).get(op['operationId'], {}))
                    hints.update(module.get('operationDocs', {}).get(op['operationId'], {}))
                identity = f'{index}:{key}'
                anchor = 'ep-' + hashlib.sha256(identity.encode()).hexdigest()[:12]
                records.append(dict(id=anchor, module=module, doc=doc, base=base, path=path,
                                    method=method.upper(), op=op, params=list(params.values()), hints=hints))
    return records


def search_contract(node, doc):
    """Include referenced field names/descriptions without indexing unrelated schemas."""
    words, seen, stack = [], set(), [node]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            ref = item.get('$ref')
            if ref:
                if ref in seen:
                    continue
                seen.add(ref)
                item = resolve(item, doc)
            words.extend(str(key) for key in item)
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, (str, int, float)):
            words.append(str(item))
    return ' '.join(words).lower()


def handoff_data(records):
    """Keep exact contracts separate from task instructions and business annotations."""
    copy = lambda value: json.loads(json.dumps(value))
    modules, operations, scopes, workflows = [], [], [], []
    for index, module in enumerate(MODULES):
        group = [r for r in records if r['module'] is module]
        module_id = f'module-{index}'
        doc = load_openapi(module['openapi'])
        source = copy({key: doc[key] for key in ('openapi', 'info', 'servers', 'security', 'components') if key in doc})
        if 'baseUrl' in module:
            source['servers'] = [{'url': module['baseUrl']}]
        for name, schema in source.get('components', {}).get('schemas', {}).items():
            for prop, field in schema.get('properties', {}).items():
                desc = field_desc(name, prop)
                if desc and isinstance(field, dict):
                    field['description'] = desc
        modules.append(dict(id=module_id, title=module['title'], note=module.get('note', ''), source=source))
        scopes.append(dict(id=module_id, label='模块 · ' + module['title'], operations=[r['id'] for r in group]))
        for rec in group:
            op = copy(rec['op'])
            if rec['params']:
                op['parameters'] = copy(rec['params'])
            path_item = resolve(doc['paths'][rec['path']], doc)
            if 'servers' not in op and 'servers' in path_item:
                op['servers'] = copy(path_item['servers'])
            label, auth = auth_text(op, doc)
            usage = rec['hints'].get('usage') or op.get('description', '')
            pending = []
            if not source.get('servers') and not op.get('servers'):
                pending.append('未声明服务地址，需确认前端环境配置与代理约定。')
            if label == '待确认':
                pending.append('未声明鉴权，不能默认匿名访问。')
            if not any(str(code).startswith('2') for code in op.get('responses', {})):
                pending.append('未声明成功响应。')
            if not any(not str(code).startswith('2') for code in op.get('responses', {})):
                pending.append('未声明异常响应，需确认错误状态码与结构。')
            if not usage:
                pending.append('使用场景尚未补充，需结合用户任务及已有页面确认。')
            summary = op.get('summary') or op.get('operationId') or rec['path']
            operations.append(dict(id=rec['id'], moduleId=module_id, path=rec['path'], method=rec['method'],
                                   operationId=op.get('operationId', ''), summary=summary, usage=usage,
                                   notes=copy(rec['hints'].get('notes', [])), authentication=label + '：' + auth,
                                   pending=pending, contract=op))
    for index, flow in enumerate(CONFIG.get('workflows', [])):
        steps, ids = [], []
        for step in flow.get('steps', []):
            matches = [r for r in records if (not step.get('module') or step['module'] == r['module']['title']) and
                       ((step.get('operationId') and r['op'].get('operationId') == step['operationId']) or
                        (step.get('endpoint') and step['endpoint'] == r['method'] + ' ' + r['path']))]
            if len(matches) != 1:
                raise ValueError(f'流程 {flow.get("title")}: 接口引用需唯一匹配，实际 {len(matches)} 条: {step}')
            rec = matches[0]
            ids.append(rec['id'])
            steps.append(dict(module=rec['module']['title'], endpoint=rec['method'] + ' ' + rec['path'], note=step.get('note', '')))
        workflows.append(dict(title=flow.get('title', ''), description=flow.get('description', ''), steps=steps, operations=ids))
        scopes.append(dict(id=f'flow-{index}', label='流程 · ' + flow.get('title', ''), operations=ids))
    scopes = [dict(id='all', label='全部接口', operations=[r['id'] for r in records])] + scopes
    scopes.extend(dict(id=r['id'], label=r['module']['title'] + ' · ' + r['method'] + ' ' + r['path'], operations=[r['id']]) for r in records)
    agent = CONFIG.get('agent', {})
    return dict(title=TITLE, audience=CONFIG.get('audience', '前端开发'), modules=modules, operations=operations,
                scopes=scopes, workflows=workflows, integration=CONFIG.get('integration', []), enums=ENUMS,
                task=agent.get('task', ''), constraints=agent.get('constraints', []), acceptanceCriteria=agent.get('acceptanceCriteria', []))


def render_agent_handoff(data):
    options = ''.join(f'<option value="{s["id"]}">{esc(s["label"])}</option>' for s in data['scopes'])
    return f'''<section class="view" id="agent" data-title="交给 Agent">
<div class="breadcrumb">项目文档 <span>/</span> 交给 Agent</div>
<div class="eyebrow">AGENT HANDOFF</div><h1>把对接资料交给前端 Agent</h1>
<p class="handoff-intro">选择范围、补充目标页面，再复制任务包。Agent 会先读取你的前端仓库约定，复用现有请求与类型封装。</p>
<div class="handoff-controls"><div><label for="agent-scope">01 · 选择接口范围</label><select id="agent-scope">{options}</select></div>
<div><label for="agent-task">02 · 补充本次任务（可选）</label><textarea id="agent-task" rows="3" placeholder="例如：将订单列表与详情接入已有页面，保留现有筛选和分页交互。">{esc(data['task'])}</textarea></div></div>
<div class="handoff-toolbar"><div><strong>03 · 交给 Agent</strong><p id="agent-summary" aria-live="polite"></p></div><div class="handoff-actions">
<button type="button" class="primary-button" data-copy="agent-prompt">复制 Agent 任务</button><button type="button" id="agent-download-md">下载任务 .md</button><button type="button" id="agent-download-json">下载契约包 .json</button></div></div>
<div class="quiet-note">复制后粘贴到前端 Agent，或把下载的文件交给它。任务包保留字段、约束、鉴权与引用模型；不会读取本机登录令牌，也不会自动调用接口。请核对源码示例中是否含有不应分享的数据。</div>
<label class="handoff-preview-label" for="agent-prompt">任务包预览 · Markdown</label><textarea id="agent-prompt" class="handoff-preview" readonly spellcheck="false" aria-label="Agent 任务包预览"></textarea>
<noscript><p>此模块的范围选择与导出需要启用 JavaScript。接口参考仍可直接阅读。</p></noscript></section>'''


def code_block(text, label, ident, lang='json'):
    return (f'<div class="code-heading"><span>{esc(label)}</span><button class="copy-code" data-copy="{ident}" type="button">复制</button></div>'
            f'<pre id="{ident}" data-lang="{lang}"><code>{esc(text)}</code></pre>')


def fetch_code(rec):
    op, doc = rec['op'], rec['doc']
    # Keep a visible base placeholder instead of accidentally treating a relative server as the docs origin.
    base = rec['base'] or 'https://YOUR_API_HOST'
    lines = ['// 调用示例：替换占位值，并按项目约定接入鉴权与错误处理。',
             'const baseUrl = ' + json.dumps(base, ensure_ascii=False) + ';']
    path = rec['path']
    path_expr = json.dumps(path, ensure_ascii=False)
    for p in rec['params']:
        if p.get('in') == 'path':
            value = p.get('example', sample(p.get('schema', {}), doc, 'request'))
            path_expr += '.replace(' + json.dumps('{' + p['name'] + '}') + ', encodeURIComponent(String(' + json.dumps(value, ensure_ascii=False) + ')))'
    lines.append('const path = ' + path_expr + ';')
    lines.append(r'const url = new URL(baseUrl.replace(/\/$/, "") + path, "https://YOUR_API_HOST");')
    for p in rec['params']:
        if p.get('in') == 'query':
            lines.append('// ' + p['name'] + ('：必填' if p.get('required') else '：可选，按需添加'))
            val = p.get('example', sample(p.get('schema', {}), doc, 'request'))
            if isinstance(val, (dict, list)):
                lines.append('// 复杂参数 ' + p['name'] + '：请按 style/explode 约定序列化。')
            else:
                lines.append('url.searchParams.set(' + json.dumps(p['name']) + ', String(' + json.dumps(val, ensure_ascii=False) + '));')
    headers = {p['name']: '<' + p['name'] + '>' for p in rec['params'] if p.get('in') == 'header'}
    security = op.get('security', doc.get('security', []))
    schemes = doc.get('components', {}).get('securitySchemes', {})
    credentials = False
    if security and all(security):
        lines.append('// 以下采用第一组鉴权方案，凭据由项目登录态提供。')
        for name in security[0]:
            scheme = resolve(schemes.get(name, {}), doc)
            if scheme.get('type') == 'http':
                headers['Authorization'] = scheme.get('scheme', '').title() + ' <credentials>'
            elif scheme.get('type') == 'apiKey' and scheme.get('in') == 'header':
                headers[scheme.get('name', name)] = '<api-key>'
            elif scheme.get('type') == 'apiKey' and scheme.get('in') == 'query':
                lines.append('url.searchParams.set(' + json.dumps(scheme.get('name', name)) + ', "<api-key>");')
            elif scheme.get('type') == 'apiKey' and scheme.get('in') == 'cookie':
                credentials = True
            else:
                lines.append('// ' + name + '：按项目约定获取凭据并设置请求。')
    body = resolve(op.get('requestBody', {}), doc)
    contents = body.get('content', {})
    chosen = next(((t, m) for t, m in contents.items() if 'json' in t), next(iter(contents.items()), None))
    body_line = ''
    if chosen:
        ctype, media = chosen
        value, _ = media_example(media, doc, 'request')
        if 'json' in ctype:
            headers['Content-Type'] = ctype
            lines.append('const body = ' + pretty(value) + ';')
            body_line = '  body: JSON.stringify(body),'
        elif ctype == 'multipart/form-data':
            lines += ['const body = new FormData();', '// 按请求字段追加数据；文件字段使用 File / Blob。']
            for name, sch in shape(media.get('schema', {}), doc).get('properties', {}).items():
                v = shape(sch, doc)
                if v.get('format') == 'binary':
                    lines.append('body.append(' + json.dumps(name) + ', new File([], "REPLACE_WITH_REAL_FILE"));')
                else:
                    lines.append('body.append(' + json.dumps(name) + ', String(' + json.dumps(sample(sch, doc, 'request'), ensure_ascii=False) + '));')
            body_line = '  body,'
        else:
            lines.append('// ' + ctype + '：请按该媒体类型构造请求体。')
    lines.append('const response = await fetch(url, {')
    lines.append('  method: ' + json.dumps(rec['method']) + ',')
    if headers:
        lines.append('  headers: ' + pretty(headers).replace('\n', '\n  ') + ',')
    if credentials:
        lines.append('  credentials: "include", // 跨域时还需服务端允许凭据')
    if body_line:
        lines.append(body_line)
    lines += ['});', 'if (!response.ok) {', '  // 在这里结合下方异常响应处理业务提示。',
              '  throw new Error(`HTTP ${response.status}`);', '}']
    if rec['method'] == 'HEAD':
        lines.append('const result = response.headers;')
    else:
        lines += ['const contentType = response.headers.get("content-type") ?? "";',
                  'const result = response.status === 204 || response.status === 205', '  ? undefined',
                  '  : contentType.includes("json")', '    ? await response.json()',
                  '    : contentType.startsWith("text/")', '      ? await response.text()',
                  '      : await response.blob();']
    return '\n'.join(lines)


def response_html(code, response, doc):
    response = resolve(response, doc)
    parts = [f'<div class="response-heading"><span class="status {"success" if str(code).startswith("2") else "failure"}">{esc(code)}</span>'
             f'<span>{esc(response.get("description", ""))}</span></div>']
    for ctype, media in response.get('content', {}).items():
        parts.append(f'<h4>{esc(ctype)}</h4>')
        if media.get('schema'):
            parts.append(field_table(media['schema'], doc, 'response'))
    if not response.get('content'):
        message = ('该状态码不包含响应体，前端无需调用 response.json()。' if str(code) in ('204', '205') else
                   '未声明响应内容；是否无响应体需结合状态码与实际实现确认。')
        parts.append(f'<p class="empty-inline">{message}</p>')
    if response.get('headers'):
        parts.append('<p class="eyebrow">响应头</p>')
        parts.append(parameter_table([dict(resolve(h, doc), name=n, **{'in': 'header'})
                                      for n, h in response['headers'].items()], doc))
    return '<div class="response-block">' + ''.join(parts) + '</div>'


def render_endpoint(rec):
    op, doc, anchor = rec['op'], rec['doc'], rec['id']
    hints = rec['hints']
    label, auth = auth_text(op, doc)
    summary = op.get('summary') or op.get('operationId') or rec['path']
    chips = ''.join(f'<span class="tag">{esc(tag)}</span>' for tag in op.get('tags', []))
    usage = hints.get('usage') or op.get('description', '')
    notes = hints.get('notes', [])
    notes_html = '<ul class="notes">' + ''.join(f'<li>{esc(n)}</li>' for n in notes) + '</ul>' if notes else ''
    request = '<h3>路径、查询与请求头</h3>' + parameter_table(rec['params'], doc)
    body = resolve(op.get('requestBody', {}), doc)
    snippets = []
    types = ['// 由接口契约推导；运行时仍需校验返回值，递归结构以 unknown 截断。']
    if rec['params']:
        for location, name in [('path', 'PathParams'), ('query', 'QueryParams'), ('header', 'HeaderParams')]:
            params = [p for p in rec['params'] if p.get('in') == location]
            if params:
                schema = {'type': 'object', 'properties': {p['name']: p.get('schema', {}) for p in params},
                          'required': [p['name'] for p in params if p.get('required') or location == 'path'], 'additionalProperties': False}
                types.append('export type ' + name + ' = ' + ts_type(schema, doc, 'request') + ';')
    for i, (ctype, media) in enumerate(body.get('content', {}).items()):
        request += f'<h3>请求体 <span class="tag">{esc(ctype)}</span> <span class="{"required" if body.get("required") else "optional"}">{"必填" if body.get("required") else "可选"}</span></h3>'
        request += field_table(media.get('schema', {}), doc, 'request')
        value, source = media_example(media, doc, 'request')
        snippets.append(('请求示例' + (f' · {ctype}' if i else ''), pretty(value), source, 'json'))
        types.append('export type RequestBody' + (str(i + 1) if i else '') + ' = ' + ts_type(media.get('schema', {}), doc, 'request') + ';')
    if not body.get('content'):
        request += '<div class="quiet-note">该接口未声明请求体。</div>'
    successes, failures = [], []
    for code, raw in (op.get('responses') or {}).items():
        response = resolve(raw, doc)
        (successes if str(code).startswith('2') else failures).append(response_html(code, response, doc))
        for i, (ctype, media) in enumerate(response.get('content', {}).items()):
            value, source = media_example(media, doc, 'response')
            snippets.append((f'{code} 响应' + (f' · {ctype}' if i else ''), pretty(value), source, 'json'))
            type_name = 'Response' + re.sub(r'\W', '', str(code)) + (str(i + 1) if i else '')
            types.append('export type ' + type_name + ' = ' + ts_type(media.get('schema', {}), doc, 'response') + ';')
    if not successes:
        successes.append('<div class="quiet-note">未声明成功响应，请向后端确认。</div>')
    if not failures:
        failures.append('<div class="quiet-note">未声明异常响应。请确认鉴权失败、校验失败与业务异常的状态码及返回结构。</div>')
    snippets = [('Fetch', fetch_code(rec), '调用骨架 · 不会在文档中发送请求', 'js'),
                ('TypeScript', '\n\n'.join(types), '按契约推导 · 可复制到项目后调整', 'ts')] + snippets
    tabs, panels = [], []
    for index, (title, code, source, lang) in enumerate(snippets):
        ident = f'{anchor}-code-{index}'
        tabs.append(f'<option value="{ident}">{esc(title)}</option>')
        panels.append(f'<div class="snippet" id="{ident}">{code_block(code, source, ident + "-text", lang)}</div>')
    overview = (f'<h3>什么时候调用</h3><p class="prose">{esc(usage) if usage else "尚未补充使用场景，可在 operationDocs 中添加。"}</p>'
                f'<div class="auth-card"><span class="eyebrow">{esc(label)}</span><p>{esc(auth)}</p></div>'
                f'<h3>联调提示</h3>{notes_html or "<p class=empty-inline>暂无额外约定；字段约束与异常响应见对应标签。</p>"}')
    panels_body = [('overview', '使用说明', overview), ('request', '请求', request),
                   ('response', '成功响应', ''.join(successes)), ('errors', '异常响应', ''.join(failures))]
    tab_html = ''.join(f'<button type="button" id="{anchor}-tab-{key}" role="tab" aria-controls="{anchor}-{key}" aria-selected="{str(i == 0).lower()}" tabindex="{0 if i == 0 else -1}">{title}</button>'
                       for i, (key, title, _) in enumerate(panels_body))
    content_html = ''.join(f'<div class="contract-panel" id="{anchor}-{key}" role="tabpanel" aria-labelledby="{anchor}-tab-{key}">{content}</div>'
                           for key, _, content in panels_body)
    return f'''<section class="api view" id="{anchor}" data-title="{esc(summary)}">
<div class="breadcrumb">接口参考 <span>/</span> {esc(rec['module']['title'])} <span>/</span> {esc(op.get('operationId', summary))}</div>
<div class="endpoint-title"><div><div class="eyebrow">{esc(rec['module']['title'])}</div><h1>{esc(summary)}</h1></div>{'<span class="tag deprecated">已弃用</span>' if op.get('deprecated') else ''}</div>
<div class="endpoint-bar"><span class="method m-{rec['method'].lower()}">{rec['method']}</span><code>{esc(rec['path'])}</code><button type="button" class="copy-code" data-copy="{anchor}-url">复制 URL</button></div>
<div class="endpoint-meta">{chips}<span class="auth-badge">{esc(label)}</span><span>Base URL <code>{esc(rec['base']) or '待确认'}</code></span><a class="agent-entry" href="#agent" data-agent-scope="{anchor}">交给 Agent ↗</a></div>
<span id="{anchor}-url" hidden>{esc(rec['base'].rstrip('/') + rec['path'])}</span>
<div class="workspace"><div class="contract"><div class="tabs" role="tablist" aria-label="{esc(summary)}详情">{tab_html}</div>{content_html}</div>
<aside class="code-rail"><div class="rail-heading"><span class="eyebrow">开发示例</span><label class="sr-only" for="{anchor}-select">选择代码示例</label><select id="{anchor}-select" class="snippet-select">{''.join(tabs)}</select></div>{''.join(panels)}<p class="code-footnote">示例中的占位值需要替换。生成示例不代表业务推荐值。</p></aside></div></section>'''


def render_workflows(records):
    cards = []
    for flow in CONFIG.get('workflows', []):
        steps = []
        for step in flow.get('steps', []):
            matches = [r for r in records if (not step.get('module') or step['module'] == r['module']['title']) and
                       ((step.get('operationId') and r['op'].get('operationId') == step['operationId']) or
                        (step.get('endpoint') and step['endpoint'] == r['method'] + ' ' + r['path']))]
            if len(matches) != 1:
                raise ValueError(f'流程 {flow.get("title")}: 接口引用需唯一匹配，实际 {len(matches)} 条: {step}')
            r = matches[0]
            steps.append(f'<li><a href="#{r["id"]}">{esc(r["op"].get("summary") or r["path"])} <span>↗</span></a><p>{esc(step.get("note", ""))}</p></li>')
        cards.append(f'<article class="flow-card"><h3>{esc(flow.get("title", ""))}</h3><p class="muted">{esc(flow.get("description", ""))}</p><ol>{"".join(steps)}</ol></article>')
    return '<div class="flow-grid">' + ''.join(cards) + '</div>' if cards else '<div class="quiet-note">尚未补充页面调用流程。可根据真实业务配置 workflows，将页面动作关联到接口。</div>'


def render_overview(records):
    groups = []
    for module in MODULES:
        operations = [r for r in records if r['module'] is module]
        base = operations[0]['base'] if operations else module.get('baseUrl', '')
        links = ''.join(f'<a class="endpoint-link" href="#{r["id"]}"><span class="method m-{r["method"].lower()}">{r["method"]}</span><span><strong>{esc(r["op"].get("summary") or r["path"])}</strong><code>{esc(r["path"])}</code></span><span class="arrow">↗</span></a>' for r in operations)
        groups.append(f'<article class="module-card"><div class="section-heading"><h3>{esc(module["title"])}</h3><span>{len(operations)} 个接口</span></div><code class="base-url">{esc(base) or "Base URL 待确认"}</code><p class="muted">{esc(module.get("note", ""))}</p>{links or "<p class=muted>无接口</p>"}</article>')
    missing_auth = sum(auth_text(r['op'], r['doc'])[0] == '待确认' for r in records)
    missing_errors = sum(not any(not str(c).startswith('2') for c in r['op'].get('responses', {})) for r in records)
    guides = ''.join(f'<article class="guide-card"><span class="guide-index">{i + 1:02}</span><h3>{esc(g["title"])}</h3><p>{esc(g["text"])}</p></article>' for i, g in enumerate(CONFIG.get('integration', [])))
    if not guides:
        guides = '<div class="quiet-note">尚未补充接入约定。建议确认登录态来源、分页、空值、时间与业务错误的处理方式。</div>'
    return f'''<section class="view overview" id="overview" data-title="开始对接">
<div class="breadcrumb">项目文档 <span>/</span> 开始对接</div>
<header class="hero"><div class="eyebrow">FRONTEND INTEGRATION GUIDE</div><h1>{esc(TITLE)}</h1><p>{esc(CONFIG.get('description', '从页面动作找到接口，把参数、响应与异常一次对齐。'))}</p><div class="hero-bottom"><span class="audience">{esc(CONFIG.get('audience', '面向前端开发'))}</span><a href="#catalog">浏览接口 <span>↘</span></a></div></header>
<div class="stats"><div><strong>{len(records):02}</strong><span>接口</span></div><div><strong>{len(MODULES):02}</strong><span>模块</span></div><div><strong>{len(CONFIG.get('workflows', [])):02}</strong><span>调用流程</span></div><div><strong>{sum(1 for r in records if r['hints'].get('notes')):02}</strong><span>已补充联调提示</span></div></div>
<div class="section-heading"><div><div class="eyebrow">01 / GET STARTED</div><h2>接入前，先对齐这些</h2></div><span>项目级约定</span></div><div class="guide-grid">{guides}</div>
{''.join(f'<div class="legacy-note">{note}</div>' for note in HERO_NOTES)}
<div class="section-heading"><div><div class="eyebrow">02 / USER FLOWS</div><h2>按页面动作串起接口</h2></div><span>点击步骤查看契约</span></div>{render_workflows(records)}
<div class="section-heading" id="catalog"><div><div class="eyebrow">03 / API REFERENCE</div><h2>接口目录</h2></div><span>功能名称 · 方法 · 路径</span></div><div class="module-grid">{''.join(groups)}</div>
<div class="coverage"><h3>联调前待确认</h3><p>{missing_auth} 个接口未声明鉴权，{missing_errors} 个接口未声明异常响应。缺失声明不代表无需鉴权或不会失败，请结合后端实现确认。</p></div></section>'''


def render_enums():
    if not ENUMS:
        return ''
    cards = []
    for block in ENUMS:
        rows = ''.join(f'<tr><td><code>{esc(row[0])}</code></td><td>{esc(row[1]) if len(row) > 1 else ""}</td></tr>' for row in block.get('rows', []) if row)
        cards.append(f'<article class="module-card"><h3>{esc(block.get("title", ""))}</h3><table><thead><tr><th>字段</th><th>取值说明</th></tr></thead><tbody>{rows}</tbody></table></article>')
    return '<section class="view" id="enums" data-title="枚举速查"><div class="breadcrumb">项目文档 / 枚举速查</div><h1>枚举与取值速查</h1><div class="module-grid">' + ''.join(cards) + '</div></section>'


class _Checker(HTMLParser):
    VOID = {'br', 'img', 'hr', 'meta', 'link', 'input', 'source', 'wbr', 'area', 'base', 'embed', 'param', 'track', 'col'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors, self.ids, self.links = [], [], [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if attrs.get('href', '').startswith('#'):
            self.links.append(attrs['href'][1:])
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            self.errors.append('unexpected closing tag: ' + tag)


def verify(doc):
    checker = _Checker()
    checker.feed(doc)
    ids = set(checker.ids)
    return {'unclosed': checker.stack, 'bad_tags': checker.errors,
            'broken_anchors': sorted(set(checker.links) - ids),
            'duplicate_ids': sorted(i for i in ids if checker.ids.count(i) > 1)}


def build():
    records = collect_operations()
    agent_data = handoff_data(records)
    # Inline data is JSON, not executable script; escape HTML script terminators.
    agent_json = json.dumps(agent_data, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    nav = []
    for index, module in enumerate(MODULES):
        group = [r for r in records if r['module'] is module]
        links = []
        for r in group:
            summary = r['op'].get('summary') or r['op'].get('operationId') or r['path']
            searchable = search_contract([module['title'], r['method'], r['path'], r['op'], r['hints']], r['doc'])
            links.append(f'<a class="nav-item" href="#{r["id"]}" data-method="{r["method"]}" data-search="{esc(searchable)}"><span class="nav-label">{esc(summary)}</span><span class="nav-detail"><span class="method m-{r["method"].lower()}">{r["method"]}</span><code>{esc(r["path"])}</code></span></a>')
        nav.append(f'<div class="nav-group"><div class="nav-title"><span>{esc(module["title"])}</span><span>{len(group)}</span></div>{"".join(links)}</div>')
    method_options = ''.join(f'<option value="{m}">{m}</option>' for m in sorted({r['method'] for r in records}))
    css = (ASSETS / 'document.css').read_text(encoding='utf-8')
    js = (ASSETS / 'agent-handoff.js').read_text(encoding='utf-8') + '\n' + (ASSETS / 'document.js').read_text(encoding='utf-8')
    doc = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(TITLE)}</title><style>{css}</style></head>
<body><a href="#content" class="skip-link">跳到正文</a><div class="app-shell">
<aside class="sidebar" aria-label="文档导航"><a class="brand" href="#overview"><span class="brand-icon">↗</span><span>{esc(TITLE)}<small>接口对接手册</small></span></a>
<div class="search-box"><label class="sr-only" for="search">搜索接口、字段或功能</label><input id="search" type="search" placeholder="搜索接口、字段或功能…" autocomplete="off"><kbd>/</kbd></div>
<label class="sr-only" for="method-filter">筛选 HTTP 方法</label><select id="method-filter"><option value="">全部方法</option>{method_options}</select>
<nav><a class="overview-link" href="#overview">◫ <span>开始对接</span><span>↗</span></a><a class="overview-link agent-nav" href="#agent">✧ <span>交给 Agent</span><span>↗</span></a><div class="nav-caption">接口参考</div>{''.join(nav)}<p id="no-results" hidden>没有匹配接口，试试功能名或字段名。</p>
{('<a class="overview-link" href="#enums">≡ <span>枚举速查</span></a>' if ENUMS else '')}</nav>
<div class="sidebar-footer"><span class="offline-dot"></span> 离线可用 <span>·</span> {len(records)} 个接口</div></aside>
<div class="main-shell"><header class="topbar"><button type="button" id="menu-toggle" aria-expanded="false" aria-controls="sidebar-panel">☰ <span>导航</span></button><span>开发文档 <span class="topbar-divider">/</span> <strong id="current-title">开始对接</strong></span><button type="button" id="print-button">打印 / PDF ↗</button></header>
<main id="content" tabindex="-1">{render_overview(records)}{''.join(render_endpoint(r) for r in records)}{render_enums()}{render_agent_handoff(agent_data)}<footer>由接口契约生成 · {datetime.now().strftime('%Y-%m-%d')} · 业务约定以已确认说明为准</footer></main></div></div>
<div class="toast" role="status" aria-live="polite" hidden></div><script id="agent-data" type="application/json">{agent_json}</script><script>{js}</script></body></html>'''
    # aria-controls target is stable for mobile navigation.
    doc = doc.replace('<aside class="sidebar"', '<aside id="sidebar-panel" class="sidebar"', 1)
    result = verify(doc)
    bad = {k: v for k, v in result.items() if v}
    if bad:
        print(f'[error] 自检异常: {bad}', file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc, encoding='utf-8')
    print(f'生成: {OUT} ({OUT.stat().st_size / 1024:.0f} KB)')
    for module in MODULES:
        print(f'  - {module["title"]}: {sum(r["module"] is module for r in records)} 个接口')
    print(f'  合计: {len(records)} 个接口；自检通过（标签/锚点/唯一 ID）')
    return 0


def load_config(path):
    cfg = json.loads(Path(path).read_text(encoding='utf-8'))
    base = Path(path).resolve().parent
    for module in cfg.get('modules', []):
        p = Path(module['openapi'])
        module['openapi'] = str(p if p.is_absolute() else base / p)
    out = Path(cfg.get('out', 'api-doc.html'))
    cfg['out'] = str(out if out.is_absolute() else base / out)
    cfg['srcRoots'] = [str(Path(s) if Path(s).is_absolute() else base / s) for s in cfg.get('srcRoots', [])]
    return cfg


def apply_config(cfg):
    global TITLE, OUT, HERO_NOTES, ENUMS, MODULES, PARAM_DOCS, EXTRA_FIELD_DOCS, FIELD_DOCS, CONFIG
    CONFIG = cfg
    TITLE = cfg.get('title', '接口对接清单')
    OUT = Path(cfg.get('out', 'api-doc.html'))
    HERO_NOTES = cfg.get('heroNotes', [])
    ENUMS = cfg.get('enums', [])
    MODULES = cfg.get('modules', [])
    PARAM_DOCS = dict(cfg.get('paramDocs') or {})
    EXTRA_FIELD_DOCS = dict(cfg.get('fieldDocs') or {})
    FIELD_DOCS = extract_field_docs(cfg.get('srcRoots') or [], collect_schema_names(MODULES))


def parse_module_arg(raw):
    title, rest = raw.split('=', 1)
    path, _, note = rest.partition('|')
    return {'title': title.strip(), 'openapi': path.strip(), 'note': note.strip()}


def main():
    parser = argparse.ArgumentParser(description='OpenAPI 3 JSON -> 前端接口对接手册（单文件 HTML）')
    parser.add_argument('--config', help='配置文件（JSON）')
    parser.add_argument('--title', help='文档标题')
    parser.add_argument('--out', help='输出 HTML 路径')
    parser.add_argument('--module', action='append', default=[], help='标题=openapi.json 或 标题=openapi.json|备注')
    parser.add_argument('--src', action='append', default=[], help='补充字段注释的 Java 源码根目录，可重复')
    args = parser.parse_args()
    try:
        if args.config:
            cfg = load_config(args.config)
            if args.title:
                cfg['title'] = args.title
            if args.out:
                cfg['out'] = args.out
        else:
            cfg = {'title': args.title or '接口对接清单', 'out': args.out or 'api-doc.html',
                   'modules': [parse_module_arg(m) for m in args.module], 'srcRoots': args.src}
        if not cfg.get('modules'):
            parser.error('需要 --config 或至少一个 --module')
        for module in cfg['modules']:
            doc = load_openapi(module['openapi'])
            if not str(doc.get('openapi', '')).startswith('3.') or not isinstance(doc.get('paths'), dict):
                parser.error(f'需要包含 paths 的 OpenAPI 3 JSON: {module["openapi"]}')
        apply_config(cfg)
        return build()
    except (OSError, ValueError, KeyError, TypeError) as err:
        parser.error(str(err))


if __name__ == '__main__':
    sys.exit(main())
