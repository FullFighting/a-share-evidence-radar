# Repository guidance

## Scope

Maintain an evidence-first Codex Skill for A-share event monitoring. Keep the runtime deterministic, transparent, and safe for preview-first notifications.

## Constraints

- Keep `skills/monitor-a-share-events/scripts/` compatible with Python 3.10+ and the standard library.
- Treat market reaction as observation, not proof of causality.
- Preserve the evidence gate: Tier 1 primary evidence or at least two independent sources.
- Never add brokerage login, order placement, CAPTCHA bypass, paywall bypass, or committed notification secrets.
- Keep external notification writes behind an explicit `--send` flag.
- Do not weaken tests to accept rumors, duplicate syndication, stale events, or leaked webhook tokens.

## Validation

Run before proposing changes:

```bash
python -m py_compile skills/monitor-a-share-events/scripts/*.py
python -m unittest discover -s tests -v
python skills/monitor-a-share-events/scripts/validate_config.py --config skills/monitor-a-share-events/assets/examples/radar-config.json
```

When the Codex `skill-creator` package is available, also run its `quick_validate.py` against `skills/monitor-a-share-events/`.

## Pull requests

Explain the source or event behavior being changed, include a regression test, and state whether the change affects evidence gating, cooldown state, notification payloads, or privacy boundaries.
