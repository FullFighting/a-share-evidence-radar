# Security policy

## Supported version

Security fixes are applied to the latest commit on the default branch. Before the first tagged release, no older snapshot is supported.

## Reporting a vulnerability

Do not publish webhook URLs, bot tokens, cookies, private watchlists, or a working exploit in a public Issue. Use the repository's enabled GitHub private vulnerability reporting feature. If GitHub does not show that option, open a public Issue containing only a request for a private contact channel; do not include exploit or secret details.

Include the affected file or workflow, impact, minimal reproduction, and suggested mitigation. Remove all live credentials and personal market data.

## Security boundaries

- Delivery is preview-only unless `--send` is explicitly supplied.
- Secrets are read from environment variables and redacted from previews.
- The project does not store brokerage credentials or execute trades.
- Collectors must not bypass login, payment, CAPTCHA, robots rules, or rate limits.
- Inputs and remote endpoints should be treated as untrusted.

If a credential is accidentally committed, revoke it immediately. Deleting it from the latest commit is not sufficient because it may remain in Git history.
