# Changelog

All notable changes will be documented in this file.

## Unreleased

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
