# 视觉模型配置参考（references/providers.md）

`visual-eyes` 的唯一后端是 **本地 Ollama + moondream**，数据全程不出本机，无需任何 API Key。

---

## 模型说明：为什么是 moondream

[moondream](https://huggingface.co/vikhyatk/moondream2) 是 moondream2 在 Ollama 中的量化版，
一个 **2B 参数的小型视觉语言模型（VLM）**，专为"在所有地方高效运行"设计，支持
Apple Silicon (MPS)、图像描述（caption）/ 视觉问答（VQA）/ 目标检测（detect）。
这正是本 skill 需要的"输入图 → 输出文字"能力，而非图像/视频生成。

**已知局限（2B 量化的固有短板）：**
- 默认倾向用英文回复（即使提示用中文）；OCR 对复杂版面会"描述"而非逐字转录。
- 偶发返回空内容或触发 Ollama 5xx——`see.py` 已自动重试一次并给出明确错误。
- 对某些复杂/文字密集图像可能理解不完整，可换更强模型（见下）。

---

## 安装与首次运行（macOS）

```bash
brew install ollama                       # 或官网下载 https://ollama.com/download 安装包
ollama serve                              # 启动本地服务（默认监听 :11434）
ollama pull moondream:1.8b                # 拉取视觉模型（约 1.7 GB，首次需联网）
ollama list                               # 确认 moondream:1.8b 已就绪
```

> 若只 `ollama pull moondream`（得到 `moondream:latest`），`see.py` 默认请求
> `moondream:1.8b` 时会自动回退到同 base 的已装模型并打印提示，无需手动处理。

---

## 调用

默认即本地 Ollama，**无需任何 API Key / 环境变量**：

```bash
python scripts/see.py --image photo.jpg --prompt "图里有什么？"
```

### 给视觉模型的提示词技巧

moondream 对"具体指令"的响应明显好于泛泛而谈，建议：
- **描述**：`"用中文描述这张图的整体场景、主体和主要动作"`（比 `"这是什么"` 更稳定）。
- **OCR**：**提问式 prompt 比命令式更稳定**——用
  `"What text and numbers are visible in this image? List them."`
  （或中文 `"图中可见哪些文字和数字？请列出。"`）。
  可加 `--options '{"temperature":0.1}'`（低温更稳定、少重复；0 有时会反复输出同一句，建议 0.1）。
  注意：moondream 对"逐字转录"类命令（如 `"Extract all text exactly as written"`）偶尔会
  直接返回**空内容**；若遇到空输出，把 prompt 改成提问式再试，通常即恢复。
- **目标检测**：`"Detect all people/objects with bounding boxes"`（moondream 支持 detect）。
- **问答**：问题越具体越好，如 `"图里的红车车牌号是什么？"`。

### 切换 Ollama 里的其它视觉模型

Ollama 生态还有多款视觉模型，直接换 `--model` 即可（如需更强效果可换体积更大的）：

```bash
ollama pull llava                  # ~4.7GB，经典多模态
ollama pull minicpm-v              # 2B，OCR 稍好
ollama pull qwen2.5vl:3b           # 3B，中英 OCR 与图表理解较好
ollama pull llama3.2-vision:11b    # 11B，效果更强但更吃内存
python scripts/see.py --image x.jpg --prompt "描述" --model minicpm-v
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
