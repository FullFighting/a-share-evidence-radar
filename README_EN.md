<p align="center">
  <img src="docs/assets/hero.svg" alt="A-share Evidence Radar" width="100%">
</p>

<p align="center">
  English · <a href="README.md">中文</a>
</p>

<p align="center">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white">
  <img alt="Zero dependencies" src="https://img.shields.io/badge/runtime-zero_dependencies-16a085">
  <a href="https://github.com/FullFighting/a-share-evidence-radar/actions/workflows/validate.yml"><img alt="CI" src="https://github.com/FullFighting/a-share-evidence-radar/actions/workflows/validate.yml/badge.svg"></a>
  <img alt="Public benchmark" src="https://img.shields.io/badge/benchmark-10%2F10-2ea44f">
  <img alt="MIT License" src="https://img.shields.io/badge/license-MIT-green">
</p>

# A-share Evidence Radar

An evidence-first Codex Skill that turns company disclosures, regulator updates, financial news, and observed market reactions into low-noise, auditable alert cards.

> Registry-verified primary evidence or two independent sources → watchlist relevance → no credible contradiction → fresh timestamp → alert eligibility.

It is not another headline forwarder. The radar clusters duplicate coverage, prevents syndicated copies from masquerading as independent confirmation, separates price reaction from causal claims, and defaults to a redacted delivery preview.

## What an alert looks like

<p align="center">
  <img src="docs/assets/event-card.svg" alt="Evidence Radar event card with score, four quality gates, and primary evidence" width="100%">
</p>

Each card answers five questions: **what happened, who is affected, where the evidence came from, why the alert matters, and what could invalidate it**. A headline match alone never triggers an external send.

## What makes it different

| Capability | Keyword bot | Price alert | Evidence Radar |
|---|:---:|:---:|:---:|
| Cross-source event clustering | — | — | ✓ |
| Syndication-aware source counting | — | — | ✓ |
| Confirmation/denial conflict gate | — | — | ✓ |
| Watchlist, sector, and keyword relevance gate | Partial | ✓ | ✓ |
| Auditable score breakdown | — | — | ✓ |
| Safe multi-channel delivery preview | Partial | Partial | ✓ |
| Public behavioral benchmark | — | — | ✓ |

## 30-second offline demo

Python 3.10+ is the only runtime requirement. These commands make no network request.

On Windows, if `python` opens the Microsoft Store, install Python 3.10+ and replace `python` below with `py -3.10`. On Linux/macOS, `python3` is commonly the right launcher.

```bash
python skills/monitor-a-share-events/scripts/doctor.py

python skills/monitor-a-share-events/scripts/run_radar.py \
  --config skills/monitor-a-share-events/assets/examples/radar-config.json

python skills/monitor-a-share-events/scripts/evaluate_radar.py
```

Expected results: `READY` from the doctor and `10/10 (100.0%)` from the public benchmark. All bundled events are fictional and safe to reproduce.

## Install as a Codex Skill

The [official Codex Skill documentation](https://learn.chatgpt.com/docs/build-skills) says repository skills belong in `$REPO_ROOT/.agents/skills` and personal skills in `$HOME/.agents/skills`. Copy or symlink the `skills/monitor-a-share-events` directory there. Codex detects changes automatically; restart it if the skill does not appear. This repository also includes `.codex-plugin/plugin.json` for plugin distribution.

Then invoke it explicitly:

```text
Use $monitor-a-share-events to monitor my A-share watchlist. Merge disclosures, news, and observed market reactions into low-noise evidence cards. Preview only; do not send.
```

## Pipeline

```mermaid
flowchart LR
    A["RSS / Atom / JSON Feed / normalized events"] --> B["Normalize and map symbols"]
    B --> C["Cluster one real-world event"]
    C --> D{"Evidence gate"}
    D -->|"Registry-verified Tier 1 or 2 independent sources"| E{"Relevance gate"}
    D -->|"Insufficient"| H["Held for verification"]
    E -->|"Watchlist / sector / keyword"| F{"Conflict gate"}
    E -->|"Unrelated"| H
    F -->|"No credible unresolved contradiction"| K{"Freshness gate"}
    F -->|"Confirm + deny"| H
    K -->|"Valid time"| G["Auditable evidence card"]
    K -->|"Stale or future"| H
    G --> I["Cooldown deduplication"]
    I --> J["Send only after explicit approval"]
```

Every card exposes `score_breakdown`, `evidence_gate`, `relevance_gate`, `conflict_gate`, `freshness_gate`, independent-source count, original links, observed market reaction, and invalidation conditions.

## Source collection

`collect_feeds.py` supports local files and explicit `http(s)` RSS, Atom, and JSON Feed URLs. It does not log in, bypass CAPTCHAs, scrape paywalls, or interpret successful parsing as verified truth.

`--source-tier` is only an operator assertion. Fusion ignores an event-file `source_tier_verified` flag and independently checks the registry plus an allowed canonical `https` URL or stable ID. The collector collapses exact cross-site copies through content fingerprints; rewritten syndication still needs a shared `evidence_origin`, and recycled news should preserve the underlying `event_at`. See the [event contract](skills/monitor-a-share-events/references/event-schema.md) and [source policy](skills/monitor-a-share-events/references/source-policy.md).

## Safe delivery

Feishu, DingTalk, WeCom, Telegram, Bark, and generic Webhooks are supported. Without `--send`, the tool prints a redacted preview and performs no network write. Credentials must be supplied through environment variables and must never be committed.

## Quality and contribution

The [public benchmark](skills/monitor-a-share-events/references/benchmark-cases.json) covers authoritative disclosures, independent corroboration, single-source rumors, syndicated copies, conflicting claims, irrelevant official news, stale events, future timestamps, forged Tier 1 flags, and recycled old events.

```bash
python -m unittest discover -s tests -v
python skills/monitor-a-share-events/scripts/evaluate_radar.py
```

The benchmark score describes only the published cases, not real-market accuracy. The most valuable contributions are anonymized failures, source adapters, clustering counterexamples, provenance labels, and secure notification channels. Read [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md) before contributing.

## Roadmap

- [x] Deterministic clustering, scoring, and four quality gates
- [x] RSS / Atom / JSON Feed adapter
- [x] Six delivery channels, cooldown state, doctor, and benchmark
- [ ] Contract-tested primary-disclosure adapters
- [ ] Market-reaction adapters that avoid causal overclaiming
- [ ] Community-maintained false-positive and false-negative corpus
- [x] Codex plugin manifest and standard distribution layout
- [ ] Public marketplace installation and versioned releases

## Boundaries

This project only processes information the user is authorized to access. It does not bypass access controls, represent delayed public data as exchange-grade real time, connect to brokerage accounts, execute orders, or provide deterministic trading calls.

MIT License. See [LICENSE](LICENSE).
