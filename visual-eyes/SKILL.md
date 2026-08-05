---
name: visual-eyes
description: 为没有视觉能力的模型提供"眼睛"。当任务涉及图片、截图、扫描件、图表、照片、视频帧、UI 界面等需要视觉理解的内容（描述场景、识别物体、OCR 提取文字、回答图像问题、多图对比）时，调用本 skill 把图像交给本地 Ollama + moondream 视觉模型，并将文字或结构化结果返回给主模型继续推理。Use this skill whenever the active model lacks vision but the task needs to read or understand an image — even if the user only says "看下这张图" / "what's in this image" / "read the text in this screenshot".
compatibility: Python 3.8+；本地 Ollama 服务（默认 http://localhost:11434）与任一视觉模型（默认 moondream:1.8b）；脚本仅用 Python 标准库，无需 API Key。
---

# Visual Eyes（视觉之眼）

给"没有视觉能力的模型"装一双眼睛。当主模型遇到需要"看"的内容时，
本 skill 充当翻译层：把图像交给本地 **moondream** 视觉模型去看，再把
文字结果交还给主模型，让它继续推理。

数据全程在本地运行（Ollama），无需任何 API Key，也不会外发。

## When to use

在以下情况触发本 skill（只要主模型自身无法直接读图）：
- 用户发来图片、截图、扫描件、照片、图表、UI 界面、代码报错截图等
- 需要描述画面内容、识别其中的物体/文字（OCR）、回答"图里有什么"类问题
- 多图对比、按图检索、从图中提取结构化信息

不触发：主模型自身已具备视觉能力，或任务纯文本无需看图。

## 配置视觉模型（默认：本地 Ollama + moondream）

本 skill 默认使用**本地 Ollama 运行 moondream**（moondream2 的本地量化版，
2B 参数的小型视觉语言模型，能在 Apple Silicon 上跑，专门用于"看图理解"），
开箱即用，只需在本机准备好 Ollama 与模型：

```bash
# 1) 安装并启动 Ollama（macOS）
brew install ollama          # 或官网下载 https://ollama.com/download
ollama serve                 # 默认监听 http://localhost:11434
# 2) 拉取视觉模型（首次需联网，约 1.x GB）
ollama pull moondream:1.8b
# 3) 验证
ollama list
```

之后调用 `scripts/see.py` 即可，**无需任何 API Key 或环境变量**。

配置优先级：`--model` > `VISION_MODEL_NAME` 环境变量 > 内置默认（moondream:1.8b）；
`--endpoint` > `VISION_MODEL_ENDPOINT` 环境变量 > 内置默认（localhost:11434）。

> 注意：脚本默认请求 `moondream:1.8b`。若你只 `ollama pull moondream`
> （得到的是 `moondream:latest`），脚本会自动回退到同 base 的已装模型并给出提示；
> 详见下方"模型未安装"一节。

## 使用方法

运行 `scripts/see.py`，传入图像与指令。**默认走本地 Ollama + moondream**：

```bash
# 自然语言描述（默认）——把"看到的内容"当作主模型的眼睛
python scripts/see.py --image <路径|URL|data:URI|base64> \
    --prompt "用中文描述这张图里有什么"

# 结构化输出（OCR / 对象列表 / 场景分析）——返回可解析的 JSON
# 注：OCR 用"提问式"prompt 比"命令式"更稳定；moondream 对逐字转录偶尔返回空内容
python scripts/see.py --image scan.png --prompt "图中可见哪些文字和数字？请列出。" --json

# OCR 类任务建议低温采样（更稳定、少重复）
python scripts/see.py --image scan.png --prompt "图中可见哪些文字和数字？请列出。" \
    --options '{"temperature":0.1}'

# 多图对比
python scripts/see.py --image a.png --image b.png --prompt "两者区别？"

# 换成 Ollama 里的其它视觉模型（如 llava / minicpm-v / qwen2.5vl）
python scripts/see.py --image x.jpg --prompt "描述" --model llava

# 远程 / 容器里的 Ollama
python scripts/see.py --image x.jpg --prompt "描述" \
    --endpoint http://192.168.1.10:11434/api/chat

# 大图/慢速时调大超时（默认 180s）
python scripts/see.py --image big.png --prompt "描述" --timeout 300
```

- 图像来源支持：本地路径、http(s) URL、data:URI、纯 base64（或 `--stdin-base64` 从管道读）。
- `--json` 返回 `{"model", "text", "caption", "image_count", "elapsed_s", "temperature", "num_predict"}`：
  `text` 是主字段（视觉模型的回复）；`caption`/`raw` 为兼容旧版的别名；
  `temperature`/`num_predict` 是本次实际发送的采样参数（未设则为 `null`）。
- `--options` 可透传任意 Ollama 采样参数（如 `temperature`、`top_p`、`num_predict`）。

## 主模型协作约定

1. 收到图像相关任务时，先判断是否需要"看"——是则加载本 skill。
2. 调用 `see.py` 拿到文字结果，将其视为"模型观察到的客观事实"。
3. 需要精确/可解析数据（如 OCR 全文、物体清单）时加 `--json`；
   只需整体理解时用默认自然语言输出。
4. moondream 默认倾向用英文回复：把视觉结果融入自己的回答时，
   请以**用户所用的语言**向用户呈现，必要时代为翻译。
5. 把视觉结果融入自己的推理与回答，并对用户说明"已通过本地视觉模型识别"。

## 模型未安装 / 调用失败

- **模型未安装**：脚本会列出本机已装模型并给出 `ollama pull <模型>` 命令（退出码 4）。
  若模型来自默认值或环境变量（非显式 `--model`），脚本会先自动回退到同 base 的已装模型。
- **连不上 Ollama**：脚本会打印安装指引（退出码 4）。
- **空内容 / HTTP 5xx**：moondream 偶发返回空内容或服务端 5xx。
  脚本会自动重试一次；仍失败会给出明确错误与建议（退出码 4）。
  若是 OCR 类指令返回空内容，多半是该命令式 prompt 触发了模型怪癖——
  改用提问式（如"图中可见哪些文字和数字？"）通常即可恢复。
- **参数/输入错误**：如未提供图像或 prompt、base64 无效（退出码 2）。

## 注意事项

- **隐私**：图像在本地 Ollama 处理，不会外发；但仍需遵守本地合规要求。
- **大图**：base64 超过 4MB 会告警、超过 16MB 直接拒绝。超大图像建议先压缩/缩放，
  避免超出模型上下文与超时（可用 `--timeout` 调大超时）。
- **稳定性**：脚本仅用标准库，不依赖第三方包；调用失败会输出明确错误与退出码
  （2=参数/输入错误，4=调用失败/未连上 Ollama/模型未安装/空内容）。

## Resources

### scripts/see.py
核心脚本：读取图像与指令，调用本地 Ollama + moondream，返回文字或 JSON。

### references/providers.md
moondream 模型说明、Ollama 安装 / 拉模型 / 调用 / 换模型 / 排错的完整指引。
