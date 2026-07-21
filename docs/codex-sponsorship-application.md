# Codex 额度赞助申请草稿

更新日期：2026-07-21

## 推荐申请顺序

1. **Codex open source fund**：适合当前早期项目。官方说明该基金总额为 100 万美元，申请滚动审核，单个项目最高可获得 25,000 美元 API credits。
2. **Codex for Open Source**：等仓库形成持续维护记录、真实用户、Star、下载量或社区贡献后再申请。该项目更关注活跃开源项目、生态重要性和维护者责任。

不要在申请中虚构 Star、下载量、用户数、性能或合作关系。

## 当前可验证基础

以下内容已经在仓库中落地，可在申请中作为事实陈述：

- 标准 Codex 插件清单与独立 Skill 均通过官方结构校验；
- Python 3.10+ 标准库实现，无第三方运行时依赖；
- 21 个自动化测试覆盖 RSS/Atom/JSON Feed、Windows 路径、一键流程、转载指纹、旧闻重发、来源伪造、时效、聚类、冷却、完整脱敏和四道质量门；
- 8 个公开行为基准覆盖权威公告、独立印证、传闻、转载、冲突、无关消息、旧闻和未来时间；
- RSS、Atom、JSON Feed 采集器、离线 Doctor 和 6 类安全推送渠道；
- 中英文 README、贡献规范、安全策略、Issue 模板和 Windows/Linux CI 矩阵。

这些是工程完整度证据，不应被表述为真实市场准确率或用户采用数据。

## Codex open source fund 表单草稿

### Which open source project are you representing?

A-share Evidence Radar / A股证据链事件雷达

### Brief description of the project

A-share Evidence Radar is an open-source Codex Skill and plugin that turns fragmented public disclosures, regulator notices, financial news, and observed market reactions into low-noise evidence cards. Unlike headline-forwarding bots, it clusters one real-world event across sources, prevents syndicated copies from posing as independent confirmation, applies evidence/relevance/conflict gates, exposes score breakdowns, and previews notifications before any external send.

### GitHub repository

`https://github.com/<YOUR_GITHUB_USERNAME>/<YOUR_REPOSITORY>`

### How would you use API credits for your project?

We would use API credits for a 90-day open-source maintenance program: build and contract-test authorized disclosure/feed adapters; expand the public benchmark from 10 to at least 100 anonymized edge cases; classify duplicate, stale, and contradictory reports; triage parser failures; review community pull requests; and maintain bilingual evidence-card documentation. Credits would support public code, tests, and maintainer workflows—not trading, brokerage access, or automated investment decisions.

### Is there anything else you’d like us to know?

The project addresses a common failure mode in financial alerting: speed is prioritized over evidence, producing duplicate notifications and unsupported causal claims. The current repository already includes a standard-library runtime, preview-first delivery, 21 automated tests, and a ten-case public behavior benchmark. We will publish adapter contracts, anonymized failures, evaluation changes, and release notes so credits translate into inspectable open-source maintenance outputs.

## 获得额度后的 90 天公开交付

- 第 1—30 天：发布首个版本，建立适配器契约，新增至少 3 个合规来源适配器和对应回归夹具。
- 第 31—60 天：将匿名化公开评测集扩展到至少 50 个案例，发布误报/漏报分类与基线结果。
- 第 61—90 天：扩展到至少 100 个案例，完成贡献者适配器指南、版本迁移说明和一次安全审查。

每项交付都以公开 Commit、Issue、PR、Release 或 benchmark 变化为证据；如果没有达到目标，应在仓库中说明原因，而不是在后续申请中美化数字。

## Codex for Open Source 精简字段

该项目当前是早期版本。只有积累真实采用证据后，才使用下面的申请稿。

### Describe your role

Primary maintainer. I designed the evidence-gating workflow, maintain the Codex Skill and deterministic fusion tools, review source adapters, and own releases, issue triage, security boundaries, and contributor guidance.

### Why does this repository qualify?（500字符以内英文草稿）

This project provides reusable, evidence-first infrastructure for financial event adapters, cross-source clustering, provenance, contradiction handling, and preview-first alerts. The public repo includes 21 tests and a ten-case behavioral benchmark. Before applying, append only verified adoption signals: stars, users, contributors, releases, integrations, or dependents.

### How will you use API credits?（500字符以内英文草稿）

We will use credits for Codex-assisted adapter maintenance, issue triage, PR review, regression generation, releases, and expansion of a public benchmark for duplicate, stale, unrelated, or contradictory events. Outputs will be public code, cases, and docs. No credits will support trading, brokerage access, or personalized investment instructions.

### Anything else we should know?（500字符以内英文草稿）

The project is intentionally safe by construction: standard-library runtime, no brokerage integration, preview-only delivery by default, redacted endpoints, and separate treatment of facts versus observed market reaction. Funding would be reported through public milestones and benchmark changes. We will not claim real-world accuracy or adoption without reproducible evidence.

## 提交前清单

- [ ] 仓库已经公开并填写真实 URL。
- [ ] GitHub 个人主页公开，能看出你是 primary/core maintainer。
- [ ] README 有清晰问题定义、演示、运行方式、安全边界和许可证。
- [ ] CI 通过，至少发布一个带说明的版本。
- [ ] Issues、Roadmap 或 Discussions 展示真实维护计划。
- [ ] 用真实数据替换所有 `<PLACEHOLDER>`，但不提交个人邮箱、组织 ID 或 API 密钥到仓库。
- [ ] 申请 Codex for Open Source 时准备 OpenAI Organization ID。
- [ ] 记录真实 Star、Fork、下载量、用户反馈或下游采用证据。

## 官方入口

- Codex open source fund: https://openai.com/form/codex-open-source-fund/
- Codex for Open Source: https://openai.com/form/codex-for-oss/
