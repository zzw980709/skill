#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
visual-eyes · see.py
====================
给"没有视觉能力的模型"装一双眼睛。

后端 = 本地 Ollama + MiniCPM-V（面壁智能 OpenBMB 的视觉语言模型，
支持图像理解 / 中英双语 OCR / 视觉问答，Q4 量化后能在 Apple Silicon 上跑，
专门用于"看图理解"，而非图像/视频生成）。

当你（主模型）遇到需要"看"的图像时，调用本脚本把它交给本地
MiniCPM-V 去理解，再把文字结果拿回来继续推理。

数据全程不出本机，无需任何 API Key。脚本仅用 Python 标准库。

用法：
  # 首次需拉取模型
  ollama pull openbmb/minicpm-v4.6

  # 自然语言描述（默认）——把"看到的内容"当作主模型的眼睛
  python see.py --image photo.jpg --prompt "图里有什么？"

  # 多图对比
  python see.py --image a.png --image b.png --prompt "两者有什么区别？"

  # 结构化输出（OCR / 对象列表 / 场景分析）
  python see.py --image scan.png --prompt "提取图中全部文字" --json

  # OCR 类任务建议低温（更稳定、少重复）
  python see.py --image scan.png --prompt "提取图中全部文字" --options '{"temperature":0.1}'

  # 换成 Ollama 里的其它视觉模型（如 moondream / llava / qwen2.5vl）
  python see.py --image x.jpg --prompt "描述" --model moondream:1.8b

  # 远程 / 容器里的 Ollama
  python see.py --image x.jpg --prompt "描述" \
      --endpoint http://192.168.1.10:11434/api/chat

  # 列出当前配置
  python see.py --list-config

  # 图片来自 URL 或 base64 / data:URI
  python see.py --image https://example.com/x.jpg --prompt "描述这张图"
  python see.py --image "data:image/png;base64,...." --prompt "这是什么"
  cat img.b64 | python see.py --prompt "描述" --stdin-base64

退出码：2 = 参数/输入错误；4 = 调用失败 / 未连上 Ollama / 模型未安装。
"""
import argparse
import base64
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request


# ===================== 默认配置 =====================
# 本地 Ollama 服务（MiniCPM-V 是面壁智能 OpenBMB 的视觉语言模型，
# 支持图像理解 / 中英 OCR / 视觉问答，Q4 量化后可在 Apple Silicon 上跑）。
# Ollama 本地服务默认不鉴权。
_OLLAMA_ENDPOINT = "http://localhost:11434/api/chat"
_OLLAMA_MODEL = "openbmb/minicpm-v4.6:latest"
_DEFAULT_TIMEOUT = 180
# 大图防护：base64 超过该阈值只告警；超过硬上限直接拒绝（必然超时/超上下文）
_WARN_B64_BYTES = 4 * 1024 * 1024
_ABORT_B64_BYTES = 16 * 1024 * 1024
# ===================================================

# 文件头识别失败时，按扩展名回退的 MIME 表
_EXT_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


class ModelNotFoundError(Exception):
    """请求的模型在 Ollama 里不存在（HTTP 404 + 'not found'）。"""

    def __init__(self, model: str, detail: str = ""):
        self.model = model
        self.detail = detail
        super().__init__(f"模型 {model} 未找到")


def print_error(msg: str, is_json: bool):
    """统一错误输出：--json 时输出 JSON 到 stderr，否则纯文本。"""
    print(json.dumps({"error": msg}, ensure_ascii=False) if is_json else msg, file=sys.stderr)


def detect_mime(raw: bytes, name: str = "") -> str:
    """根据文件头猜测 MIME；识别失败时回退到扩展名。"""
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw[:2] == b"BM":
        return "image/bmp"
    if raw[:2] in (b"II", b"MM"):
        return "image/tiff"
    ext = os.path.splitext(name)[1].lower()
    return _EXT_MIME.get(ext, "image/png")


def load_image(src: str):
    """返回 (b64, mime)。支持 path / http(s) URL / data:URI / 纯 base64。

    输入无效时抛 ValueError，错误信息带可执行提示。
    """
    src = src.strip()
    if not src:
        raise ValueError("图像来源为空")
    if src.startswith("data:"):
        meta, _, b64 = src.partition(",")
        if not meta.startswith("data:image/"):
            raise ValueError(f"data:URI 的 MIME 前缀不是图片：{meta[:40]}…")
        b64 = re.sub(r"\s+", "", b64)
        if not _valid_b64(b64):
            raise ValueError("data:URI 内的 base64 无效")
        mime = meta[5:].split(";")[0] or "image/png"
        return b64, mime
    if src.startswith("http://") or src.startswith("https://"):
        req = urllib.request.Request(src, headers={"User-Agent": "visual-eyes"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
        except Exception as e:
            raise ValueError(f"下载图像失败（{src[:80]}…）：{e}")
        return base64.b64encode(raw).decode(), detect_mime(raw, src)
    if os.path.isfile(src):
        with open(src, "rb") as f:
            raw = f.read()
        return base64.b64encode(raw).decode(), detect_mime(raw, src)
    # 当作纯 base64
    b64 = re.sub(r"\s+", "", src)
    if not _valid_b64(b64):
        raise ValueError(
            f"无法识别图像来源：'{src[:60]}…' 既不是存在的文件/URL，也不是合法的 base64"
        )
    return b64, detect_mime(base64.b64decode(b64))


def _valid_b64(b64: str) -> bool:
    """严格校验 base64 字符串（拒绝空串与非 base64 字符）。"""
    if not b64:
        return False
    try:
        base64.b64decode(b64, validate=True)
        return True
    except Exception:
        return False


def check_image_size(images, is_json: bool):
    """大图防护：超阈值告警；超硬上限终止。返回 True 表示应终止。"""
    for i, (b64, _mime) in enumerate(images, 1):
        n = len(b64)
        if n > _ABORT_B64_BYTES:
            print_error(
                f"图像 {i} 的 base64 超过 {_ABORT_B64_BYTES // (1024 * 1024)}MB，"
                "几乎必然超时或超出模型上下文。请先压缩/缩放后再试。", is_json)
            return True
        if n > _WARN_B64_BYTES:
            sys.stderr.write(
                f"[visual-eyes] 警告：图像 {i} 较大（base64 {n // 1024}KB），"
                "若超时可先压缩，或用 --timeout 调大超时。\n")
    return False


def build_ollama_messages(images, prompt: str, system: str):
    """构造 Ollama /api/chat 的 messages（images 为 base64 字符串数组）。"""
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({
        "role": "user",
        "content": prompt,
        "images": [b64 for b64, _ in images],
    })
    return msgs


def api_tags_url(endpoint: str) -> str:
    """从给定的 /api/chat 端点推导 /api/tags 端点，推不出则回退本地默认。"""
    base = endpoint.rstrip("/")
    for suffix in ("/api/chat", "/api/generate"):
        if base.endswith(suffix):
            return base[: -len(suffix)] + "/api/tags"
    if base.endswith("/api/tags"):
        return base
    return "http://localhost:11434/api/tags"


def list_ollama_models(tags_url: str):
    """返回本地可用的模型名列表；查询失败返回 []。"""
    try:
        req = urllib.request.Request(tags_url, headers={"User-Agent": "visual-eyes"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return []


def pick_fallback_model(requested: str, available) -> str | None:
    """在已安装模型中挑选回退项：同 base 优先 <base>:latest，其次同 base 其它。"""
    base = requested.split(":")[0]
    same_base = sorted(m for m in available if m.split(":")[0] == base)
    if not same_base:
        return None
    if f"{base}:latest" in same_base:
        return f"{base}:latest"
    return same_base[0]


def request_chat(endpoint: str, payload: dict, timeout: float):
    """POST /api/chat，返回响应 dict；模型缺失时抛 ModelNotFoundError。"""
    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")
        if e.code == 404 and "not found" in body.lower():
            raise ModelNotFoundError(payload["model"], body)
        raise


def _request_with_retry(endpoint, payload_builder, model, timeout):
    """POST 一次；Ollama 服务端 5xx（模型进程偶发崩溃）时稍候重试一次。"""
    try:
        return request_chat(endpoint, payload_builder(model), timeout)
    except urllib.error.HTTPError as e:
        if e.code >= 500:
            # 5xx 通常是 Ollama runner 崩溃，下次请求会自动重载模型
            sys.stderr.write(f"[visual-eyes] Ollama 服务端返回 HTTP {e.code}，稍候重试一次…\n")
            time.sleep(2)
            return request_chat(endpoint, payload_builder(model), timeout)
        raise


def _attempt(endpoint, model, payload_builder, timeout):
    """单次模型调用：空内容自动重试一次。返回 (text, model)。"""
    resp = _request_with_retry(endpoint, payload_builder, model, timeout)
    text = resp["message"]["content"]
    if not text.strip():
        # 视觉模型偶发返回空内容（模型/图像怪癖），重试一次
        sys.stderr.write("[visual-eyes] 模型返回空内容，重试一次…\n")
        resp = _request_with_retry(endpoint, payload_builder, model, timeout)
        text = resp["message"]["content"]
    return text, model


def run_chat(endpoint, requested_model, payload_builder, timeout, allow_fallback):
    """调用；模型缺失且允许回退时自动换到已装模型。

    返回 (text, effective_model)。模型缺失且无法回退时抛 ModelNotFoundError。
    """
    try:
        return _attempt(endpoint, requested_model, payload_builder, timeout)
    except ModelNotFoundError:
        if not allow_fallback:
            raise
        fallback = pick_fallback_model(requested_model,
                                       list_ollama_models(api_tags_url(endpoint)))
        if not fallback:
            raise
        sys.stderr.write(
            f"[visual-eyes] 模型 {requested_model} 未安装，已自动回退到已安装的 {fallback}。\n"
            f"[visual-eyes] 若要使用 {requested_model}，请执行：ollama pull {requested_model}\n")
        return _attempt(endpoint, fallback, payload_builder, timeout)


def suggest_ollama():
    sys.stderr.write(
        "\n[visual-eyes] 未连接到本地 Ollama 服务。本 skill 默认使用本地 Ollama + MiniCPM-V。\n"
        "[visual-eyes] 安装并启动 Ollama 后重试：\n"
        "    1) 安装 Ollama（macOS）：\n"
        "       - 官网下载 https://ollama.com/download 安装包，或\n"
        "       - brew install ollama\n"
        "    2) 启动服务：打开 Ollama 应用，或执行 `ollama serve`（默认监听 :11434）\n"
        "    3) 拉取视觉模型：ollama pull openbmb/minicpm-v4.6\n"
        "    4) 验证：ollama list\n"
    )


def list_config():
    print("visual-eyes 当前配置（本地 Ollama + MiniCPM-V）：")
    print(f"  backend : 本地 Ollama（数据不出本机，无需 API Key）")
    print(f"  endpoint: {_OLLAMA_ENDPOINT}")
    print(f"  model   : {_OLLAMA_MODEL}  （MiniCPM-V 视觉语言模型，中英 OCR 强）")
    print(f"  timeout : {_DEFAULT_TIMEOUT}s（可用 --timeout 调）")
    print()
    print("图像来源：本地路径 / http(s) URL / data:URI / 纯 base64 / --stdin-base64")
    print("可选参数：--json / --options '{\"temperature\":0.1}' / --timeout <秒> / --model / --endpoint")
    print("首次使用前请先 `ollama pull openbmb/minicpm-v4.6`，并确认 `ollama serve` 正在运行。")


def main():
    ap = argparse.ArgumentParser(description="visual-eyes: 把图像交给本地 MiniCPM-V 去看")
    ap.add_argument("--image", action="append",
                    help="图像：本地路径 / URL / data:URI / 纯 base64；可多次传入多图")
    ap.add_argument("--prompt", help="给视觉模型的指令/问题")
    ap.add_argument("--model", help="Ollama 视觉模型名，默认 MiniCPM-V；可换 moondream/llava 等")
    ap.add_argument("--endpoint", help="Ollama /api/chat 地址，默认 localhost:11434")
    ap.add_argument("--json", action="store_true",
                    help="以结构化 JSON 输出（text / caption / image_count / elapsed_s 等）")
    ap.add_argument("--options", help="Ollama 采样参数 JSON，如 '{\"temperature\":0.1}'（OCR 建议低温）")
    ap.add_argument("--timeout", type=float, default=_DEFAULT_TIMEOUT,
                    help=f"单次调用超时秒数，默认 {_DEFAULT_TIMEOUT}")
    ap.add_argument("--system",
                    default="You are a helpful vision assistant. Answer the user's question about the image accurately, concisely, and in the same language the user used.")
    ap.add_argument("--stdin-base64", action="store_true",
                    help="从标准输入读取 base64 图像数据")
    ap.add_argument("--list-config", action="store_true",
                    help="列出当前配置并退出")
    args = ap.parse_args()

    if args.list_config:
        list_config()
        return

    # ---- 输入校验（错误码 2）----
    if not args.image and not args.stdin_base64:
        print_error("未提供图像：请用 --image 指定，或 --stdin-base64 从管道读取", args.json)
        sys.exit(2)
    if not args.prompt:
        print_error("未提供 --prompt（给视觉模型的指令）", args.json)
        sys.exit(2)

    images = []
    try:
        if args.stdin_base64:
            data = sys.stdin.read().strip()
            if data:
                images.append(load_image(data))
        for src in (args.image or []):
            images.append(load_image(src))
    except ValueError as e:
        print_error(str(e), args.json)
        sys.exit(2)
    if not images:
        print_error("未提供任何图像", args.json)
        sys.exit(2)

    options = {}
    if args.options:
        try:
            options = json.loads(args.options)
        except json.JSONDecodeError as e:
            print_error(f"--options 不是合法 JSON：{e}", args.json)
            sys.exit(2)
        if not isinstance(options, dict):
            print_error("--options 必须是 JSON 对象，如 '{\"temperature\":0.1}'", args.json)
            sys.exit(2)

    # ---- 配置优先级：命令行 > 环境变量 > 内置默认 ----
    endpoint = args.endpoint or os.environ.get("VISION_MODEL_ENDPOINT") or _OLLAMA_ENDPOINT
    requested_model = args.model or os.environ.get("VISION_MODEL_NAME") or _OLLAMA_MODEL
    # 仅当用户显式 --model 时才禁止自动回退；默认/环境变量指定可自动换到已装模型
    allow_fallback = args.model is None

    if check_image_size(images, args.json):
        sys.exit(4)

    messages = build_ollama_messages(images, args.prompt, args.system)

    def payload_builder(model: str) -> dict:
        payload = {"model": model, "messages": messages, "stream": False}
        if options:
            payload["options"] = options
        return payload

    t0 = time.perf_counter()
    try:
        text, effective_model = run_chat(endpoint, requested_model, payload_builder,
                                         args.timeout, allow_fallback)
    except ModelNotFoundError as e:
        available = list_ollama_models(api_tags_url(endpoint))
        lines = [f"视觉模型 {e.model} 未安装"]
        if available:
            lines.append("本机已安装：" + "、".join(available))
            lines.append(f"请执行：ollama pull {e.model}")
        else:
            lines.append("请先执行：ollama pull openbmb/minicpm-v4.6 并确认 `ollama serve` 正在运行")
        print_error("\n".join(lines), args.json)
        sys.exit(4)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")[:500]
        hint = ""
        if e.code >= 500:
            hint = "（Ollama 服务端错误，可能是模型进程异常，可 `ollama stop <模型>` 后重试）"
        print_error(f"视觉模型返回 HTTP {e.code}：{body}{hint}", args.json)
        sys.exit(4)
    except TimeoutError:
        print_error(
            f"请求超时（{args.timeout}s）：{endpoint}。可用 --timeout 调大，或先压缩图片。",
            args.json)
        sys.exit(4)
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            print_error(
                f"请求超时（{args.timeout}s）：{endpoint}。可用 --timeout 调大，或先压缩图片。",
                args.json)
        else:
            suggest_ollama()
            print_error(f"无法连接 Ollama 服务（{endpoint}）：{reason}", args.json)
        sys.exit(4)
    except Exception as e:
        print_error(f"视觉模型调用失败：{e}", args.json)
        sys.exit(4)

    if not text.strip():
        print_error(
            "视觉模型连续返回空内容（可能是模型量化问题或图像过复杂）。"
            "建议：重试、换 --model（如 moondream/llava），或把图像压缩后再试。",
            args.json)
        sys.exit(4)

    if args.json:
        out = {
            "model": effective_model,
            "text": text,
            "caption": text,   # 兼容旧版字段
            "raw": text,       # 兼容旧版字段
            "image_count": len(images),
            "elapsed_s": round(time.perf_counter() - t0, 2),
            "temperature": options.get("temperature") if options else None,
            "num_predict": options.get("num_predict") if options else None,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(text)


if __name__ == "__main__":
    main()
