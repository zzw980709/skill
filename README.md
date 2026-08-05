# Skills

个人 Claude Code Skills 仓库,存放自己编写/使用的 skills。

每个 skill 是一个独立目录,包含 `SKILL.md`(技能说明与触发条件)以及所需的脚本、参考资料。安装时把对应 skill 目录链接或复制到 `~/.claude/skills/` 即可。

## 已有 Skills

| Skill | 目录 | 说明 |
| ----- | ---- | ---- |
| visual-eyes | `visual-eyes/` | 给没有视觉能力的模型装"眼睛":通过本地 Ollama + MiniCPM-V 视觉模型识别图片/截图/扫描件,返回文字或结构化结果(支持 OCR、多图对比、图像问答)。中英双语 OCR 准确,全程本地运行,无需 API Key。 |
| scaffold | `scaffold/` | 从需求产出符合当前仓库分层与规范、可直接合入主干的代码。技术栈不固定:先识别工作目录的技术栈与代码约定(构建清单 + 源码布局 → 约定快照),选对应内置模板集(`templates/<stack>/`,覆盖 Java/Spring Boot DDD、Node/TS Express、Python FastAPI、Go Gin)当骨架,再按"可行性分析 → 计划 → 任务清单 → 用户确认 → 生成 → 复审"的闸门式流程产出镜像仓库真实写法的代码,始终以活代码校准。 |
