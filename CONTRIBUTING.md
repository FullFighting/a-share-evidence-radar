# Contributing

Thank you for helping make A-share alerts more verifiable and less noisy.

## High-value contributions

- Add a source adapter that uses an authorized public feed or documented API.
- Submit an anonymized false-positive, false-negative, or clustering counterexample.
- Improve provenance handling, evidence independence, or contradiction detection.
- Add a notification channel without weakening preview-first safety.
- Improve Chinese or English documentation with a reproducible example.

Please do not add scrapers that bypass login, payment, CAPTCHA, robots rules, or access controls. Do not commit real webhook URLs, bot tokens, cookies, brokerage data, or personal holdings.

## Development workflow

1. Open an Issue describing the user-visible problem and a minimal example.
2. Keep the implementation standard-library only unless an optional dependency has a clear, documented benefit.
3. Add or update a case in `skills/monitor-a-share-events/references/benchmark-cases.json` for behavior changes.
4. Add unit tests for scripts or delivery formats.
5. Run:

```bash
python -m unittest discover -s tests -v
python skills/monitor-a-share-events/scripts/evaluate_radar.py
python skills/monitor-a-share-events/scripts/doctor.py
```

6. Update both `README.md` and `README_ZH.md` when user-facing behavior changes.

## Adapter contract

Adapters emit UTF-8 JSONL following `skills/monitor-a-share-events/references/event-schema.md`. Preserve canonical URLs and original publication timestamps. Classify uncertain items conservatively, and use a shared `evidence_origin` when multiple observations come from one upstream document or syndicated story.

Network adapters must set a descriptive User-Agent, use finite timeouts, respect source terms and rate limits, and surface errors rather than silently returning incomplete success.

## Pull request checklist

- [ ] The PR solves one clearly described problem.
- [ ] Tests and benchmark cases cover the change.
- [ ] No secret, private holding, copyrighted data dump, or access-control bypass is included.
- [ ] Alert wording remains neutral and does not become investment advice.
- [ ] Documentation is updated where needed.
