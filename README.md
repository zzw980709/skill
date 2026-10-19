# Skills

个人 Claude Code Skills 仓库,存放自己编写/使用的 skills。

每个 skill 是一个独立目录,包含 `SKILL.md`(技能说明与触发条件)以及所需的脚本、参考资料。安装时把对应 skill 目录链接或复制到 `~/.claude/skills/` 即可。

## 已有 Skills

| Skill | 目录 | 说明 |
| ----- | ---- | ---- |
| visual-eyes | `visual-eyes/` | 给没有视觉能力的模型装"眼睛":通过本地 Ollama + MiniCPM-V 视觉模型识别图片/截图/扫描件,返回文字或结构化结果(支持 OCR、多图对比、图像问答)。中英双语 OCR 准确,全程本地运行,无需 API Key。 |
| scaffold | `scaffold/` | 从需求产出符合当前仓库分层与规范、可直接合入主干的代码。技术栈不固定:先识别工作目录的技术栈与代码约定(构建清单 + 源码布局 → 约定快照),选对应内置模板集(`templates/<stack>/`,覆盖 Java/Spring Boot DDD、Node/TS Express、Python FastAPI、Go Gin)当骨架,再按"可行性分析 → 计划 → 任务清单 → 用户确认 → 生成 → 复审"的闸门式流程产出镜像仓库真实写法的代码,始终以活代码校准。 |
| api-exporter | `api-exporter/` | 静态扫描 Spring Boot 源码生成 OpenAPI 3.0 并导入 Apifox(tree-sitter 解析,无需启动服务、无需 classpath)。**skill 内置工具源码**(`tool/`,Rust),首次使用 `cargo build --release` 编译一次即可,不依赖外部工程。支持只导出**指定接口**:按路径(精确/glob)、控制器、`@Api` 分组、HTTP 方法、Java 方法名筛选,或用清单文件批量指定,`--list` 可先预览全部接口;被筛掉的接口不再解析、未被引用的数据模型自动剔除,产物可直接导入 Apifox 或任意 OpenAPI 工具。附 `scripts/check_document.py` 校验脚本(悬空引用/operationId 重复/缺少 2xx/path 参数不符)。 |
