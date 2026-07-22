# Governance

## Maintainer responsibility

FullFighting is the current primary maintainer and release owner. The maintainer reviews source provenance, evidence-gate behavior, notification safety, privacy boundaries, and release notes.

## Decision process

- Use public Issues for bugs, adapters, benchmark failures, and roadmap proposals.
- Require a regression test and benchmark case for behavior changes.
- Prefer the smallest change that preserves deterministic output and the evidence gate.
- Record material decisions in the accepted PR or linked Issue; do not rely on private chat as the only rationale.
- Treat market reaction as observation, never proof that an event caused a price move.

The maintainer may reject sources that require login, bypass access controls, lack stable provenance, or cannot be tested without publishing private data. A source adapter does not become Tier 1 merely because it parses successfully.

## Contributions and review

Anyone may open an Issue or PR under the contribution and security policies. Non-trivial changes require passing CI and one maintainer review. The author of a change should not describe fictional fixtures as real adoption or production accuracy.

If more recurring maintainers join, this document will be updated with their scope and a two-reviewer rule for evidence-gate or notification-security changes.

## Releases

The release owner publishes versioned notes that identify changes to evidence gating, cooldown state, notification payloads, and privacy boundaries. Security-sensitive fixes may be prepared privately and disclosed after a safe release is available.

## Conduct and security

All participation follows [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Report vulnerabilities through GitHub private vulnerability reporting when available, following [SECURITY.md](SECURITY.md).
