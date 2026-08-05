# 模板集

按技术栈拆分的生成骨架。第 0 步识别出技术栈后，选对应的模板集作为起点；每个模板集自带 `README.md`，说明占位符与校准清单。
**所有模板都只是起点，生成前必须读活代码校准**（见 `SKILL.md` 的【生成规范】）。

| 模板集 | 技术栈 | 说明 |
|---|---|---|
| `java-springboot-ddd/` | Java + Spring Boot + JPA | 项目版 DDD 四层（interfaces/application/domain/infrastructure）+ DDL，源自 altamira 项目写法沉淀 |
| `node-ts-express/` | Node.js + TypeScript + Express + Prisma | router / service / repository / dto + migration |
| `python-fastapi/` | Python + FastAPI + SQLAlchemy | router / service / repository / schemas / model + migration |
| `go-gin/` | Go + Gin + sqlx | handler / service / repository / model / dto |

想增加其它技术栈（NestJS、Laravel、Rails、Spring WebFlux、actix-web…），照某个模板集的结构复制一份即可：
`README.md`（占位符 + 校准清单）+ 每层一个带 `{{占位符}}` 与 `TODO(需求)` 标记的骨架文件。
