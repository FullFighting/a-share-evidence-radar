# GitHub 发布与增长清单

目标不是短期刷 Star，而是让第一次访问的人在一分钟内确认：问题真实、方案不同、可以运行、值得持续关注。

## 仓库元数据

- 建议仓库名：`a-share-evidence-radar`
- 建议描述：`Evidence-first A-share event radar for Codex — cluster disclosures, news and market reactions into low-noise alerts.`
- 建议 Topics：`a-share`、`china-stock`、`event-monitoring`、`stock-alerts`、`rss`、`python`、`codex`、`agent-skills`、`webhook`、`fintech`
- 将 `docs/assets/hero.svg` 导出为 1280×640 PNG，并在 Settings → Social preview 上传。GitHub 推荐至少 640×320，1280×640 显示最佳。
- 开启 Issues、Discussions 和 Private vulnerability reporting。

参考：[GitHub 社交预览说明](https://docs.github.com/en/enterprise-cloud@latest/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview)。

## 首次发布

1. 确认四组 CI（Windows/Linux × Python 3.10/3.12）全部通过。
2. 创建 `v0.2.0` Release，说明四道质量门、Feed 采集、公开评测和安全推送。
3. 在 Release 中放一段可复制的 30 秒演示命令和真实终端输出。
4. 创建 3—5 个边界清晰的 `good first issue`，每个都附输入、预期输出和验收命令。
5. 置顶一个 Discussion：征集匿名化误报、漏报和错误聚类案例。

## 发布文案

中文：

> 我做了一个 A 股证据链事件雷达：它不会抓到标题就转发，而是先合并公告、新闻和行情反应，再经过证据、相关性、冲突、时效四道门。Python 零依赖，支持 Codex Skill/插件、6 类推送渠道和公开回归评测。最需要的贡献不是更多爬虫，而是匿名化误报与漏报案例。

English:

> I built an evidence-first A-share event radar for Codex. It clusters disclosures, news, and observed market reactions, then applies evidence, relevance, contradiction, and freshness gates before an alert is eligible. Standard-library Python, six delivery channels, and a public behavioral benchmark. The most valuable contributions are anonymized failures—not more headline scrapers.

## 持续增长

- 每次修复误报或漏报，都把匿名化案例加入公开 benchmark，并在 Release notes 中说明。
- 对外展示“新增了哪些失败案例”，不要宣传无法复现的准确率。
- 24—48 小时内回复高质量 Issue，给首次贡献者提供明确的测试命令。
- 每个版本只突出一个清晰主题，例如“转载不再冒充双重印证”。
- README 中的路线图必须与公开 Issue 和已发布版本保持一致。
- 记录真实 Star、Fork、Release 下载、贡献者和下游使用；申请赞助时只使用可验证数据。

GitHub 官方也建议项目提供清晰的功能、运行方式、演示、测试，并完善仓库描述与 Topics。参考：[用 GitHub 项目展示工作](https://docs.github.com/en/account-and-profile/tutorials/using-your-github-profile-to-enhance-your-resume)。
