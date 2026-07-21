# Early beta: five evidence-radar users wanted

A-share Evidence Radar is an early beta. The code and public benchmark are reproducible, but they are not evidence of production accuracy or broad adoption. This beta is looking for five people who already work with at least one of these workflows:

- maintaining Codex Skills or agent workflows;
- tracking A-share public disclosures or financial news for research;
- building RSS, Atom, JSON Feed, webhook, or event-normalization integrations.

## Fifteen-minute test

1. Run the offline config check:

   ```bash
   python skills/monitor-a-share-events/scripts/validate_config.py \
     --config skills/monitor-a-share-events/assets/examples/radar-config.json
   ```

2. Run the fictional offline demo and confirm that it produces one eligible card and one held card:

   ```bash
   python skills/monitor-a-share-events/scripts/run_radar.py \
     --config skills/monitor-a-share-events/assets/examples/radar-config.json
   ```

3. If you have an authorized public feed, copy the example config outside the repository, replace the feed location, and run the validator again. Keep delivery in preview mode.
4. Report the first point of confusion, an unexpected card, or a missing card through the repository's **Beta feedback** or **Anonymized failure case** Issue form.

Useful feedback includes the operating system, Python version, install method, time to first successful demo, expected result, actual result, and the smallest fictional or anonymized fixture that reproduces the problem.

## Privacy and safety

- Do not post private holdings, credentials, cookies, paid article text, or personal data.
- Replace real symbols and issuer names when they are not necessary to reproduce a rule failure.
- Keep webhook URLs, bot tokens, and chat IDs in environment variables.
- Do not use the beta for trading, brokerage access, or unattended external sends.
- Review every generated fixture before posting it publicly; automated redaction is not a guarantee.

## What success means

The first beta milestone is not a target Star count. It is:

- five completed test reports from people other than the maintainer;
- at least three reproducible friction or failure cases;
- a documented median time to the first successful offline card;
- every accepted behavior change represented by a public benchmark case and unit test.

## 中文邀请

这个项目正在寻找首批 5 位真实试用者：Codex Skill 使用者、A 股公开信息研究者，或 RSS/事件数据集成开发者均可。测试只需约 15 分钟，默认离线、默认不发送。请不要公开真实持仓、密钥、Cookie 或付费内容；最有价值的反馈是首次运行卡在哪里、哪张事件卡不符合预期，以及可以匿名复现问题的最小案例。

如果愿意参与，请使用仓库的 **Beta feedback** Issue 模板。所有采用数据只按真实、可验证的公开记录统计。
