# Changesets

This directory contains changeset files for tracking changes to the project.

## Creating a changeset

Run:

```bash
npm run changeset
```

This will guide you through creating a changeset file.

## How it works

1. Make your changes
2. Run `npm run changeset` to create a changeset describing your changes
3. Commit the changeset file along with your changes
4. When ready to release, the CI will automatically:
   - Bump the version in `pyproject.toml`
   - Update `CHANGELOG.md`
   - Publish to PyPI
   - Create a GitHub release
