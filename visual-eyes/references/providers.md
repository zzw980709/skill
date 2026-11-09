# Ollama 配置与排错

脚本通过 Ollama `/api/chat` 调用视觉模型；默认模型名以 `see.py` 的配置为准。
模型的可用 tag、下载大小、硬件需求与识别质量因版本和量化而异，不在此固定承诺。

## 安装与首次运行

仅在需要安装或准备模型时执行；拉取模型会联网并占用磁盘。

```bash
# macOS 安装示例；已安装时跳过
brew install ollama
# 已有服务时不重复启动
ollama serve
# 另一个终端中准备默认模型；也可使用已安装的视觉模型
ollama pull openbmb/minicpm-v4.6
ollama list
```

若默认模型不可用，使用 `ollama list` 中适合图片任务的模型，通过 `--model` 明确指定。
自动回退只匹配冒号前的完整模型名，例如 `openbmb/minicpm-v4.6:latest` 可回退到
`openbmb/minicpm-v4.6:other-tag`，不会回退到同组织下的其它模型。

## 自定义端点与模型

```bash
python3 <skill-dir>/scripts/see.py --image x.jpg --prompt "用中文描述画面" \
  --model <installed-vision-model> \
  --endpoint http://192.168.1.10:11434/api/chat
```

环境变量：`VISION_MODEL_NAME`、`VISION_MODEL_ENDPOINT`，优先级低于命令行。
远程端点会收到图像内容；默认本机端点不需要 API Key，脚本未实现鉴权参数。

## 提示词与排错

- OCR：明确语言、阅读顺序与无法辨认时的标记。可用 `--options '{"temperature":0.1}'` 降低采样随机性，不保证准确率。
- 多图比较：说明图片顺序和需要比较的方面，避免只问“有什么区别”。
- 连不上服务：检查指定端点及服务状态；容器内的 localhost 指容器自身。
- 模型未安装：按错误中列出的模型名核对，必要时准备模型后重试。
- HTTP 5xx 或空回复：脚本有有限重试。仍失败时检查服务日志、内存或模型兼容性，避免重复发送同一请求。
- 超时：默认每次 180 秒；先考虑缩放大图，再按需增加 `--timeout`。重试会增加总耗时。

`--json` 只控制脚本结果封装格式。要提取业务字段，仍需约束 prompt 并校验返回的 `text`。
