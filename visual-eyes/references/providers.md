# 视觉模型配置参考（references/providers.md）

`visual-eyes` 的唯一后端是 **本地 Ollama + MiniCPM-V**，数据全程不出本机，无需任何 API Key。

---

## 模型说明：为什么是 MiniCPM-V

[MiniCPM-V](https://github.com/OpenBMB/MiniCPM-V) 是面壁智能（OpenBMB）开源的视觉语言模型（VLM），
基于 Qwen3.5 架构 + CLIP 视觉投影，支持 **图像理解 / 中英双语 OCR / 视觉问答 / 图表与 UI 理解**，
Q4 量化后约 1.6GB，能在 Apple Silicon 上流畅运行。这正是本 skill 需要的"输入图 → 输出文字"
能力，而非图像/视频生成。

**相比 2B 量化的 moondream，MiniCPM-V 的优势：**
- 中英文 OCR 准确：中文逐字转录基本无误，含全角标点、`¥` 等符号。
- 视觉问答 / 数学 / 形状识别更可靠，能理解 UI 界面与图表。
- 支持思考（thinking）模式与长上下文（256K）。

**已知局限：**
- 默认倾向用英文回复（即便用中文提问）——主模型应把结果翻译成用户语言。
- 偶发返回空内容或触发 Ollama 5xx——`see.py` 已自动重试一次并给出明确错误。

---

## 安装与首次运行（macOS）

```bash
brew install ollama                       # 或官网下载 https://ollama.com/download 安装包
ollama serve                              # 启动本地服务（默认监听 :11434）
ollama pull openbmb/minicpm-v4.6          # 拉取视觉模型（约 1.6 GB，首次需联网）
ollama list                               # 确认 openbmb/minicpm-v4.6 已就绪
```

> 若默认模型未安装，`see.py` 会自动回退到同 base 的已装模型（如其它 openbmb 模型）并打印提示。

---

## 调用

默认即本地 Ollama，**无需任何 API Key / 环境变量**：

```bash
python scripts/see.py --image photo.jpg --prompt "图里有什么？"
```

### 给视觉模型的提示词技巧

提示词建议（MiniCPM-V 对"具体指令"的响应明显好于泛泛而谈）：
- **描述**：`"用中文描述这张图的整体场景、主体和主要动作"`（比 `"这是什么"` 更稳定）。
- **OCR**：直接让模型转录即可（中英均可）；用中文提问通常得到中文回复，逐字转录准确。
  可加 `--options '{"temperature":0.1}'`（低温更稳定、少重复；0 有时会反复输出同一句，建议 0.1）。
  若个别时候空输出，把 prompt 改成提问式（如 `"图中可见哪些文字和数字？请列出。"`）通常即恢复。
- **问答**：问题越具体越好，如 `"图里的红车车牌号是什么？"`、`"这个登录界面上有哪些元素？"`。

### 切换 Ollama 里的其它视觉模型

Ollama 生态还有多款视觉模型，直接换 `--model` 即可（如需更轻量可换 moondream）：

```bash
ollama pull moondream:1.8b           # 2B，更轻量但 OCR/理解较弱
ollama pull llava                    # ~4.7GB，经典多模态
ollama pull qwen2.5vl:3b             # 3B，中英 OCR 与图表理解较好
ollama pull llama3.2-vision:11b      # 11B，效果更强但更吃内存
python scripts/see.py --image x.jpg --prompt "描述" --model moondream:1.8b
```

### 远程 / 容器部署的 Ollama

若 Ollama 跑在别的机器或容器里，用 `--endpoint`（或 `VISION_MODEL_ENDPOINT` 环境变量）覆盖：

```bash
python scripts/see.py --image x.jpg --prompt "描述" \
    --endpoint http://192.168.1.10:11434/api/chat
```

---

## 故障排查

- 报 `URLError` / 连不上：服务未启动或没装，见上方安装步骤（脚本也会打印指引）。
- 报"模型 xxx 未安装"：脚本已列出本机模型，执行 `ollama pull <模型名>` 即可；
  非显式 `--model` 时会自动回退到同 base 的已装模型。
- 报 `HTTP 5xx` / 空内容：Ollama 模型进程偶发异常，先 `ollama stop <模型>` 再重试；
  仍不行就换一个视觉模型（见上），或把图像压缩/缩小。
- 超时：大图先压缩/缩放，或调大 `--timeout`（默认 180s）。
