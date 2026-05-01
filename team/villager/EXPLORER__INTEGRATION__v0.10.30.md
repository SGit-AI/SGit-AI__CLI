# Explorer Integration Notes — v0.10.30

**Audience:** The Opus session that wrote the v0.10.30 brief-pack.
**Date:** May 1, 2026
**Explorer branch:** `claude/cli-explorer-session-J3WqA`

This document records decisions and changes made by the Explorer agent
while reviewing and integrating the Sonnet agent's brief executions.
It is the counterpart to `SONNET__ONBOARDING__v0.10.30.md`.

---

## Integration process in place

The Sonnet agent pushes to `claude/sonnet-onboarding-oMP6A`. The Explorer
agent reviews each batch, applies fixes, and merges into
`claude/cli-explorer-session-J3WqA`, which Dinis merges to `dev`.

The full review log (what was fixed and why on each merge) is at:
`team/humans/dinis_cruz/claude-code-web/05/01/v0.10.30/10__villager-integration-review-log.md`

---

## Recurring issue: multi-paragraph docstrings

Every batch so far has contained multi-paragraph docstrings and multi-line
comment blocks in violation of CLAUDE.md. The Sonnet onboarding doc has been
updated (`00b__explorer-review-process.md` in the brief-pack) to call this
out explicitly with examples. If you write future briefs, add a reminder that
docstrings must be one line maximum.

---

## CI changes made by the Explorer

**Publish restricted to main only** (`ci-pipeline__dev.yml`)

`should_publish_pypi` and `should_publish_dockerhub` were removed from the
dev pipeline. Dev pushes now only increment the tag. Publishing happens
exclusively on main branch pushes. This prevents half-baked dev releases
appearing on PyPI and Docker Hub.

**Two-pass parallel CI** (`pytest__run-tests/action.yml`)

The Sonnet agent's brief 05 work added `pytest-xdist` two-pass execution:
- Pass 1: parallel (`-n auto`, excludes `no_parallel` marker)
- Pass 2: serial (only `no_parallel` tests, appends coverage)
Exit code 5 (no tests collected) handled as success.

---

## Architectural decision: mutation tests in CI

**Doc:** `team/villager/dev/v0.10.30__brief-pack/21b__addendum-mutation-ci-architecture.md`

Brief 21's `git stash / git checkout --` mutation revert approach is
**replaced** by `git worktree` isolation for CI safety. Key points:

- Python `sys.modules` caches mutated imports — stash-and-run is not safe
- Signal interrupts can leave mutations live in the working tree
- Solution: one `git worktree` per mutation, created from HEAD, discarded
  after the run. Main checkout is never touched.

Two new CI jobs scoped (to be implemented in brief 21):
- `run-mutation-tests` — calls `tests/mutation/run_mutations.py`
- `run-appsec-tests` — `pytest tests/appsec/` (once that folder has content)

Both gate `increment-tag`.

New test folder structure:
```
tests/mutation/   # orchestrator script, NOT a pytest folder
tests/appsec/     # adversarial tests, normal pytest
```

---

## Docker Hub publishing added (Explorer work, not Villager)

Separate from the brief-pack, the Explorer session added:
- `docker/Dockerfile` + `docker/setup-sgit-docker.sh`
- CI job `publish-to-dockerhub` in `ci-pipeline.yml` (main only)
- Image published to `diniscruz/sgit-ai:latest` + `diniscruz/sgit-ai:<version>`
- Wheel built in CI and installed into Docker image (avoids PyPI timing race)
- Version read from wheel filename, not `_version.py` (avoids checkout timing bug)

---

## Status of briefs (as of May 1, 2026)

| Brief | Status | Notes |
|---|---|---|
| 03-06 | Done | Shared fixtures, CI parallelization |
| 10 | Done | chmod 0600 on `.sg_vault/local/` files |
| 11 | Done | Secure unlink — zero-overwrite before delete |
| 12 | Done | Clear KDF cache at passphrase boundaries |
| 13 | Done | write_file guard + typed exceptions + fail-closed clone_mode |
| 14-22 | Pending | Sonnet agent working through in order |

Brief 21 scope extended — see `21b__addendum-mutation-ci-architecture.md`.
