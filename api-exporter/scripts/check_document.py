#!/usr/bin/env python3
"""Sanity-check an OpenAPI document produced by api-exporter.

Usage:
    python3 check_document.py <openapi.json>

Prints a short summary (paths / operations / schemas) and fails (exit 1) on:
  - dangling $ref
  - duplicate operationId
  - an operation with no responses, or no 2xx response
  - {placeholders} in a path without a matching `in: path` parameter (or vice versa)

Non-fatal findings (unreferenced schemas, missing operationId) are warnings.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
PLACEHOLDER = re.compile(r"\{([^}/]+)\}")


def walk(node):
    """Yield every dict inside the document."""
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            yield current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <openapi.json>", file=sys.stderr)
        return 2

    try:
        with open(argv[1], encoding="utf-8") as handle:
            doc = json.load(handle)
    except (OSError, json.JSONDecodeError) as err:
        print(f"[error] 无法读取 {argv[1]}: {err}")
        return 1

    errors: list[str] = []
    warnings: list[str] = []

    schemas = (doc.get("components") or {}).get("schemas") or {}
    servers = [s.get("url", "?") for s in (doc.get("servers") or [])]

    # --- dangling $ref -------------------------------------------------------
    referenced: set[str] = set()
    for obj in walk(doc):
        ref = obj.get("$ref")
        if not isinstance(ref, str):
            continue
        prefix = "#/components/schemas/"
        if ref.startswith(prefix):
            name = ref[len(prefix):]
            referenced.add(name)
            if name not in schemas:
                errors.append(f"悬空 $ref: {ref}")
        else:
            warnings.append(f"未知引用形式（脚本未校验）: {ref}")

    # --- operations ----------------------------------------------------------
    operations = 0
    by_method: Counter[str] = Counter()
    operation_ids: Counter[str] = Counter()

    for path, item in (doc.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(op, dict):
                continue
            operations += 1
            by_method[method.upper()] += 1

            op_id = op.get("operationId")
            if isinstance(op_id, str) and op_id:
                operation_ids[op_id] += 1
            else:
                warnings.append(f"{method.upper()} {path}: 缺少 operationId")

            responses = op.get("responses")
            if not isinstance(responses, dict) or not responses:
                errors.append(f"{method.upper()} {path}: 没有 responses")
            elif not any(code.startswith("2") for code in responses):
                errors.append(f"{method.upper()} {path}: 没有 2xx response")

            declared = {
                p.get("name")
                for p in (op.get("parameters") or [])
                if isinstance(p, dict) and p.get("in") == "path"
            }
            placeholders = set(PLACEHOLDER.findall(path))
            for missing in sorted(placeholders - declared):
                errors.append(f"{method.upper()} {path}: 路径占位符 {{{missing}}} 缺少 path 参数")
            for extra in sorted(declared - placeholders):
                errors.append(f"{method.upper()} {path}: path 参数 {extra!r} 不在路径模板里")

    for op_id, count in operation_ids.items():
        if count > 1:
            errors.append(f"operationId 重复 {count} 次: {op_id}")

    # --- schemas -------------------------------------------------------------
    with_props = sum(1 for s in schemas.values() if isinstance(s, dict) and s.get("properties"))
    for name in sorted(set(schemas) - referenced):
        warnings.append(f"模型未被引用: {name}")

    # --- report --------------------------------------------------------------
    print(f"openapi   : {doc.get('openapi', '?')}")
    info = doc.get("info") or {}
    print(f"title     : {info.get('title', '?')}  (version {info.get('version', '?')})")
    print(f"servers   : {', '.join(servers) if servers else '(无)'}")

    print(f"paths     : {len(doc.get('paths') or {})}")
    methods = ", ".join(f"{m} {n}" for m, n in sorted(by_method.items())) or "无"
    print(f"operations: {operations}  ({methods})")
    print(f"schemas   : {len(schemas)}  (含字段的 {with_props})")

    for warning in warnings:
        print(f"[warn] {warning}")
    for error in errors:
        print(f"[error] {error}")

    if errors:
        print(f"\n检查未通过: {len(errors)} 个错误, {len(warnings)} 个警告")
        return 1
    print(f"\n检查通过: 0 个错误, {len(warnings)} 个警告")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
