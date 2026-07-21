# Source policy

## Source tiers

| Tier | Typical sources | Use |
|---|---|---|
| 1 | Issuer disclosure, SSE, SZSE, BSE, CSRC, official ministry or court publication | Sufficient to pass the authority side of the evidence gate when the document is verified |
| 2 | Licensed wire or established financial newsroom with original reporting | Strong corroboration; verify cited primary material |
| 3 | Data portals, aggregators, research blogs, community-maintained feeds | Discovery and context; require independent corroboration |
| 4 | Social posts, forums, screenshots, unattributed forwards | Lead only; never sufficient alone |

A Tier 1 claim is authoritative only when the fusion stage independently loads an auditable source registry, verifies the exact source name/location, and finds an allowed canonical `https` URL or registry-recognized stable evidence identifier. Free-form `--source-tier 1`, an event-file `source_tier_verified` flag, a source-name substring, or successful parsing is not verification.

Search-result snippets, copied headlines, and mirrors inherit the weaker of the original source and the access path until the canonical page is verified.

## Independence rules

- Count syndicated copies of the same article as one source.
- Set the same `evidence_origin` on syndicated copies or observations derived from the same upstream document.
- Exact normalized-content fingerprints may collapse byte-for-byte or text-identical copies automatically. Altered rewrites still require provenance annotation; do not claim semantic syndication detection without evidence.
- Count several portals citing the same announcement as one underlying fact plus the announcement.
- Prefer different evidence types: official disclosure plus market data is more informative than two copies of one headline.
- A denial is counterevidence, not corroboration.

## Collection strategy

1. Poll official disclosure and exchange sources incrementally by publication time or stable identifier.
2. Use established financial news for discovery and context.
3. Add market observations only after the factual event record exists.
4. Canonicalize URLs, retain observation time in `published_at`, preserve the underlying event/original-disclosure time in `event_at`, and store retrieval time separately.
5. Apply source-specific rate limits, exponential backoff, and conditional HTTP headers where supported.

## Freshness and latency

“Real time” must describe the actual pipeline. Distinguish:

- exchange or vendor streaming data;
- minute-level polling;
- scheduled digest;
- delayed public data.

Never promise lower latency than the slowest required source. When an underlying event is older than the report, populate `event_at`; repost time must not refresh old information. When a source timestamp is absent, treat freshness as unknown.

## Recommended event focus

Prioritize events with a plausible information edge for research:

- regulatory action, exchange inquiry, risk warning, investigation;
- earnings preannouncement or material correction;
- merger, restructuring, control change, suspension or termination;
- buyback, insider increase/decrease, pledge or unlock event;
- material contract, production halt, litigation, safety or product incident;
- policy changes with a traceable sector exposure path;
- price or volume anomaly that follows, rather than substitutes for, verified evidence.
