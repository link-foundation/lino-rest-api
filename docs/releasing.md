# Releasing lino-rest-api

JavaScript, Rust and Python share one version. The private root npm workspace
is development tooling and is not published.

Add one changeset to each pull request:

```markdown
---
"lino-rest-api": patch
---

Describe the change here.
```

After a merge to `main`, `.github/workflows/release.yml` runs the tests and
consumes the changeset. `scripts/version-packages.mjs` bumps all three
manifests, both package locks and all three changelogs in one commit. This PR's
patch changeset prepares **0.2.1** from the current **0.2.0**.

The publishing jobs check the exact version with uncached registry requests.
An existing version skips its upload; only HTTP 404 means it is missing.
Network, authentication, rate-limit and server errors fail the check. A push
without a changeset keeps the current version and resumes any missing uploads.
Each registry publishes independently, so one failure does not stop the others.
The GitHub release is created at the version commit after all three jobs succeed.

Rerunning a workflow reuses its `Release-Run` commit, including manual instant
releases. If `main` advanced to an unrelated commit after validation, the
workflow fails rather than publishing code that its tests did not validate;
the newer push has its own workflow run.

The workflow's manual `instant` mode bumps all three packages by the selected
patch, minor or major increment after validation. `changeset-pr` mode opens
a pull request for the same release flow. Run either mode from `main`.

## Trusted publisher setup

All three registries must trust the workflow filename **`release.yml`**, with
owner **`link-foundation`** and repository **`lino-rest-api`**. The publishing
jobs grant `id-token: write` and use:

- npm 11 on Node 24, `npm publish --provenance --access public` from `js/`.
- `rust-lang/crates-io-auth-action@v1` and its short-lived token for
  `cargo publish --locked` from `rust/`.
- `pypa/gh-action-pypi-publish@release/v1` for `python/dist/`.

No registry token secrets are required. GitHub Pages already uses GitHub
Actions as its source; no Pages setting change is needed for this issue.

After this workflow is merged, use
[package-registry-manager](https://github.com/link-foundation/package-registry-manager)
to inspect the jobs and complete the first publication and publisher registration:

```sh
npx package-registry-manager inspect --repository .
npx package-registry-manager setup --repository . --registry npm --package lino-rest-api --execute
npx package-registry-manager setup --repository . --registry crates-io --package lino-rest-api --execute
npx package-registry-manager setup --repository . --registry pypi --package lino-rest-api --execute
```

The first npm and crates.io publication needs browser approval; PyPI needs a
pending publisher configured in the browser. This one-time setup is separate
from subsequent automated OIDC releases. Registry publisher registration and
live uploads cannot be validated by the pull request's test jobs.

See the [npm trusted publishing documentation](https://docs.npmjs.com/trusted-publishers/),
[crates.io authentication action](https://github.com/rust-lang/crates-io-auth-action)
and [PyPI trusted publishing documentation](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

## Local checks

```sh
npm run test:release
python -m build python
python -m twine check python/dist/*
python experiments/check-python-distributions.py
cd js && npm pack --dry-run
cd ../rust && cargo publish --dry-run --locked
```

Release regression tests use temporary fixture repositories and mocked registry
responses. They cover the original multiline version output, coordinated bumps,
tool settings, registry errors, manual changesets and workflow reruns. Set
`DEBUG=1` on release scripts to print stack traces when diagnosing a failure.
