# Villager Dev — v0.10.30 Consolidated Report

**Author:** Villager Dev
**Date:** 2026-05-01
**Sprint range:** commits `bc10167…4d53f79` (Apr 20 – May 1, 2026)
**Branch:** `claude/villager-multi-agent-setup-sUBO6`
**Style:** read-only review — no source or test edits. Findings only.

---

## Executive summary

The v0.10.30 sprint shipped seven new feature areas (probe, write,
cat/ls extensions, fetch, delete-on-remote, rekey wizard + 4 step
sub-commands, sparse / read-only clone, resumable push with
per-blob checkpointing, deterministic HMAC-IV for tree CAS). All
seven landed working code + happy-path tests, but the code-quality
delta against the v0.5.11 baseline (94% Type_Safe, 18 mock
violations) is **mixed**:

- **Compliance preserved:** `cli/__init__.py` purity (finding 03);
  no stray `__init__.py` under `tests/` (finding 04); the three
  sync-layer test files (Probe, Delete_Rekey, Write_File) are
  exemplary no-mock tests (finding 02 sub-2.4).

- **Compliance eroded:**
  - 4 × `class FakeArgs` homemade stubs added in
    `tests/unit/cli/test_CLI__Vault__Write.py` (finding 02 sub-2.3).
  - 9 new `Vault__Sync` public methods returning raw `dict` instead
    of Type_Safe schemas (finding 01).
  - 2 new persisted JSON state files (`clone_mode.json`,
    `push_state.json`) without `Schema__*` classes (finding 10).
  - `Vault__Sync.py` grew from ~2400 to **2986 LOC**; `CLI__Vault.py`
    grew to **1381 LOC** (finding 06).

- **Critical coverage gap:**
  - `encrypt_deterministic` and `encrypt_metadata_deterministic`
    (the sprint's headline crypto change) have **zero direct tests**.
    The "test vectors mandatory" rule is violated for a brand-new
    cryptographic primitive (finding 09). **Escalates to AppSec.**
  - Resumable-push checkpoint mechanism (`_load_push_state` /
    `_save_push_state` / `_clear_push_state`) has **no dedicated
    test file** (finding 07).

## Top three issues

1. **Crypto determinism untested (finding 09)** — `encrypt_deterministic`
   is used at 8 call sites in `Vault__Sub_Tree.py` to build the
   entire tree-object CAS layer, but has zero direct tests, no
   browser interop vector, and no determinism / round-trip /
   different-key assertions. Major; potential blocker pending AppSec.

2. **Resumable push checkpoint untested (finding 07 sub-7)** — the
   sprint's user-visible reliability feature ("upload blobs first
   with per-blob checkpoint") has no test that asserts what happens
   when a push is interrupted, the state file is written, and a
   second push resumes from the checkpoint. The `_load_push_state` /
   `_save_push_state` / `_clear_push_state` triplet at
   `Vault__Sync.py:2729–2748` is wholly untested.

3. **`Vault__Sync.py` at 2986 LOC (finding 06)** — single file with
   8+ logical responsibilities; v0.5.11 already flagged it as the
   worst file in the codebase, sprint added ~600 LOC. Architecture-level
   concern. Architect-owned.

## Mock count breakdown (per Dinis directive)

Source: `grep -rn 'unittest.mock\|MagicMock\|@patch\|monkeypatch' tests/`

| Category | Count | Note |
|----------|------:|------|
| Total mock-pattern lines (all categories) | **553** | — |
| `unittest.mock` / `MagicMock` / `@patch` lines | 34 | concentrated in 9 files |
| `monkeypatch` lines | 519 | concentrated in 19 files |
| Newly introduced this sprint (in newly-added test files, `unittest.mock`) | **0** | clean |
| Newly introduced this sprint (in newly-added test files, homemade stubs) | **4** | `FakeArgs` × 4 in `test_CLI__Vault__Write.py` |
| Carryover from before sprint, untouched in modified files | bulk of 553 | — |

**Newly introduced this sprint: 4 homemade stubs (FakeArgs).** No
new `unittest.mock` imports or `monkeypatch` uses were introduced
in newly-added sprint tests. Carryover backlog (~550 lines) remains
above the v0.5.11 reported baseline of 18 — recommend reconciling
the counting method with Sherpa.

## Type_Safe regressions

- **Count of new fields with raw primitives in Type_Safe classes:** 0
  (the sprint added 0 new `Type_Safe` classes — only methods on
  existing classes).
- **Count of method signatures introducing raw `str`/`int`/`dict`:** 9
  on `Vault__Sync` (the new methods listed in finding 01).
- **Count of new persisted JSON files without `Schema__*` class:** 2
  (clone_mode.json, push_state.json — finding 10).
- **Worst offender:** `Vault__Sync.write_file` (`also: dict = None,
  -> dict`) — this method takes a `dict` of vault_path → bytes for
  atomic multi-file writes, mutates a flat-map `dict`, and returns
  a `dict` with `unchanged: bool`, `paths: dict`. Shape is
  load-bearing for the agent / programmatic workflow but is
  documented only in a docstring.

## Test coverage gaps — top three

1. **Resumable push** — zero direct test file. `_load_push_state` /
   `_save_push_state` / `_clear_push_state` have no unit tests, and
   no end-to-end test that interrupts a push, leaves
   `push_state.json`, and re-pushes. Single biggest gap of the
   sprint.

2. **`encrypt_deterministic` / `encrypt_metadata_deterministic`** —
   no direct tests, no determinism assertion, no IV-derivation
   assertion, no browser interop vector. Used at 8 call sites in
   `Vault__Sub_Tree`. The "true CAS dedup" claim from the sprint
   commit message is not asserted by any test.

3. **`probe_token` share-token branch** — the second probe path
   (line 1824–1830 of `Vault__Sync.py`) returning `{'type':
   'share', 'transfer_id': ...}` has **zero coverage**. Only the
   vault-token branch is tested. Network-failure paths in probe are
   also untested (the bare `except Exception:` swallows real errors;
   see finding 8.1).

## Escalations

### To Architect (boundary calls)

- **Finding 01 / 10:** Should `Vault__Sync` public-method return
  shapes become `Schema__*` instances? Or are dicts intentionally
  the public Python contract for agent integrations?
- **Finding 05 / 06:** Class-split for `Vault__Sync.py` (2986 LOC)
  and `CLI__Vault.py` (1381 LOC). Eight + four candidate sub-classes
  identified.
- **Finding 10:** Pick names + Safe_* types for `Schema__Clone_Mode`
  and `Schema__Push_State`. Should `mode` be an `Enum__Clone_Mode`?

### To AppSec (crypto / security review)

- **Finding 09:** New `encrypt_deterministic` primitive has no
  tests, no browser interop vector, and is used as the substrate
  for tree CAS. Owns the cryptographic-correctness review and the
  test-vector definition.
- **Finding 8.6:** Read-only guard fails **open** when
  `clone_mode.json` is corrupted or malformed —
  `load_clone_mode` returns `{'mode': 'full'}` and the vault becomes
  read-write. Confirm whether this is intended.
- **Finding 02 sub-2.2:** `MagicMock` returns from
  `patch.object(..., return_value=MagicMock())` in
  `test_Vault__GC.py` and `test_Vault__Diff.py` pass attribute
  assertions silently — possible security-test smell.

### To QA (coverage definition)

- **Finding 07** — close the missing-scenario sets across probe,
  rekey, delete-on-remote, write_file, sparse_*, resumable push.
- Suggested new test files: `test_Vault__Sync__Sparse.py`,
  `test_Vault__Sync__Push_Checkpoint.py`,
  `test_Vault__Crypto__Deterministic.py`.

## Items not completed within time budget

- **Per-line `git blame` of mock-pattern lines** to distinguish
  "introduced this sprint" from "carryover and not removed" in
  modified test files. Time-bounded estimate from sampling: most
  of the 553 lines are carryover; the sprint introduced 0 new
  `unittest.mock` imports plus 4 homemade `FakeArgs` stubs.
- **Coverage-percentage delta** vs. v0.5.11. Did not run pytest
  with coverage in this read-only review.
- **Integration-test sweep.** Reviewed unit tests only; the
  Python-3.12 venv integration suite was not run.

## Findings file index

See `00__index.md` for navigation. Each finding file is ≤200 lines and
self-contained.
