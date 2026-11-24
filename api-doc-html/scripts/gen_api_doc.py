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

CLASS_RE = re.compile(r"\b(?:class|enum)\s+(\w+)")
JSON_PROP_RE = re.compile(r"@JsonProperty\s*\(([^)]*)\)")
JSON_PROP_VALUE_RE = re.compile(r'(?:value|name)\s*=\s*"([^"]+)"')
JSON_PROP_BARE_RE = re.compile(r'^\s*"([^"]+)"')
FIELD_RE = re.compile(r"(?:private|public|protected)\s+[^;=()]+?\s+(\w+)\s*(?:=|;)")
DOC_OPEN_RE = re.compile(r"^\s*/\*\*")
DOC_CLOSE_RE = re.compile(r"\*/\s*$")
DOC_STAR_RE = re.compile(r"^\s*\*\s?")

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
BASELINE_LABEL = "生产环境"
BASELINE_DATE = ""


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


def _strip_java_literals(line):
    line = re.sub(r'"(?:\\.|[^"\\])*"', '""', line)
    line = re.sub(r"'(?:\\.|[^'\\])*'", "''", line)
    return line.split('//', 1)[0]


def _json_prop_name(text):
    match = JSON_PROP_RE.search(text)
    if not match:
        return None
    args = match.group(1)
    value = JSON_PROP_VALUE_RE.search(args)
    if value:
        return value.group(1)
    bare = JSON_PROP_BARE_RE.match(args)
    return bare.group(1) if bare else None


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
            class_stack = []  # (class name, brace depth at class body)
            depth = 0
            pending_class = None
            pending_doc = None
            pending_json = None
            json_buffer = None
            in_doc = False
            in_block = False
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
                if in_block:
                    if "*/" in line:
                        in_block = False
                    continue
                if line.startswith("/*"):
                    if "*/" not in line:
                        in_block = True
                    continue
                if json_buffer is not None:
                    json_buffer += " " + line
                    if ")" in line:
                        pending_json = _json_prop_name(json_buffer)
                        json_buffer = None
                    continue
                if "@JsonProperty" in line:
                    pending_json = None
                    if ")" in line:
                        pending_json = _json_prop_name(line)
                    elif "(" in line:
                        json_buffer = line
                    continue

                code = _strip_java_literals(line)
                class_match = CLASS_RE.search(code)
                before = depth
                depth += code.count("{") - code.count("}")
                if class_match:
                    pending_class = class_match.group(1)
                    docs.setdefault(pending_class, {})
                if pending_class and "{" in code:
                    class_stack.append((pending_class, before + 1))
                    pending_class = None
                    pending_doc = None
                    pending_json = None
                while class_stack and depth < class_stack[-1][1]:
                    class_stack.pop()
                if class_match:
                    continue

                field_match = FIELD_RE.match(code)
                if field_match and class_stack:
                    prop = pending_json or field_match.group(1)
                    if pending_doc:
                        docs[class_stack[-1][0]].setdefault(prop, pending_doc)
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
LOCATION_LABELS = {'path': '路径', 'query': '查询', 'header': '请求头', 'cookie': 'Cookie'}


def esc(value):
    return html.escape(str(value), quote=True)


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
        bits.append('联合结构')
    return bits


def contract_rows(schema, doc, direction, prefix='', depth=0, seen=(), schema_name='',
                  change_fields=None, scope=''):
    ref = schema.get('$ref') if isinstance(schema, dict) else None
    if depth > 6 or (ref and ref in seen):
        return '<tr><td colspan="4" class="muted">递归或深层结构，请结合原始契约查看。</td></tr>'
    seen = seen + ((ref,) if ref else ())
    if ref:
        schema_name = ref.split('/')[-1]
    node = shape(schema, doc)
    if node.get('type') == 'array':
        return contract_rows(node.get('items', {}), doc, direction, prefix + '[]', depth + 1, seen,
                             schema_name, change_fields, scope)
    rows = []
    area = '请求' if direction == 'request' else '响应'
    marks = change_fields or {}
    for key, value in node.get('properties', {}).items():
        v = shape(value, doc)
        if v.get('readOnly' if direction == 'request' else 'writeOnly'):
            continue
        path = prefix + ('.' if prefix else '') + key
        desc = field_desc(schema_name, key) or v.get('description', '')
        required = key in node.get('required', [])
        change = marks.get((area, scope, path))
        row_class = ''
        cell_badge = ''
        if change:
            row_class = ' class="row-' + ('added' if change['kind'] == 'added' else 'changed') + '"'
            badge_class = 'add' if change['kind'] == 'added' else 'mod'
            badge_text = '新增' if change['kind'] == 'added' else '变更'
            cell_badge = f'<span class="cell-badge {badge_class}">{badge_text}</span>'
        chips = ''.join(f'<span>{esc(c)}</span>' for c in constraints(v))
        rows.append(f'<tr{row_class}><td><code>{esc(path)}</code></td>'
                    f'<td><code class="type">{esc(schema_type(value, doc))}</code></td>'
                    f'<td><span class="{"req" if required else "opt"}">{"必填" if required else "可选"}</span></td>'
                    f'<td>{esc(desc) if desc else "<span class=muted>暂无说明</span>"}{cell_badge}'
                    f'<div class="chips">{chips}</div></td></tr>')
        if v.get('properties') or v.get('type') == 'array':
            rows.append(contract_rows(value, doc, direction, path, depth + 1, seen,
                                      schema_name, change_fields, scope))
    return ''.join(rows)


def field_table(schema, doc, direction, change_fields=None, scope=''):
    rows = contract_rows(schema, doc, direction, change_fields=change_fields, scope=scope)
    if not rows:
        return f'<p class="empty-inline">类型 <code>{esc(schema_type(schema, doc))}</code>，未声明可展开字段；以原始契约为准。</p>'
    return ('<div class="table-wrap"><table><thead><tr><th>字段路径</th><th>类型</th><th>必填</th>'
            '<th>说明 / 约束</th></tr></thead><tbody>' + rows + '</tbody></table></div>')


def parameter_table(params, doc, change_fields=None):
    if not params:
        return '<p class="empty-inline">未声明路径、查询或请求头参数。</p>'
    rows = []
    marks = change_fields or {}
    for p in params:
        sch = shape(p.get('schema', {}), doc)
        desc = p.get('description') or PARAM_DOCS.get(p.get('name'), '')
        location = p.get('in', '')
        change = marks.get(('请求', '', f'{location}.{p.get("name", "")}'))
        row_class = ''
        cell_badge = ''
        if change:
            row_class = ' class="row-' + ('added' if change['kind'] == 'added' else 'changed') + '"'
            badge_class = 'add' if change['kind'] == 'added' else 'mod'
            badge_text = '新增' if change['kind'] == 'added' else '变更'
            cell_badge = f'<span class="cell-badge {badge_class}">{badge_text}</span>'
        chips = ''.join(f'<span>{esc(c)}</span>' for c in constraints(sch))
        rows.append(f'<tr{row_class}><td><code>{esc(p.get("name", ""))}</code><small>{esc(location)}</small></td>'
                    f'<td><code class="type">{esc(schema_type(sch, doc))}</code></td>'
                    f'<td><span class="{"req" if p.get("required") or location == "path" else "opt"}">'
                    f'{"必填" if p.get("required") or location == "path" else "可选"}</span></td>'
                    f'<td>{esc(desc) if desc else "<span class=muted>暂无说明</span>"}{cell_badge}'
                    f'<div class="chips">{chips}</div></td></tr>')
    return '<div class="table-wrap"><table><thead><tr><th>参数 / 位置</th><th>类型</th><th>必填</th><th>说明 / 约束</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'


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


def iter_module_operations(module):
    doc = load_openapi(module['openapi'])
    base = module.get('baseUrl', (doc.get('servers') or [{'url': ''}])[0].get('url', ''))
    for path, item in doc.get('paths', {}).items():
        item = resolve(item, doc)
        for method, raw in item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(raw, dict):
                continue
            op = resolve(raw, doc)
            params = {}
            for raw_param in item.get('parameters', []) + op.get('parameters', []):
                p = resolve(raw_param, doc)
                params[(p.get('name'), p.get('in'))] = p
            yield dict(module=module, doc=doc, base=base, path=path,
                       method=method.upper(), op=op, params=list(params.values()),
                       changes=[], change_status=None, breaking=False)


def collect_operations():
    records = []
    for index, module in enumerate(MODULES):
        for rec in iter_module_operations(module):
            key = rec['method'] + ' ' + rec['path']
            hints = {**CONFIG.get('operationDocs', {}).get(key, {}),
                     **module.get('operationDocs', {}).get(key, {})}
            if rec['op'].get('operationId'):
                hints.update(CONFIG.get('operationDocs', {}).get(rec['op']['operationId'], {}))
                hints.update(module.get('operationDocs', {}).get(rec['op']['operationId'], {}))
            identity = f'{index}:{key}'
            rec['id'] = 'ep-' + hashlib.sha256(identity.encode()).hexdigest()[:12]
            rec['hints'] = hints
            records.append(rec)
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


# ------------------------------------------------------------------ contract diff

def change(area, kind, field, before, after, text='', breaking=False, scope=''):
    return {'area': area, 'kind': kind, 'field': field, 'before': before, 'after': after,
            'text': text, 'breaking': breaking, 'scope': scope}


def field_sig(field):
    parts = [field['type'], '必填' if field['required'] else '可选']
    if field['constraints']:
        parts.append('、'.join(field['constraints']))
    return '，'.join(parts)


def flatten_fields(schema, doc, direction, prefix='', depth=0, seen=()):
    ref = schema.get('$ref') if isinstance(schema, dict) else None
    if depth > 8 or (ref and ref in seen):
        return {}
    seen = seen + ((ref,) if ref else ())
    node = shape(schema, doc)
    if node.get('type') == 'array':
        return flatten_fields(node.get('items', {}), doc, direction, prefix + '[]', depth + 1, seen)
    fields = {}
    for key, value in node.get('properties', {}).items():
        v = shape(value, doc)
        if v.get('readOnly' if direction == 'request' else 'writeOnly'):
            continue
        path = prefix + ('.' if prefix else '') + key
        fields[path] = {
            'type': schema_type(value, doc),
            'required': key in node.get('required', []),
            'constraints': tuple(constraints(v)),
        }
        if v.get('properties') or v.get('type') == 'array':
            fields.update(flatten_fields(value, doc, direction, path, depth + 1, seen))
    return fields


def parameter_map(params, doc):
    out = {}
    for p in params:
        location = p.get('in', '')
        name = p.get('name', '')
        sch = shape(p.get('schema', {}), doc)
        out[(location, name)] = {
            'type': schema_type(sch, doc),
            'required': bool(p.get('required') or location == 'path'),
            'constraints': tuple(constraints(sch)),
        }
    return out


def operation_signature(rec):
    op, doc = rec['op'], rec['doc']
    body = resolve(op.get('requestBody', {}), doc)
    responses = {}
    for code, raw in (op.get('responses') or {}).items():
        resp = resolve(raw, doc)
        responses[str(code)] = {
            'description': resp.get('description', ''),
            'content': {ctype: flatten_fields(media.get('schema', {}), doc, 'response')
                        for ctype, media in (resp.get('content') or {}).items()},
        }
    return {
        'path': rec['path'],
        'auth': auth_text(op, doc),
        'params': parameter_map(rec['params'], doc),
        'body_required': bool(body.get('required')),
        'body': {ctype: flatten_fields(media.get('schema', {}), doc, 'request')
                 for ctype, media in (body.get('content') or {}).items()},
        'responses': responses,
    }


def diff_fields(before, after, area, scope=''):
    rows = []
    for path in sorted(set(after) - set(before)):
        f = after[path]
        rows.append(change(area, 'added', path, '—', field_sig(f), '新增字段', scope=scope))
    for path in sorted(set(before) - set(after)):
        f = before[path]
        rows.append(change(area, 'removed', path, field_sig(f), '—', '移除字段', True, scope=scope))
    for path in sorted(set(before) & set(after)):
        b, a = before[path], after[path]
        bits = []
        if b['type'] != a['type']:
            bits.append(f'类型 {b["type"]} → {a["type"]}')
        if b['required'] != a['required']:
            bits.append('必填变化')
        if b['constraints'] != a['constraints']:
            bits.append('约束变更')
        if bits:
            rows.append(change(area, 'changed', path, field_sig(b), field_sig(a),
                               '；'.join(bits), b['type'] != a['type'] or b['required'] != a['required'],
                               scope=scope))
    return rows


def diff_params(before, after):
    rows = []
    for key in sorted(set(after) - set(before)):
        p = after[key]
        label = LOCATION_LABELS.get(key[0], key[0])
        rows.append(change('请求', 'added', f'{key[0]}.{key[1]}', '—', field_sig(p),
                           f'新增{label}参数'))
    for key in sorted(set(before) - set(after)):
        p = before[key]
        label = LOCATION_LABELS.get(key[0], key[0])
        rows.append(change('请求', 'removed', f'{key[0]}.{key[1]}', field_sig(p), '—',
                           f'移除{label}参数', True))
    for key in sorted(set(before) & set(after)):
        b, a = before[key], after[key]
        bits = []
        if b['type'] != a['type']:
            bits.append(f'类型 {b["type"]} → {a["type"]}')
        if b['required'] != a['required']:
            bits.append('必填变化')
        if b['constraints'] != a['constraints']:
            bits.append('约束变更')
        if bits:
            rows.append(change('请求', 'changed', f'{key[0]}.{key[1]}', field_sig(b), field_sig(a),
                               '；'.join(bits), b['type'] != a['type'] or b['required'] != a['required']))
    return rows


def diff_body(before, after):
    rows = []
    if before['body_required'] != after['body_required']:
        rows.append(change('请求', 'changed', 'requestBody',
                           '必填' if before['body_required'] else '可选',
                           '必填' if after['body_required'] else '可选',
                           '请求体必填变化', not before['body_required'] and after['body_required']))
    for ctype in sorted(set(after['body']) - set(before['body'])):
        rows.append(change('请求', 'added', ctype, '—', ctype, '新增请求体类型'))
        rows.extend(diff_fields({}, after['body'][ctype], '请求'))
    for ctype in sorted(set(before['body']) - set(after['body'])):
        rows.append(change('请求', 'removed', ctype, ctype, '—', '移除请求体类型', True))
    for ctype in sorted(set(before['body']) & set(after['body'])):
        rows.extend(diff_fields(before['body'][ctype], after['body'][ctype], '请求'))
    return rows


def diff_responses(before, after):
    rows = []
    for code in sorted(set(after) - set(before)):
        desc = after[code]['description']
        rows.append(change('响应', 'added', code, '—', desc or '已声明', '新增响应'))
        for ctype, fields in after[code]['content'].items():
            rows.append(change('响应', 'added', f'{code} {ctype}', '—', ctype, '新增响应内容类型'))
            rows.extend(diff_fields({}, fields, '响应', code))
    for code in sorted(set(before) - set(after)):
        desc = before[code]['description']
        rows.append(change('响应', 'removed', code, desc or '已声明', '—', '移除响应', True))
    for code in sorted(set(before) & set(after)):
        b, a = before[code], after[code]
        for ctype in sorted(set(a['content']) - set(b['content'])):
            rows.append(change('响应', 'added', f'{code} {ctype}', '—', ctype, '新增响应内容类型'))
            rows.extend(diff_fields({}, a['content'][ctype], '响应', code))
        for ctype in sorted(set(b['content']) - set(a['content'])):
            rows.append(change('响应', 'removed', f'{code} {ctype}', ctype, '—', '移除响应内容类型', True))
        for ctype in sorted(set(b['content']) & set(a['content'])):
            rows.extend(diff_fields(b['content'][ctype], a['content'][ctype], '响应', code))
    return rows


def diff_operations(before, after):
    b, a = operation_signature(before), operation_signature(after)
    rows = []
    if b['path'] != a['path']:
        rows.append(change('接口', 'changed', 'path', b['path'], a['path'], '路径变更', True))
    if b['auth'] != a['auth']:
        rows.append(change('鉴权', 'changed', 'security', b['auth'][0], a['auth'][0], '鉴权变更', True))
    rows.extend(diff_params(b['params'], a['params']))
    rows.extend(diff_body(b, a))
    rows.extend(diff_responses(b['responses'], a['responses']))
    return rows


def compute_diffs(records):
    summary = {'has_baseline': False, 'added': 0, 'modified': 0, 'removed': 0,
               'breaking': 0, 'total': 0, 'modules': []}
    for module in MODULES:
        current = [r for r in records if r['module'] is module]
        entry = {'module': module, 'baseline': bool(module.get('baseline')),
                 'added': [], 'modified': [], 'removed': [], 'unchanged': 0}
        summary['modules'].append(entry)
        if not module.get('baseline'):
            continue
        try:
            base_records = list(iter_module_operations({**module, 'openapi': module['baseline']}))
        except (OSError, ValueError, KeyError, TypeError) as err:
            print(f"[warn] 无法读取基线契约 {module['baseline']}: {err}", file=sys.stderr)
            entry['baseline'] = False
            continue
        summary['has_baseline'] = True
        by_id, by_path = {}, {}
        for br in base_records:
            oid = br['op'].get('operationId')
            if oid:
                by_id.setdefault(oid, []).append(br)
            by_path.setdefault((br['method'], br['path']), []).append(br)
        used = set()
        for rec in current:
            oid = rec['op'].get('operationId')
            match = None
            if oid and len(by_id.get(oid, [])) == 1:
                match = by_id[oid][0]
            else:
                candidates = by_path.get((rec['method'], rec['path']), [])
                if len(candidates) == 1:
                    match = candidates[0]
            if not match:
                rec['change_status'] = 'added'
                entry['added'].append(rec)
                continue
            used.add(id(match))
            rows = diff_operations(match, rec)
            if rows:
                rec['change_status'] = 'modified'
                rec['changes'] = rows
                rec['breaking'] = any(row['breaking'] for row in rows)
                entry['modified'].append(rec)
            else:
                entry['unchanged'] += 1
        for br in base_records:
            if id(br) not in used:
                br['change_status'] = 'removed'
                br['breaking'] = True
                summary_text = br['op'].get('summary') or br['op'].get('operationId') or br['path']
                br['changes'] = [change('接口', 'removed', f'{br["method"]} {br["path"]}',
                                        summary_text, '—', '接口已移除', True)]
                entry['removed'].append(br)
        summary['added'] += len(entry['added'])
        summary['modified'] += len(entry['modified'])
        summary['removed'] += len(entry['removed'])
        summary['breaking'] += sum(1 for r in entry['modified'] if r.get('breaking')) + len(entry['removed'])
    summary['total'] = summary['added'] + summary['modified'] + summary['removed']
    return summary


# ------------------------------------------------------------------ render helpers

def badge_for(rec):
    status = rec.get('change_status')
    if status == 'added':
        return '<span class="badge added">新增</span>'
    if status == 'modified':
        out = '<span class="badge modified">修改</span>'
        if rec.get('breaking'):
            out += '<span class="badge breaking">破坏性</span>'
        return out
    if status == 'removed':
        return '<span class="badge removed">移除</span><span class="badge breaking">破坏性</span>'
    return ''


def change_mark(kind):
    return {'added': '+', 'removed': '−', 'changed': '~'}.get(kind, '~')


def change_field(change_item):
    scope = change_item.get('scope') or ''
    field = change_item.get('field', '')
    return (scope + ' ' + field).strip() if scope else field


def render_change_item(item, compact=False):
    kind = item['kind']
    field = change_field(item)
    before = item.get('before', '')
    after = item.get('after', '')
    text = item.get('text', '')
    if compact:
        return (f'<div class="diff-item {kind}"><span class="mark">{change_mark(kind)}</span>'
                f'<div><code>{esc(field)}</code>'
                f'<p><span class="inline-old">{esc(before)}</span> → <span class="inline-new">{esc(after)}</span></p>'
                f'<small>{esc(text)}</small></div></div>')
    return (f'<li class="diff-item {kind}"><span class="mark">{change_mark(kind)}</span>'
            f'<div><code>{esc(field)}</code><p>{esc(before)} → {esc(after)}</p>'
            f'<small>{esc(text)}</small></div></li>')


def render_change_list(items, limit=4):
    shown = items[:limit]
    out = ''.join(render_change_item(item, True) for item in shown)
    if len(items) > limit:
        out += (f'<li class="diff-item muted"><span class="mark">…</span>'
                f'<div><p>还有 {len(items) - limit} 项，见变更明细。</p></div></li>')
    return out or '<li class="muted">无变化</li>'


def change_counts(changes):
    counts = {'请求': 0, '响应': 0, '接口': 0, '鉴权': 0}
    for item in changes:
        counts[item['area']] = counts.get(item['area'], 0) + 1
    return counts


def render_change_card(rec, link=True):
    status = rec.get('change_status')
    summary = rec['op'].get('summary') or rec['op'].get('operationId') or rec['path']
    method = rec['method']
    path = rec['path']
    title_link = f'<a class="change-link" href="#{rec["id"]}">查看契约 ↗</a>' if link and status != 'removed' else ''
    if status == 'removed':
        body = ('<div class="change-cols"><div class="change-col"><div class="change-col-title">影响</div>'
                '<ul class="diff-list"><li class="diff-item removed"><span class="mark">−</span>'
                '<div><p>生产环境存在，当前版本已移除。</p><small>前端需删除相关入口、调用与错误处理。</small></div></li></ul>'
                '</div></div>')
        return (f'<article class="change-card removed"><div class="change-head"><div class="change-title">'
                f'<span class="method {method.lower()}">{method}</span><code>{esc(path)}</code>'
                f'<strong>{esc(summary)}</strong>{badge_for(rec)}</div><span class="change-link muted">当前版本已移除</span></div>'
                f'{body}</article>')
    counts = change_counts(rec.get('changes', []))
    if status == 'added':
        body = ('<div class="change-cols"><div class="change-col"><div class="change-col-title">本次新增</div>'
                '<ul class="diff-list"><li class="diff-item added"><span class="mark">+</span>'
                '<div><p>生产环境不存在此接口。</p><small>按最新契约接入，不影响已有调用。</small></div></li></ul>'
                '</div></div>')
    else:
        request_items = [c for c in rec.get('changes', []) if c['area'] == '请求']
        response_items = [c for c in rec.get('changes', []) if c['area'] in ('响应', '接口', '鉴权')]
        body = ('<div class="change-cols">'
                f'<div class="change-col"><div class="change-col-title">请求 <span>{len(request_items)}</span></div>'
                f'<ul class="diff-list">{render_change_list(request_items)}</ul></div>'
                f'<div class="change-col"><div class="change-col-title">响应 <span>{len(response_items)}</span></div>'
                f'<ul class="diff-list">{render_change_list(response_items)}</ul></div>'
                '</div>')
    foot = ''
    if status == 'modified':
        foot = (f'<div class="change-foot"><span class="{"breaking-note" if rec.get("breaking") else ""}">'
                f'{"破坏性变更：需要前端调整。" if rec.get("breaking") else "兼容变更。"}</span>'
                f'<span>operationId：{esc(rec["op"].get("operationId", "未声明"))}</span></div>')
    return (f'<article class="change-card {status}"><div class="change-head"><div class="change-title">'
            f'<span class="method {method.lower()}">{method}</span><code>{esc(path)}</code>'
            f'<strong>{esc(summary)}</strong>{badge_for(rec)}</div>{title_link}</div>{body}{foot}</article>')


def render_change_detail(rec):
    status = rec.get('change_status')
    summary = rec['op'].get('summary') or rec['op'].get('operationId') or rec['path']
    if status == 'removed':
        return (f'<article class="change-detail" data-status="removed" data-breaking="true">'
                f'<div class="change-detail-head"><div class="change-detail-title">'
                f'<span class="method {rec["method"].lower()}">{rec["method"]}</span>'
                f'<code>{esc(rec["path"])}</code><strong>{esc(summary)}</strong>{badge_for(rec)}</div>'
                f'<span class="change-detail-meta">基线中存在</span></div>'
                f'<div class="removed-summary"><div><b>生产环境行为</b>{esc(summary)}</div>'
                f'<div><b>当前版本</b>接口已移除，不再保证可用</div>'
                f'<div><b>前端动作</b>删除入口、调用与错误处理</div></div>'
                f'<p class="detail-note breaking">破坏性变更：依赖此接口的页面需要移除或改用其他方式。</p></article>')
    if status == 'added':
        return (f'<article class="change-detail" data-status="added" data-breaking="false">'
                f'<div class="change-detail-head"><div class="change-detail-title">'
                f'<span class="method {rec["method"].lower()}">{rec["method"]}</span>'
                f'<code>{esc(rec["path"])}</code><strong>{esc(summary)}</strong>{badge_for(rec)}</div>'
                f'<span class="change-detail-meta">operationId：{esc(rec["op"].get("operationId", "未声明"))}</span></div>'
                f'<p class="detail-note">生产环境不存在此接口；当前版本新增。按最新契约接入即可。</p>'
                f'<p class="detail-note"><a class="link" href="#{rec["id"]}">查看完整契约 ↗</a></p></article>')
    rows = ''.join(
        f'<tr><td class="area">{esc(c["area"])}</td><td><code>{esc(change_field(c))}</code></td>'
        f'<td class="old">{esc(c["before"])}</td><td class="new">{esc(c["after"])}</td>'
        f'<td class="impact {"breaking" if c["breaking"] else ""}">{esc(c["text"])}</td></tr>'
        for c in rec.get('changes', []))
    return (f'<article class="change-detail" data-status="modified" data-breaking="{str(bool(rec.get("breaking"))).lower()}">'
            f'<div class="change-detail-head"><div class="change-detail-title">'
            f'<span class="method {rec["method"].lower()}">{rec["method"]}</span>'
            f'<code>{esc(rec["path"])}</code><strong>{esc(summary)}</strong>{badge_for(rec)}</div>'
            f'<span class="change-detail-meta">operationId：{esc(rec["op"].get("operationId", "未声明"))}</span></div>'
            f'<div class="diff-table-wrap"><table class="diff-table"><thead><tr><th>区域</th>'
            f'<th>字段 / 位置</th><th>{esc(BASELINE_LABEL)}</th><th>当前版本</th><th>影响</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>'
            f'<p class="detail-note {"breaking" if rec.get("breaking") else ""}">'
            f'{"破坏性变更：需要前端调整。" if rec.get("breaking") else "兼容变更：新增或放宽，不要求现有调用立即修改。"}</p></article>')


def change_text(rec):
    lines = [f'{rec["method"]} {rec["path"]} {rec["op"].get("summary") or ""}'.strip()]
    for c in rec.get('changes', []):
        lines.append(f'  {c["area"]} {change_field(c)}：{c["before"]} → {c["after"]}（{c["text"]}）')
    return '\n'.join(lines)


def change_strip(rec):
    if not rec['module'].get('baseline'):
        return ''
    status = rec.get('change_status')
    if status == 'added':
        return ('<div class="change-strip added"><div class="strip-main"><span class="eyebrow">CHANGES VS PRO</span>'
                '<strong>本次新增接口</strong></div><div class="strip-tags"><span class="badge added">新增</span></div>'
                '<a href="#changes">查看变更明细 ↗</a></div>')
    if status == 'modified':
        counts = change_counts(rec.get('changes', []))
        parts = []
        if counts.get('请求'):
            parts.append(f'请求 {counts["请求"]} 项')
        if counts.get('响应'):
            parts.append(f'响应 {counts["响应"]} 项')
        if counts.get('接口'):
            parts.append(f'接口 {counts["接口"]} 项')
        if counts.get('鉴权'):
            parts.append(f'鉴权 {counts["鉴权"]} 项')
        tags = '<span class="badge breaking">破坏性</span>' if rec.get('breaking') else '<span class="tag">兼容变更</span>'
        return (f'<div class="change-strip {"breaking" if rec.get("breaking") else "modified"}">'
                f'<div class="strip-main"><span class="eyebrow">CHANGES VS PRO</span>'
                f'<strong>本次变更：{" · ".join(parts) or "契约调整"}</strong></div>'
                f'<div class="strip-tags">{tags}</div><a href="#changes">查看变更明细 ↗</a></div>')
    return ('<div class="change-strip unchanged"><div class="strip-main"><span class="eyebrow">CHANGES VS PRO</span>'
            '<strong>本次无契约变化</strong></div><div class="strip-tags"><span class="badge neutral">无变更</span></div>'
            '<a href="#changes">查看变更明细 ↗</a></div>')


def render_change_rail(rec):
    if not rec['module'].get('baseline'):
        return ''
    status = rec.get('change_status')
    if status == 'added':
        return ('<aside class="change-rail added"><div class="rail-head"><div><div class="eyebrow">CHANGES VS PRO</div>'
                '<h2>本次变更</h2></div><span class="badge added">新增</span></div>'
                f'<div class="rail-meta">{esc(BASELINE_LABEL)}不存在此接口</div>'
                '<p class="rail-note">新增接口，不影响已有调用；按最新契约接入即可。</p>'
                '<a class="rail-link" href="#changes">查看完整变更 ↗</a></aside>')
    if status == 'modified':
        request_items = [c for c in rec.get('changes', []) if c['area'] == '请求']
        response_items = [c for c in rec.get('changes', []) if c['area'] == '响应']
        other_items = [c for c in rec.get('changes', []) if c['area'] in ('接口', '鉴权')]
        sections = []
        for title, items in [('请求', request_items), ('响应', response_items), ('其他', other_items)]:
            if items:
                sections.append(f'<section class="rail-section"><div class="rail-section-head">{title} '
                                f'<span>{len(items)}</span></div>'
                                f'{"".join(render_change_item(c, True) for c in items)}</section>')
        note = ('<div class="rail-note">破坏性变更：需要前端调整成功或失败分支。</div>'
                if rec.get('breaking') else '<div class="rail-note">兼容变更：新增或放宽，不要求现有调用立即修改。</div>')
        return (f'<aside class="change-rail"><div class="rail-head"><div><div class="eyebrow">CHANGES VS PRO</div>'
                f'<h2>本次变更</h2></div>{badge_for(rec)}</div>'
                f'<div class="rail-meta">{esc(BASELINE_LABEL)}{(" · " + esc(BASELINE_DATE)) if BASELINE_DATE else ""}</div>'
                f'{"".join(sections)}{note}'
                f'<button type="button" class="copy-btn" data-copy="{rec["id"]}-change">复制变更</button>'
                '<a class="rail-link" href="#changes">查看完整变更 ↗</a></aside>'
                f'<div id="{rec["id"]}-change" hidden>{esc(change_text(rec))}</div>')
    return ('<aside class="change-rail unchanged"><div class="rail-head"><div><div class="eyebrow">CHANGES VS PRO</div>'
            '<h2>本次变更</h2></div><span class="badge neutral">无变更</span></div>'
            f'<div class="rail-meta">{esc(BASELINE_LABEL)}{(" · " + esc(BASELINE_DATE)) if BASELINE_DATE else ""}</div>'
            '<div class="empty-change"><div class="empty-icon">✓</div><p>请求与响应均未变化。</p>'
            '<small>现有调用无需调整。</small></div></aside>')


def response_html(code, response, doc, change_fields=None):
    response = resolve(response, doc)
    ok = str(code).startswith('2')
    parts = [f'<div class="response-head"><span class="status {"ok" if ok else "err"}">{esc(code)}</span>'
             f'<span>{esc(response.get("description", ""))}</span></div>']
    for ctype, media in response.get('content', {}).items():
        parts.append(f'<h3>{esc(ctype)}</h3>')
        if media.get('schema'):
            parts.append(field_table(media['schema'], doc, 'response', change_fields, str(code)))
    if not response.get('content'):
        message = ('该状态码不包含响应体，前端无需调用 response.json()。' if str(code) in ('204', '205') else
                   '未声明响应内容；是否无响应体需结合状态码与实际实现确认。')
        parts.append(f'<p class="empty-inline">{message}</p>')
    if response.get('headers'):
        parts.append('<div class="eyebrow" style="margin-top:14px">响应头</div>')
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
    change_fields = {(c['area'], c.get('scope', ''), c['field']): c for c in rec.get('changes', [])}
    request = '<h3>路径、查询与请求头</h3>' + parameter_table(rec['params'], doc, change_fields)
    body = resolve(op.get('requestBody', {}), doc)
    for ctype, media in body.get('content', {}).items():
        request += (f'<h3>请求体 <span class="tag">{esc(ctype)}</span> '
                    f'<span class="{"req" if body.get("required") else "opt"}">'
                    f'{"必填" if body.get("required") else "可选"}</span></h3>')
        request += field_table(media.get('schema', {}), doc, 'request', change_fields)
    if not body.get('content'):
        request += '<div class="quiet-note">该接口未声明请求体。</div>'
    successes, failures = [], []
    for code, raw in (op.get('responses') or {}).items():
        response = resolve(raw, doc)
        (successes if str(code).startswith('2') else failures).append(response_html(code, response, doc, change_fields))
    if not successes:
        successes.append('<div class="quiet-note">未声明成功响应，请向后端确认。</div>')
    if not failures:
        failures.append('<div class="quiet-note">未声明异常响应。请确认鉴权失败、校验失败与业务异常的状态码及返回结构。</div>')
    overview = (f'<h3>什么时候调用</h3><p class="prose">{esc(usage) if usage else "尚未补充使用场景，可在 operationDocs 中添加。"}</p>'
                f'<div class="auth-card"><span class="eyebrow">{esc(label)}</span><p>{esc(auth)}</p></div>'
                f'<h3>联调提示</h3>{notes_html or "<p class=empty-inline>暂无额外约定；字段约束与异常响应见对应标签。</p>"}')
    panels = [('overview', '使用说明', overview), ('request', '请求', request),
              ('response', '成功响应', ''.join(successes)), ('errors', '异常响应', ''.join(failures))]
    tab_html = ''.join(f'<button type="button" role="tab" id="{anchor}-tab-{key}" aria-controls="{anchor}-{key}" '
                       f'aria-selected="{str(i == 0).lower()}" tabindex="{0 if i == 0 else -1}">{title}</button>'
                       for i, (key, title, _) in enumerate(panels))
    content_html = ''.join(f'<div class="tab-panel{" active" if i == 0 else ""}" id="{anchor}-{key}" '
                           f'role="tabpanel" aria-labelledby="{anchor}-tab-{key}">{content}</div>'
                           for i, (key, _, content) in enumerate(panels))
    rail = render_change_rail(rec)
    workspace_class = 'workspace' if rail else 'workspace single'
    departure = op.get('deprecated')
    deprecated_tag = '<span class="badge breaking">已弃用</span>' if departure else ''
    return f'''<section class="view endpoint" id="{anchor}" data-title="{esc(summary)}">
<div class="breadcrumb">接口参考 <span>/</span> {esc(rec['module']['title'])} <span>/</span> {esc(op.get('operationId', summary))}</div>
<div class="endpoint-title"><div><div class="eyebrow">{esc(rec['module']['title'])}</div><h1>{esc(summary)}</h1></div>{deprecated_tag}</div>
<div class="endpoint-bar"><span class="method {rec['method'].lower()}">{rec['method']}</span><code>{esc(rec['path'])}</code><button type="button" class="copy-btn" data-copy="{anchor}-url">复制 URL</button></div>
<div class="endpoint-meta">{chips}<span class="auth-badge">{esc(label)}</span><span>Base URL <code>{esc(rec['base']) or '待确认'}</code></span><a class="agent-entry" href="#agent" data-agent-scope="{anchor}">交给 Agent ↗</a></div>
<span id="{anchor}-url" hidden>{esc(rec['base'].rstrip('/') + rec['path'])}</span>
{change_strip(rec)}
<div class="{workspace_class}"><div class="contract"><div class="tabs" role="tablist" aria-label="{esc(summary)}详情">{tab_html}</div>{content_html}</div>{rail}</div></section>'''


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
            steps.append(f'<li><a href="#{r["id"]}">{esc(r["op"].get("summary") or r["path"])} <span>↗</span></a>'
                         f'<p>{esc(step.get("note", ""))}</p></li>')
        cards.append(f'<article class="flow-card"><h3>{esc(flow.get("title", ""))}</h3>'
                     f'<p>{esc(flow.get("description", ""))}</p><ol>{"".join(steps)}</ol></article>')
    return '<div class="flow-grid">' + ''.join(cards) + '</div>' if cards else '<div class="quiet">尚未补充页面调用流程。可根据真实业务配置 workflows，将页面动作关联到接口。</div>'


def render_overview(records, diffs):
    groups = []
    for module in MODULES:
        operations = [r for r in records if r['module'] is module]
        base = operations[0]['base'] if operations else module.get('baseUrl', '')
        links = ''.join(
            f'<a class="endpoint-link" href="#{r["id"]}"><span class="method {r["method"].lower()}">{r["method"]}</span>'
            f'<span class="grow"><strong>{esc(r["op"].get("summary") or r["path"])}</strong><code>{esc(r["path"])}</code></span>'
            f'{badge_for(r)}<span class="arrow">↗</span></a>' for r in operations)
        groups.append(f'<article class="module-card"><div class="module-card-head"><h3>{esc(module["title"])}</h3>'
                      f'<span>{len(operations)} 个接口</span></div><code class="base-url">{esc(base) or "Base URL 待确认"}</code>'
                      f'<p class="muted">{esc(module.get("note", ""))}</p>{links or "<p class=muted>无接口</p>"}</article>')
    missing_auth = sum(auth_text(r['op'], r['doc'])[0] == '待确认' for r in records)
    missing_errors = sum(not any(not str(c).startswith('2') for c in r['op'].get('responses', {})) for r in records)
    pending = missing_auth + missing_errors
    guides = ''.join(f'<article class="guide-card"><span class="guide-index">{i + 1:02}</span>'
                     f'<h3>{esc(g["title"])}</h3><p>{esc(g["text"])}</p></article>'
                     for i, g in enumerate(CONFIG.get('integration', [])))
    if not guides:
        guides = '<div class="quiet">尚未补充接入约定。建议确认登录态来源、分页、空值、时间与业务错误的处理方式。</div>'
    baseline_pill = ''
    if diffs['has_baseline']:
        baseline_pill = (f'<span class="pill pro"><span class="dot"></span>变更基线：{esc(BASELINE_LABEL)}'
                         f'{" · " + esc(BASELINE_DATE) if BASELINE_DATE else ""}</span>')
    else:
        baseline_pill = '<span class="pill"><span class="dot"></span>未提供变更基线</span>'
    change_summary = ''
    change_cards = ''
    if diffs['has_baseline']:
        cards = []
        for entry in diffs['modules']:
            for rec in entry['added'] + entry['modified'] + entry['removed']:
                cards.append(render_change_card(rec))
        change_cards = ''.join(cards[:8])
        more = ''
        if len(cards) > 8:
            more = f'<p class="detail-note"><a class="link" href="#changes">查看全部 {len(cards)} 项变更 ↗</a></p>'
        change_summary = f'''<div class="section-head"><div><div class="eyebrow">01 / CHANGES</div><h2>本次变更</h2></div><span class="side">对比 {esc(BASELINE_LABEL)}{(" · " + esc(BASELINE_DATE)) if BASELINE_DATE else ""}</span></div>
<div class="change-overview"><div class="change-summary"><span class="label">共 {diffs["total"]} 项</span>
<span class="chip add">新增 <b>{diffs["added"]}</b></span><span class="chip mod">修改 <b>{diffs["modified"]}</b></span>
<span class="chip del">移除 <b>{diffs["removed"]}</b></span><span class="chip brk">破坏性 <b>{diffs["breaking"]}</b></span>
<span class="grow"></span><a class="link" href="#changes" style="font-size:10px">查看完整变更明细 ↗</a></div>
<div class="change-cards">{change_cards}</div>{more}</div>'''
    change_count = diffs['total'] if diffs['has_baseline'] else 0
    stats = (f'<div class="stats"><div class="stat"><strong>{len(records):02}</strong><span>当前接口</span>'
             f'<small>{len(MODULES)} 个模块</small></div>'
             f'<div class="stat"><strong>{change_count:02}</strong><span>本次变更</span><small>对比 {esc(BASELINE_LABEL) if diffs["has_baseline"] else "未提供基线"}</small></div>'
             f'<div class="stat alert"><strong>{diffs["breaking"]:02}</strong><span>破坏性变更</span><small>需要前端调整</small></div>'
             f'<div class="stat"><strong>{pending:02}</strong><span>待确认</span><small>契约缺口</small></div></div>')
    change_link = '<a href="#changes">查看本次变更 ↗</a>' if diffs['has_baseline'] else ''
    hero_bottom = (f'{baseline_pill}'
                   f'<span class="pill">{esc(CONFIG.get("audience", "面向前端开发"))}</span>'
                   f'<span>生成于 {datetime.now().strftime("%Y-%m-%d")}</span><span class="grow"></span>'
                   f'{change_link}')
    hero_notes = ''.join(f'<div class="quiet" style="margin-top:10px">{note}</div>' for note in HERO_NOTES)
    agent_link = '<a href="#agent">带入 Agent 任务包 ↗</a>' if diffs['has_baseline'] else ''
    coverage = (f'<div class="coverage"><div><h3>联调前待确认</h3><p>{missing_auth} 个接口未声明鉴权，'
                f'{missing_errors} 个接口未声明异常响应。缺失声明不代表无需鉴权或不会失败，请结合后端实现确认。</p></div>'
                f'{agent_link}</div>')
    return f'''<section class="view active overview" id="overview" data-title="开始对接">
<div class="breadcrumb">项目文档 <span>/</span> 开始对接</div>
<header class="hero"><div class="eyebrow">FRONTEND INTEGRATION GUIDE</div><h1>{esc(TITLE)}</h1>
<p>{esc(CONFIG.get('description', '先看本次变更，再查完整契约。页面只保留前端真正需要的字段、约束和错误分支。'))}</p>
<div class="hero-meta">{hero_bottom}</div></header>
{stats}
{change_summary}
<div class="section-head"><div><div class="eyebrow">02 / GET STARTED</div><h2>接入前，先对齐这些</h2></div><span class="side">项目级约定</span></div>
<div class="guide-grid">{guides}</div>{hero_notes}
<div class="section-head"><div><div class="eyebrow">03 / USER FLOWS</div><h2>按页面动作串起接口</h2></div><span class="side">点击步骤查看契约</span></div>
{render_workflows(records)}
<div class="section-head" id="catalog"><div><div class="eyebrow">04 / API REFERENCE</div><h2>接口目录</h2></div><span class="side">功能名称 · 方法 · 路径</span></div>
<div class="module-grid">{''.join(groups)}</div>
{coverage}
<footer><span>由接口契约生成 · {datetime.now().strftime('%Y-%m-%d')} · 业务约定以已确认说明为准</span>
<span>变更基线：{esc(BASELINE_LABEL) if diffs["has_baseline"] else "未提供"}</span></footer></section>'''


def render_changes(records, diffs):
    if not diffs['has_baseline']:
        return ''
    modified = [r for e in diffs['modules'] for r in e['modified']]
    added = [r for e in diffs['modules'] for r in e['added']]
    removed = [r for e in diffs['modules'] for r in e['removed']]
    unchanged = [r for r in records if r['module'].get('baseline') and not r.get('change_status')]
    copy_lines = [f'本次变更（对比 {BASELINE_LABEL}{("，" + BASELINE_DATE) if BASELINE_DATE else ""}）',
                  f'新增 {len(added)} 项 · 修改 {len(modified)} 项 · 移除 {len(removed)} 项 · 破坏性 {diffs["breaking"]} 项']
    for rec in added:
        copy_lines.append(f'+ {rec["method"]} {rec["path"]} {rec["op"].get("summary") or ""}（新增）'.strip())
    for rec in modified:
        copy_lines.append(f'~ {rec["method"]} {rec["path"]} {rec["op"].get("summary") or ""}'.strip())
        for c in rec.get('changes', []):
            copy_lines.append(f'  {c["area"]} {change_field(c)}：{c["before"]} → {c["after"]}（{c["text"]}）')
    for rec in removed:
        copy_lines.append(f'- {rec["method"]} {rec["path"]} {rec["op"].get("summary") or ""}（移除，破坏性）'.strip())
    def group(status, title, items):
        if not items:
            return ''
        cards = ''.join(render_change_detail(r) for r in items)
        return (f'<div class="change-group" data-group="{status}"><div class="change-group-head">'
                f'<h2>{title}</h2><span class="count">{len(items)}</span></div>{cards}</div>')
    unchanged_html = ''
    if unchanged:
        cards = ''.join(
            f'<article class="change-detail" data-status="unchanged" data-breaking="false" style="border-left:3px solid #cfded7">'
            f'<div class="change-detail-head"><div class="change-detail-title">'
            f'<span class="method {r["method"].lower()}">{r["method"]}</span><code>{esc(r["path"])}</code>'
            f'<strong>{esc(r["op"].get("summary") or r["path"])}</strong><span class="badge neutral">无变更</span></div>'
            f'<span class="change-detail-meta">operationId：{esc(r["op"].get("operationId", "未声明"))}</span></div>'
            f'<p class="detail-note">请求与响应均未变化。可作为本次接入的稳定参照。</p></article>'
            for r in unchanged)
        unchanged_html = (f'<div class="change-group" data-group="unchanged"><div class="change-group-head">'
                          f'<h2>未变更</h2><span class="count">{len(unchanged)}</span></div>{cards}</div>')
    return f'''<section class="view" id="changes" data-title="本次变更">
<div class="breadcrumb">项目文档 <span>/</span> 本次变更</div>
<div class="changes-hero"><div><div class="eyebrow">CHANGES VS PRODUCTION</div><h1>本次变更</h1>
<p>对比 {esc(BASELINE_LABEL)}{("（" + esc(BASELINE_DATE) + "）") if BASELINE_DATE else ""}。新增 {len(added)} 个接口、修改 {len(modified)} 个接口、移除 {len(removed)} 个接口；其中 {diffs["breaking"]} 项为破坏性变更。</p></div>
<span class="pill pro"><span class="dot"></span>{esc(BASELINE_LABEL)}{(" · " + esc(BASELINE_DATE)) if BASELINE_DATE else ""}</span></div>
<div class="changes-toolbar"><div class="segmented" role="group" aria-label="按变更类型筛选">
<button type="button" class="active" data-change-filter="all">全部</button>
<button type="button" data-change-filter="added">新增 <span>{len(added)}</span></button>
<button type="button" data-change-filter="modified">修改 <span>{len(modified)}</span></button>
<button type="button" data-change-filter="removed">移除 <span>{len(removed)}</span></button></div>
<label class="switch"><input type="checkbox" id="breaking-only"> 只看破坏性</label><span class="grow"></span>
<button type="button" class="copy-btn" data-copy="changes-copy">复制变更清单</button></div>
<div id="changes-copy" hidden>{esc(chr(10).join(copy_lines))}</div>
{group('modified', '修改接口', modified)}
{group('added', '新增接口', added)}
{group('removed', '移除接口', removed)}
{unchanged_html}
</section>'''


def render_enums():
    if not ENUMS:
        return ''
    cards = []
    for block in ENUMS:
        rows = ''.join(f'<tr><td><code>{esc(row[0])}</code></td><td>{esc(row[1]) if len(row) > 1 else ""}</td></tr>'
                       for row in block.get('rows', []) if row)
        cards.append(f'<article class="module-card"><h3>{esc(block.get("title", ""))}</h3>'
                     f'<table><thead><tr><th>字段</th><th>取值说明</th></tr></thead><tbody>{rows}</tbody></table></article>')
    return ('<section class="view" id="enums" data-title="枚举速查"><div class="breadcrumb">项目文档 / 枚举速查</div>'
            '<h1>枚举与取值速查</h1><div class="module-grid">' + ''.join(cards) + '</div></section>')


def handoff_data(records, diffs):
    copy = lambda value: json.loads(json.dumps(value))
    modules, operations, scopes, removed = [], [], [], []
    for index, module in enumerate(MODULES):
        group = [r for r in records if r['module'] is module]
        module_id = f'module-{index}'
        doc = load_openapi(module['openapi'])
        source = copy({key: doc[key] for key in ('openapi', 'info', 'servers', 'security', 'components') if key in doc})
        if 'baseUrl' in module:
            source['servers'] = [{'url': module['baseUrl']}]
        for name, schema in source.get('components', {}).get('schemas', {}).items():
            if not isinstance(schema, dict):
                continue
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
            summary = op.get('summary') or op.get('operationId') or rec['path']
            operations.append(dict(id=rec['id'], moduleId=module_id, path=rec['path'], method=rec['method'],
                                   operationId=op.get('operationId', ''), summary=summary, usage=usage,
                                   notes=copy(rec['hints'].get('notes', [])), authentication=label + '：' + auth,
                                   pending=pending, contract=op, changeStatus=rec.get('change_status'),
                                   changes=copy(rec.get('changes', [])), breaking=rec.get('breaking', False)))
        for br in next((e for e in diffs['modules'] if e['module'] is module), {'removed': []})['removed']:
            removed.append(dict(id=br.get('id', ''), moduleId=module_id, endpoint=f'{br["method"]} {br["path"]}',
                                method=br['method'], path=br['path'],
                                summary=br['op'].get('summary') or br['op'].get('operationId') or br['path'],
                                moduleTitle=module['title']))
    for index, flow in enumerate(CONFIG.get('workflows', [])):
        steps, ids = [], []
        for step in flow.get('steps', []):
            matches = [r for r in records if (not step.get('module') or step['module'] == r['module']['title']) and
                       ((step.get('operationId') and r['op'].get('operationId') == step['operationId']) or
                        (step.get('endpoint') and step['endpoint'] == r['method'] + ' ' + r['path']))]
            if len(matches) != 1:
                raise ValueError(f'流程 {flow.get("title")}: 接口引用需唯一匹配，实际 {len(matches)} 条: {step}')
            ids.append(matches[0]['id'])
        scopes.append(dict(id=f'flow-{index}', label='流程 · ' + flow.get('title', ''), operations=ids))
    changed_ids = [r['id'] for r in records if r.get('change_status') in ('added', 'modified')]
    prefix = []
    if changed_ids or removed:
        prefix.append(dict(id='changed', label=f'本次变更的接口（{len(changed_ids) + len(removed)}）',
                           operations=changed_ids))
    prefix.append(dict(id='all', label=f'全部接口（{len(records)}）', operations=[r['id'] for r in records]))
    scopes = prefix + scopes
    scopes.extend(dict(id=r['id'], label=r['module']['title'] + ' · ' + r['method'] + ' ' + r['path'],
                       operations=[r['id']]) for r in records)
    agent = CONFIG.get('agent', {})
    return dict(title=TITLE, audience=CONFIG.get('audience', '前端开发'), modules=modules, operations=operations,
                scopes=scopes, removed=removed, hasBaseline=diffs['has_baseline'],
                baselineLabel=BASELINE_LABEL, baselineDate=BASELINE_DATE,
                task=agent.get('task', ''))


def render_agent_handoff(data):
    options = ''.join(f'<option value="{s["id"]}">{esc(s["label"])}</option>' for s in data['scopes'])
    default_scope = data['scopes'][0]
    default_count = len(default_scope['operations'])
    changes = sum(1 for op in data['operations']
                  if op['id'] in default_scope['operations'] and (op.get('changeStatus') or op.get('changes')))
    return f'''<section class="view" id="agent" data-title="交给 Agent">
<div class="breadcrumb">项目文档 <span>/</span> 交给 Agent</div>
<div class="eyebrow">AGENT HANDOFF</div><h1>把这次要调整的接口交给前端 Agent</h1>
<p class="handoff-intro">选择一个范围、补充任务，复制任务包。包内只有本次任务、变更清单和所选接口的最新 OpenAPI 契约；通用编码约束由前端 Agent 按其仓库规范处理。</p>
<div class="handoff-controls"><div><label for="agent-scope">01 · 选择接口范围</label><select id="agent-scope">{options}</select></div>
<div><label for="agent-task">02 · 本次要调整什么（可选）</label><textarea id="agent-task" rows="3" placeholder="例如：把订单列表新增的筛选与状态接入已有页面，处理取消接口的新响应。">{esc(data['task'])}</textarea></div></div>
<div class="handoff-toolbar"><div><strong>03 · 交给 Agent</strong><p id="agent-summary">{default_count} 个接口 · {changes} 项接口变更 · 含最新契约</p></div>
<div class="handoff-actions"><button type="button" class="btn primary" data-copy="agent-packet">复制任务包</button>
<button type="button" class="btn" id="agent-download-md">下载 .md</button><button type="button" class="btn" id="agent-download-json">下载契约 .json</button></div></div>
<p class="handoff-note">任务包不包含「工作方式」「验收要求」等通用模板，也不读取本机令牌或调用真实接口。分享前请核对契约说明中是否含有不应外发的业务数据。</p>
<div class="packet"><div class="packet-head"><span>任务包预览 · Markdown</span><span>默认范围：{esc(default_scope['label'])}</span></div>
<pre id="agent-packet"></pre></div>
<noscript><p class="quiet">此模块的范围选择与导出需要启用 JavaScript。接口参考仍可直接阅读。</p></noscript></section>'''


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
    if not records:
        print('[error] 未匹配到任何接口；请检查模块 OpenAPI 或过滤范围。', file=sys.stderr)
        return 1
    diffs = compute_diffs(records)
    agent_data = handoff_data(records, diffs)
    agent_json = json.dumps(agent_data, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    nav = []
    for module in MODULES:
        group = [r for r in records if r['module'] is module]
        links = []
        for r in group:
            summary = r['op'].get('summary') or r['op'].get('operationId') or r['path']
            searchable = search_contract([module['title'], r['method'], r['path'], r['op'], r['hints']], r['doc'])
            if r.get('changes'):
                searchable += ' ' + ' '.join(c['text'] + ' ' + c['field'] for c in r['changes'])
            links.append(f'<a class="nav-item" href="#{r["id"]}" data-method="{r["method"]}" data-changed="{r.get("change_status") or ""}" data-search="{esc(searchable)}">'
                         f'<span class="nav-label">{esc(summary)} {badge_for(r)}</span>'
                         f'<span class="nav-detail"><span class="method {r["method"].lower()}">{r["method"]}</span><code>{esc(r["path"])}</code></span></a>')
        nav.append(f'<div class="nav-group"><div class="nav-title"><span>{esc(module["title"])}</span><span>{len(group)}</span></div>{"".join(links)}</div>')
    method_options = ''.join(f'<option value="{m}">{m}</option>' for m in sorted({r['method'] for r in records}))
    changed_switch = ('<label class="switch"><input type="checkbox" id="changed-only"> 只看本次变更</label>'
                      if diffs['has_baseline'] else '')
    changes_nav = (f'<a class="nav-main" href="#changes">本次变更 <span class="count">{diffs["total"]}</span></a>'
                   if diffs['has_baseline'] else '')
    enums_nav = '<a class="nav-main" href="#enums">枚举速查</a>' if ENUMS else ''
    baseline_footer = (f'变更基线 <b>{esc(BASELINE_LABEL)}</b><br>{esc(BASELINE_DATE)} · ' if diffs['has_baseline'] else '')
    css = (ASSETS / 'document.css').read_text(encoding='utf-8')
    js = (ASSETS / 'agent-handoff.js').read_text(encoding='utf-8') + '\n' + (ASSETS / 'document.js').read_text(encoding='utf-8')
    doc = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(TITLE)}</title><style>{css}</style></head>
<body><a href="#content" class="skip">跳到正文</a><div class="app">
<aside class="sidebar" id="sidebar" aria-label="文档导航"><a class="brand" href="#overview"><span class="brand-mark">Δ</span><span>{esc(TITLE)}<small>前端对接手册</small></span></a>
<div class="search"><label class="sr-only" for="nav-search">搜索接口、字段或变更</label><input id="nav-search" type="search" placeholder="搜索接口、字段或变更…" autocomplete="off"><kbd>/</kbd></div>
<div class="side-filters"><label class="sr-only" for="method-filter">筛选 HTTP 方法</label>
<select id="method-filter"><option value="">全部方法</option>{method_options}</select>{changed_switch}</div>
<nav><a class="nav-main" href="#overview">开始对接</a>{changes_nav}<a class="nav-main" href="#agent">交给 Agent</a>
<div class="nav-caption">接口参考</div>{''.join(nav)}{enums_nav}<p class="no-results" id="no-results" hidden>没有匹配接口，试试功能名或字段名。</p></nav>
<div class="sidebar-footer">{baseline_footer}离线可用 · {len(records)} 个接口</div></aside>
<div class="main"><header class="topbar"><div style="display:flex;align-items:center;gap:12px"><button type="button" id="menu-toggle" aria-expanded="false" aria-controls="sidebar">☰ <span>导航</span></button>
<div class="crumbs">开发文档<span>/</span><strong id="current-title">开始对接</strong></div></div>
<div class="topbar-right"><button type="button" id="print-button">打印 / PDF ↗</button></div></header>
<main id="content" tabindex="-1">{render_overview(records, diffs)}{render_changes(records, diffs)}{''.join(render_endpoint(r) for r in records)}{render_enums()}{render_agent_handoff(agent_data)}</main></div></div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<script id="agent-data" type="application/json">{agent_json}</script><script>{js}</script></body></html>'''
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
    if diffs['has_baseline']:
        print(f'  变更: 新增 {diffs["added"]} · 修改 {diffs["modified"]} · 移除 {diffs["removed"]} · 破坏性 {diffs["breaking"]}')
    return 0


def load_config(path):
    cfg = json.loads(Path(path).read_text(encoding='utf-8'))
    base = Path(path).resolve().parent
    for module in cfg.get('modules', []):
        p = Path(module['openapi'])
        module['openapi'] = str(p if p.is_absolute() else base / p)
        if module.get('baseline'):
            bp = Path(module['baseline'])
            module['baseline'] = str(bp if bp.is_absolute() else base / bp)
    out = Path(cfg.get('out', 'api-doc.html'))
    cfg['out'] = str(out if out.is_absolute() else base / out)
    cfg['srcRoots'] = [str(Path(s) if Path(s).is_absolute() else base / s) for s in cfg.get('srcRoots', [])]
    return cfg


def apply_config(cfg):
    global TITLE, OUT, HERO_NOTES, ENUMS, MODULES, PARAM_DOCS, EXTRA_FIELD_DOCS, FIELD_DOCS, CONFIG
    global BASELINE_LABEL, BASELINE_DATE
    CONFIG = cfg
    TITLE = cfg.get('title', '接口对接清单')
    OUT = Path(cfg.get('out', 'api-doc.html'))
    HERO_NOTES = cfg.get('heroNotes', [])
    ENUMS = cfg.get('enums', [])
    MODULES = cfg.get('modules', [])
    PARAM_DOCS = dict(cfg.get('paramDocs') or {})
    EXTRA_FIELD_DOCS = dict(cfg.get('fieldDocs') or {})
    BASELINE_LABEL = cfg.get('baselineLabel', '生产环境')
    BASELINE_DATE = cfg.get('baselineDate', '')
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
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as err:
        parser.error(str(err))


if __name__ == '__main__':
    sys.exit(main())
