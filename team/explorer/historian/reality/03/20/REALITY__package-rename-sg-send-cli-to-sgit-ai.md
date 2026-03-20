# REALITY: Package Rename — sg-send-cli → sgit-ai

**Date:** 2026-03-20
**Version:** v0.8.15
**Status:** Complete

## Context

The project was originally developed under the name `sg-send-cli` and published to PyPI under that name. The project has moved to a new GitHub organisation (`SGit-AI`) and needs to publish to PyPI as `sgit-ai`.

The previous PyPI trusted publishing OIDC token was scoped to `sg-send-cli`, which caused a 403 error when attempting to publish the renamed package. This rename resolves that by aligning all identifiers.

## What Happened

### Rename Scope

1. **Source directory:** `sg_send_cli/` → `sgit_ai/` (git mv)
2. **All Python imports:** 174 files updated (`from sg_send_cli.` → `from sgit_ai.`)
3. **pyproject.toml:** package name, entry points, repository URLs, coverage config
4. **CI pipeline:** `PACKAGE_NAME` env var
5. **Documentation:** CLAUDE.md, README.md, team/explorer/CLAUDE.md

### What Was Preserved

- Historical team documents left unchanged (accuracy over consistency)
- `team/humans/dinis_cruz/briefs/` — READ-ONLY, not touched
- Environment variable names (`SG_SEND_TOKEN`, etc.) — backward compatibility
- Internal vault directory structure (`.sg_vault/`) — unrelated to package name

### Verification

- **1011 unit tests pass** (Python 3.12, full suite)
- **415 tests pass** on Python 3.11 (safe_types + schemas; crypto tests need 3.12)
- Package installs as `sgit-ai` via `pip install -e .`
- `import sgit_ai` resolves correctly

## Key Decision

The `sgit` CLI entry point was kept alongside the new `sgit-ai` entry point for user convenience. Both point to `sgit_ai.cli:main`.

## Remaining Work

- Configure PyPI trusted publishing for the new `sgit-ai` package name
- Update any external documentation or references that point to `sg-send-cli`
- Consider renaming environment variables (`SG_SEND_*` → `SGIT_*`) in a future release
