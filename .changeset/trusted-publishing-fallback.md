---
"lino-rest-api": patch
---

CI/CD: crates.io publishing tries trusted publishing (OIDC) first and falls back to the `CARGO_REGISTRY_TOKEN` (or `CARGO_TOKEN`) secret when OIDC is unavailable.
