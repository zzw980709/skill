# Skills

个人 Claude Code Skills 仓库,存放自己编写/使用的 skills。

每个 skill 是一个独立目录,包含 `SKILL.md`(技能说明与触发条件)以及所需的脚本、参考资料。安装时把对应 skill 目录链接或复制到 `~/.claude/skills/` 即可。

## 已有 Skills

| Skill | 目录 | 说明 |
| ----- | ---- | ---- |
| visual-eyes | `visual-eyes/` | 给没有视觉能力的模型装"眼睛":通过本地 Ollama + MiniCPM-V 视觉模型识别图片/截图/扫描件,返回文字或结构化结果(支持 OCR、多图对比、图像问答)。中英双语 OCR 准确,全程本地运行,无需 API Key。 |
