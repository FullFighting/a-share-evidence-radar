# Event and watchlist schema

## Event observation

Use one JSON object per observation. Required fields are `title`, `source`, and `published_at`.

```json
{
  "title": "示例公司披露回购方案",
  "summary": "董事会审议通过回购方案，金额区间以公告为准。",
  "source": "上海证券交易所",
  "source_tier": 1,
  "source_tier_verified": true,
  "tier_basis": "registry",
  "evidence_origin": "sse-announcement-20260721-001",
  "url": "https://example.invalid/announcement",
  "published_at": "2026-07-21T09:42:00+08:00",
  "event_at": "2026-07-21T09:40:00+08:00",
  "symbols": ["600000"],
  "sectors": ["银行"],
  "event_type": "buyback",
  "stance": "confirm",
  "confidence": 1.0,
  "metrics": {
    "price_change_pct": 2.8,
    "volume_ratio": 1.9
  },
  "invalidation": "股东大会未通过或公司后续终止方案"
}
```

Fields:

- `source_tier`: claimed integer 1-4. Name-based inference is only a convenience claim; otherwise use Tier 3. It does not set `source_tier_verified`.
- `source_tier_verified`: adapter output for audit only. The fusion stage ignores this input boolean and independently recomputes verification from `--source-registry` plus a canonical reference.
- `tier_basis`: `registry`, `operator_asserted`, or an adapter-specific documented basis.
- `evidence_origin`: optional upstream story or document identifier. Give syndicated copies the same value so they count as one independent source.
- `content_fingerprint`: optional normalized-content hash produced by an adapter. Exact fingerprints count as one evidence origin across domains; altered syndicated copies still require `evidence_origin` or citation-chain annotation.
- `event_at`: optional time of the underlying event or original disclosure. The freshness gate prefers this value so a new repost cannot make old information fresh. If absent, it falls back to `published_at`.
- `first_published_at`: accepted legacy alias for `event_at`.
- `symbols`: six-digit mainland codes. Prefixes such as `sh600000` and `600000.SH` are normalized.
- `event_type`: one of `regulatory`, `earnings`, `merger`, `buyback`, `insider_change`, `contract`, `policy`, `litigation`, `operations`, `market_anomaly`, `rumor`, or `other`.
- `stance`: `confirm`, `deny`, `uncertain`, or `context`.
- `confidence`: source-specific extraction confidence from 0 to 1. It cannot upgrade a weak source into authoritative evidence.
- `metrics`: optional observed market fields. They describe reaction and must not be presented as proof of cause.

Every output card includes `score_breakdown`, `evidence_gate`, `relevance_gate`, `conflict_gate`, and `freshness_gate` so users can audit why it was eligible or held.

## Watchlist

```json
{
  "symbols": {
    "600000": {
      "name": "示例公司",
      "aliases": ["示例简称"],
      "sectors": ["银行"],
      "weight": 0.12
    }
  },
  "keywords": ["回购", "减持", "监管问询"],
  "sectors": ["银行"]
}
```

`weight` is optional context for ranking relevance. The bundled script does not turn portfolio weight into trading advice.

## Output states

- `eligible`: passes score and evidence gate and is not inside cooldown.
- `held`: lacks sufficient evidence or score.
- `suppressed`: matches a recently emitted cluster in state.
- `verification_pending`: reserve this label in downstream adapters when the primary page could not be opened.

`published_at` remains required and describes this observation's publication time. If the source omits it, reject the observation or keep it outside the fusion input as `verification_pending`; do not substitute retrieval time. Adapters should populate `event_at` whenever a story refers to an older disclosure or event.
