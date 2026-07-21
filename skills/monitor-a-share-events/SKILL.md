---
name: monitor-a-share-events
description: Monitor A-share watchlists with evidence-first, low-noise event alerts. Use for company announcements, exchange or regulator disclosures, financial news, and observed price anomalies that need source-aware clustering, evidence/relevance/conflict/freshness gates, explainable scoring, configuration diagnosis, cooldown deduplication, safe Feishu/DingTalk/WeCom/Telegram/Bark/Webhook delivery, or reproducible false-positive and false-negative feedback. Do not use for autonomous trading or unsupported buy/sell calls.
---

# A-share evidence radar

Create high-signal alerts instead of forwarding every headline. Require either one authoritative primary source or independent corroboration before an event is push-eligible. Explain why the event matters, why it reached the user, and what evidence is still missing.

Resolve `SKILL_ROOT` as the directory containing this `SKILL.md`. Resolve bundled `scripts/`, `references/`, and `assets/` relative to `SKILL_ROOT`; do not assume the current working directory is the skill directory. Use absolute paths when invoking scripts from another directory.

## Core workflow

1. Establish scope.
   - Resolve the watchlist, sectors, keywords, desired latency, quiet hours, and notification channels.
   - If details are absent, default to a preview-only run for a small supplied watchlist. Do not invent holdings.
2. Validate configuration before network access.
   - Run `scripts/validate_config.py --config <config>` for an offline check of paths, parameter ranges, source-registry shape, and accidentally embedded credentials.
   - Fix every failure before collecting. Review warnings instead of silently ignoring them.
   - Keep webhook URLs, bot tokens, chat IDs, cookies, and API keys in environment variables, never in the config.
3. Plan sources.
   - Read [references/source-policy.md](references/source-policy.md) when selecting or evaluating sources.
   - Read [references/source-registry.md](references/source-registry.md) before granting a feed verified Tier 1 status.
   - Prefer issuer, exchange, regulator, and statutory-disclosure sources. Treat portals, social posts, and reposts as discovery leads.
   - Browse or query live sources for current monitoring tasks; never treat cached model knowledge as current market information.
4. Normalize observations.
   - Read [references/event-schema.md](references/event-schema.md) before creating input files or adapters.
   - Preserve timestamps, canonical URLs, source identity, source tier, affected symbols, and factual wording.
   - Separate facts from interpretation. Mark rumors and denials explicitly.
   - For RSS, Atom, or JSON Feed inputs, run `scripts/collect_feeds.py`. Treat its output as normalized observations, not verified facts.
5. Fuse and score.
   - Run `scripts/fuse_events.py` to cluster duplicates, apply the evidence gate, score relevance and materiality, and create alert cards.
   - Inspect held and suppressed counts. Do not lower the threshold merely to produce output.
   - Inspect `score_breakdown` and all four gates: evidence, relevance, conflict, and freshness.
6. Verify important cards.
   - Open the primary source for every critical card.
   - Confirm symbol, issuer, publication time, event type, and whether the news is new or a recycled report.
   - Add counterevidence or an invalidation condition when available.
7. Preview before delivery.
   - Show the exact message body and target channel, but keep endpoints, tokens, chat IDs, and routing identifiers redacted.
   - Run `scripts/push_alert.py` without `--send` for a safe preview.
   - Send only after the user authorizes the external write. Never expose webhook URLs, bot tokens, chat IDs, or cookies.
8. Schedule only on request.
   - Use the product's automation mechanism rather than inventing cron directives when automations are available.
   - Keep collection frequency within source terms and rate limits. Prefer conditional requests and incremental state.

## Run the complete pipeline

Prefer the config-driven entry point for first use and scheduled workflows. The bundled config is self-contained and fictional.

```powershell
python <SKILL_ROOT>/scripts/run_radar.py `
  --config <SKILL_ROOT>/assets/examples/radar-config.json
```

`--commit-state` is required to update configured deduplication state. `--send` is required for any configured external notification and may be used only after explicit user authorization.

## Fuse event observations

Use JSON or JSONL inputs. The command is deterministic and standard-library only.

```powershell
python scripts/fuse_events.py `
  --events events.jsonl `
  --watchlist watchlist.json `
  --source-registry source-registry.json `
  --format markdown `
  --min-score 60
```

For repeat runs, provide state. State is read by default and updated only with `--commit-state`.

```powershell
python scripts/fuse_events.py `
  --events events.jsonl `
  --watchlist watchlist.json `
  --source-registry source-registry.json `
  --state radar-state.json `
  --commit-state `
  --cooldown-minutes 360 `
  --output alerts.md
```

Treat an event as push-eligible only when:

- at least one registry-verified Tier 1 observation has a canonical URL or stable evidence identifier, or at least two independent sources corroborate it;
- its score meets the configured threshold;
- it matches the configured watchlist, sector, or keyword when a filter is active; and
- no unresolved confirmation/denial conflict remains; and
- its underlying `event_at` (falling back to `published_at`) is neither stale nor beyond the allowed future clock skew.

Keep a rumor or single secondary report in the held queue. A large price move is corroborating context, not proof of the claimed cause.

## Collect feed observations

Use the bundled adapter for user-authorized RSS, Atom, and JSON Feed sources. It performs no login, browser bypass, or site scraping.

```powershell
python scripts/collect_feeds.py `
  --feed feed.xml `
  --watchlist watchlist.json `
  --source-registry source-registry.json `
  --output events.jsonl
```

For an explicit `https://` feed URL, respect its terms and polling limits. A command-line `--source-tier` is an unverified operator assertion; Tier 1 is downgraded unless a source registry verifies it and the event has a canonical reference. A parsed feed item does not become authoritative merely because parsing succeeded.

## Diagnose and evaluate

Validate a user config without fetching remote feeds:

```powershell
python scripts/validate_config.py --config radar-config.json
```

Run the full offline readiness check before the first live or scheduled workflow:

```powershell
python scripts/doctor.py --config radar-config.json
```

Run `scripts/evaluate_radar.py` against the public benchmark after changing clustering, evidence, relevance, conflict, or freshness rules. Do not claim quality improvements without adding a case that demonstrates them.

## Turn real failures into public tests

When a user reports a missed alert, noisy alert, bad cluster, provenance mistake, or false conflict:

1. Reproduce the result locally before changing a rule.
2. Replace private holdings, credentials, personal data, and licensed article text with fictional or explicitly anonymized values.
3. Preserve only the minimum fields needed to demonstrate the failure, including timestamps and source independence.
4. State the actual card state, expected card state, command, Python version, and why the expectation is safer.
5. Add a benchmark case and a unit test before changing behavior.
6. Offer to open the repository's anonymized failure-case Issue only when the user authorizes that external write.

Never describe self-authored benchmark cases as real users, production accuracy, or market validation.

## Preview or send an alert

Keep secrets in environment variables. Supported channels and environment names are documented by the script help.

```powershell
# Safe preview; performs no network request.
python scripts/push_alert.py --channel feishu --input alerts.md

# External write; use only after explicit approval.
python scripts/push_alert.py --channel feishu --input alerts.md --send
```

If a platform rejects Markdown, retry as plain text rather than changing the factual content. Record delivery status separately from event state.

## Alert quality contract

Every delivered card must contain:

- event title and affected symbol or sector;
- publication time and freshness;
- evidence level and independent source count;
- primary links, with the authoritative link first;
- a concise reason it is relevant to the watchlist;
- observed market reaction, clearly separated from causal claims;
- uncertainty, counterevidence, or invalidation condition;
- a neutral research label, never an instruction to trade.

Prefer wording such as “值得核验”“触发监控条件” and “尚未获得官方确认.” Avoid “必涨”“抄底”“立即买入” and fabricated causal explanations.

## Operating boundaries

- Do not bypass paywalls, CAPTCHAs, authentication, robots rules, or source rate limits.
- Do not represent delayed public data as exchange-grade real time.
- Do not use one reposted story as multiple independent confirmations.
- Do not send external messages, create bots, or schedule recurring jobs without authorization.
- Do not place orders or connect brokerage credentials. This skill is for information triage and research, not investment advice.

## Failure handling

- If the authoritative source is unavailable, label the card `verification_pending` and hold it unless the user explicitly requests unverified leads.
- If timestamps are missing, reject the observation at normalization or hold it as `verification_pending`; never invent a publication time.
- If symbol mapping is ambiguous, show candidate mappings and do not push.
- If all events fail the evidence gate, report that no push-worthy event was found; do not fill the quota with noise.
