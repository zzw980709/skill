# Skills

个人技能库，可用于 Codex、Claude Code 等支持 `SKILL.md` 的代理。
每个目录包含独立入口，以及按需读取的脚本、参考资料或模板。

| Skill | 适用任务 | 前置条件 |
| --- | --- | --- |
| [scaffold](scaffold/SKILL.md) | 按现有仓库结构新增模块、接口、实体或 CRUD 骨架 | 目标仓库代码与构建环境；内置 Java、Node/TS、Python、Go 模板 |
| [api-exporter](api-exporter/SKILL.md) | 查询或筛选 Spring Boot 端点，导出 OpenAPI JSON，按需同步 Apifox | Rust/Cargo 编译内置 CLI；同步时需要 Apifox 凭据 |
| [api-doc-html](api-doc-html/SKILL.md) | 生成带接入约定、页面流程、字段契约、Fetch / TypeScript 示例及 Agent 交接包的单文件对接手册 | Python 3；从源码生成时另需 api-exporter |
| [visual-eyes](visual-eyes/SKILL.md) | 主模型无法读图或指定 Ollama 时，进行 OCR、图片问答和对比 | Python 3.10+、Ollama 服务和视觉模型 |

## 安装

将需要的 skill 目录复制或链接到对应代理的技能目录，例如 `~/.codex/skills/` 或 `~/.claude/skills/`。
也可使用支持这些目录的代理所配置的其它技能路径。不要仅复制 `SKILL.md`，脚本、参考资料及模板需要保留。

两个 API skill 一起安装时保留同级目录，方便查找工具；分开安装可用 `--exporter` 或 `API_EXPORTER_BIN` 指定可执行文件。
命令中的 `<skill-dir>` 需换成实际安装目录；输出文件路径按任务指定，不依赖代理的当前工作目录恰好是技能目录。

## 使用边界

- 要 OpenAPI JSON、查端点或同步 Apifox：用 `api-exporter`。
- 要可读 HTML：用 `api-doc-html`；已有 JSON 时无需扫描源码。
- 要镜像仓库结构生成模块：用 `scaffold`，局部修复无需套用整套流程。
- 主模型能直接看图时，通常无需 `visual-eyes`。

纯文件导出使用 `api-exporter --dry-run`，避免环境中已有 Apifox 凭据时触发远程导入。
`visual-eyes --json` 返回 JSON 封装，正文 `text` 仍是视觉模型的原始回复。

## 验证

HTML 源码导出流程的离线回归测试（不连接 Apifox，不需要 Rust 编译产物）：

```bash
python3 -m unittest discover -s api-doc-html/tests -v
```

前端手册效果演示：[订单中心对接手册](api-doc-html/examples/frontend-guide.html)（虚构数据）。
