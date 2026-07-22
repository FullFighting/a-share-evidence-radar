# Changelog

All notable changes will be documented in this file.

## 0.3.0 - 2026-07-22

### Added

- Offline user-config validation for paths, parameter ranges, registry shape, notification channels, and credential-like values.
- `doctor.py --config` support and five configuration-safety regression tests.
- A structured early-beta guide and GitHub feedback form for reproducible first-run reports.
- Contract-tested SSE and SZSE primary-disclosure metadata adapters with valid and failed fixtures.
- A standard-library HTTPS client with public-address checks, bounded redirects and retries, response limits, per-host pacing, and conditional-request caching.
- A 40-case fictional public regression suite, `GOVERNANCE.md`, `ADOPTERS.md`, and an opt-in Codex/API maintenance workflow with token-usage capture.

### Fixed

- `doctor.py --config` now fails readiness when the selected notification channel is missing required environment variables, without printing credential values; `run_radar.py --no-notify` remains usable.

### Changed

- Replaced the benchmark score badge with a case-count badge and narrowed syndication claims to exact fingerprints or explicit provenance labels.
- Removed the unsupported claim that an official Skill validator is pinned in CI.

### Security

- Remote feed collection now requires HTTPS and blocks non-public destinations, oversized responses, cross-host redirects, and unbounded retry behavior.

## 0.2.0

### Added

- Evidence-first Codex Skill with deterministic event clustering and scoring.
- Evidence, relevance, conflict, and freshness gates with auditable score breakdowns.
- RSS, Atom, and JSON Feed collection with watchlist symbol mapping.
- Preview-first delivery for Feishu, DingTalk, WeCom, Telegram, Bark, and Webhooks.
- Offline doctor, ten-case public benchmark, and cross-platform test suite.

### Security

- Fusion independently verifies Tier 1 claims against the source registry and rejects non-canonical references.
- Freshness uses the underlying `event_at` when available so a repost cannot refresh old information.

### Changed

- Added a stronger bilingual README first screen, visual event-card preview, and 1280×640 social-preview asset.
- Made the English README the default GitHub landing page and preserved Chinese as `README_ZH.md`.
- Fixed Windows CI subprocess decoding by explicitly reading UTF-8 output.
- Updated official GitHub Actions to their current Node 24-based major versions.
