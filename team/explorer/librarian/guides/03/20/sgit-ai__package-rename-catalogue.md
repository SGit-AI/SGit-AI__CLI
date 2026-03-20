# SGit-AI Package Rename Catalogue

**Date:** 2026-03-20
**Version:** v0.8.15
**Previous Package Name:** sg-send-cli (PyPI), sg_send_cli (import)
**New Package Name:** sgit-ai (PyPI), sgit_ai (import)

## What Changed

| Item | Before | After |
|------|--------|-------|
| PyPI package name | `sg-send-cli` | `sgit-ai` |
| Python import name | `sg_send_cli` | `sgit_ai` |
| Source directory | `sg_send_cli/` | `sgit_ai/` |
| CLI entry points | `sg-send-cli`, `sgit` | `sgit-ai`, `sgit` |
| GitHub repository | `the-cyber-boardroom/SG_Send__CLI` | `SGit-AI/SGit-AI__CLI` |
| CI PACKAGE_NAME | `sg_send_cli` | `sgit_ai` |
| Coverage source | `sg_send_cli` | `sgit_ai` |

## Files Modified

- **245 files** changed in total (641 insertions, 641 deletions)
- **110 source files** in `sgit_ai/` — all imports updated
- **174 Python files** across source and tests — `sg_send_cli` → `sgit_ai`
- **pyproject.toml** — package name, scripts, URLs, coverage config
- **CLAUDE.md** — all references updated
- **README.md** — installation and architecture references
- **CI pipeline** — `.github/workflows/ci-pipeline.yml`

## What Was NOT Changed

- **Historical team documents** (`team/humans/`, `team/villager/`, `team/explorer/historian/`) — left as-is for historical accuracy
- **Environment variable names** (`SG_SEND_TOKEN`, `SG_SEND_BASE_URL`) — kept for backward compatibility
- **Internal vault directory names** (`.sg_vault/`) — not part of this rename scope

## Verification

- All **1011 unit tests** pass (Python 3.12)
- Package installs correctly as `sgit-ai`
- Import `sgit_ai` resolves correctly
