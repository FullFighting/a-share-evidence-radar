# Source registry

Use a source registry when an adapter should claim a verified source tier. The registry is local, reviewable configuration; it is not a cryptographic guarantee and must be maintained when domains or ownership change.

```json
{
  "sources": {
    "Example Exchange": {
      "tier": 1,
      "hosts": ["disclosure.example.org"],
      "evidence_origin_prefixes": ["exchange-document:"],
      "allow_local": false,
      "note": "Documented public disclosure feed"
    }
  }
}
```

Rules:

- The key must exactly match the normalized adapter source name.
- `tier` must be 1-4 and follow `source-policy.md`.
- `hosts` constrains remote feeds and event canonical URLs. Fusion accepts only `https` URLs without embedded credentials and with an exact allowed host.
- `evidence_origin_prefixes` optionally recognizes stable identifiers when no canonical URL is available. Keep prefixes narrow and source-specific.
- `allow_local` should normally be `false`; enable it only for reviewed fixtures or offline mirrors the user controls.
- A verified Tier 1 observation still requires a canonical URL or a registry-recognized stable `evidence_origin`.
- Review registry changes like code. A contributor must explain the source owner, access method, terms, and why the tier is appropriate.

Without a matching registry entry, `--source-tier` remains an operator assertion. The fusion stage does not trust `source_tier_verified` from an event file; it recomputes trust and downgrades an unverified Tier 1 claim to Tier 3.
