# Brief — Dotfile tracking (Sonnet-ready execution brief)

**Date:** 2026-05-11
**Branch:** `claude/improve-cli-hidden-files-RcT0m`
**Audience:** SGit Dev Agent (Sonnet) — implementation pass
**Source brief:** `team/villager/v0.14.x__brief-pack/06__dotfile-tracking-brief.md`
**Status of source:** TODO in `00__index.md` row 06; superseded by this document for execution.

This brief inherits everything from the source brief above and **only documents the
deltas, decisions, and corrections** needed to make it mechanical to implement. Read
brief 06 first; this file does not repeat its rationale.

---

## 1. Decisions locked in this session

| # | Topic                                  | Decision                                                                                                                          |
|---|----------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------|
| 1 | `.idea` / `.vscode`                    | **Keep as `ALWAYS_IGNORED_DIRS`** — matches the source brief. Per-user state is the safer default; users opt in via `.gitignore` negation. |
| 2 | `.env*` coverage                       | **Add a tiny glob exception** — `.env*` is ignored except for the template allowlist `{'.env.example', '.env.sample', '.env.template'}`. Implemented as a dedicated method, NOT generic glob support. |
| 3 | Schema home                            | **`sgit_ai/schemas/inspect/Schema__Ignore_Reason.py`** — new `schemas/inspect/` folder, matching the existing `schemas/<area>/` convention. |
| 4 | Migration surface                      | **CHANGELOG note + release-note draft** — no runtime warnings, no first-run hint. Sonnet drafts a short paragraph as a deliverable. |

---

## 2. Corrections to source brief 06

| # | Source brief says                                  | Reality                                                                                       | Action                                                                                                         |
|---|----------------------------------------------------|-----------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------|
| A | Mirror change in `Vault__Bare`, `Vault__Merge`, `Vault__Sync__Base`. | Source brief misses `Vault__Sync__Push.py:506`, which also duplicates `not d.startswith('.')`. | Edit `Vault__Sync__Push.py:506` too (see §3c). Leave `Vault__Sync__Base.py:160` untouched (per source).        |
| B | Tests live in `tests/unit/core/test_Vault__Ignore.py`. | Tests live in `tests/unit/sync/test_Vault__Ignore.py`.                                        | Keep tests in `tests/unit/sync/`. No move. Add the new CLI tests under `tests/unit/plugins/inspect/`.          |
| C | "~5–10 existing tests need updating."              | Concretely: **3 tests** in `Test_Vault__Ignore__Dotfiles` (lines 50-66) + **1 set assertion** at line 42-47. No other tests touch dotfile-blanket behaviour (grep confirms). | See §4a for the exact list — flip those tests, no broader hunt needed.                                          |
| D | `Vault__Branch_Switch.py` not mentioned.           | It calls `Vault__Ignore` already (see `:367-399`), so it inherits the fix.                    | Do not edit. State this in the PR description so reviewer doesn't go hunting.                                  |
| E | "Mirror the existing `inspect tree` registration." | Pattern lives in `sgit_ai/plugins/inspect/CLI__Inspect.py:11-51`.                              | Copy the `inspect_sub.add_parser(...)` block style verbatim (see §5).                                          |

---

## 3. Code changes — exact files and behaviour

### 3a. `sgit_ai/core/Vault__Ignore.py`

Replace the curated set + both `should_ignore_*` methods with the source brief's "New state" block, with **these adjustments**:

1. **`ALWAYS_IGNORED_DIRS`** — exactly as in source brief §2a "New state" (22 entries).

2. **`ALWAYS_IGNORED_FILES`** — exactly as in source brief §2a "New state" (13 entries: `.env`, `.env.local`, `.env.production`, `.env.development`, `.netrc`, `.pgpass`, `.git-credentials`, `id_rsa`, `id_ed25519`, `id_ecdsa`, `id_dsa`, `.npmrc`, `.pypirc`).

3. **NEW: `.env*` glob with template allowlist.** Add module-level constant:
   ```python
   ENV_TEMPLATE_ALLOWLIST = {'.env.example', '.env.sample', '.env.template'}
   ```
   And a helper method on `Vault__Ignore`:
   ```python
   def _is_env_secret(self, filename: str) -> bool:
       """True if filename starts with '.env' and is not a known template."""
       if not filename.startswith('.env'):
           return False
       return filename not in ENV_TEMPLATE_ALLOWLIST
   ```
   Wire it into `should_ignore_file` *after* the `ALWAYS_IGNORED_FILES` exact-name check:
   ```python
   def should_ignore_file(self, rel_path: str) -> bool:
       filename = rel_path.rsplit('/', 1)[-1] if '/' in rel_path else rel_path
       if filename in ALWAYS_IGNORED_FILES:
           return True
       if self._is_env_secret(filename):
           return True
       return self._matches(rel_path, is_dir=False)
   ```
   This is **the only glob** in the hardcoded layer. All other globs belong in `.gitignore`. Do not generalise this into a `ALWAYS_IGNORED_FILE_GLOBS` set — the source brief's "exact-name only" rule still holds for everything else.

4. **NEW: `explain()` method.** Returns a populated `Schema__Ignore_Reason` (see §3b). Signature:
   ```python
   def explain(self, rel_path: str, is_dir: bool = False) -> 'Schema__Ignore_Reason':
       ...
   ```
   The four `reason_code` values: `'always_ignored_dir'`, `'always_ignored_file'`, `'env_secret_glob'`, `'gitignore_pattern'`, `'tracked'`.
   For `'gitignore_pattern'`, populate `matched_rule` with the raw pattern string (`pattern['pattern']`) — the first pattern that ignored the path wins (last-write-wins semantics from `_matches`, so iterate and capture).

5. **Drop the blanket `startswith('.')` branches** — both of them (source brief §2a lines 33 and 39 in the "Current state" snippet).

### 3b. NEW `sgit_ai/schemas/inspect/__init__.py` + `Schema__Ignore_Reason.py`

Folder is new — create `__init__.py` (empty file is fine; mirror `schemas/merge/__init__.py`).

`Schema__Ignore_Reason.py`:

```python
from osbot_utils.type_safe.Type_Safe import Type_Safe

from sgit_ai.safe_types.Safe_Str__File_Path import Safe_Str__File_Path  # confirm path
# If no Safe_Str__File_Path exists yet, use Safe_Str — do NOT introduce a new
# Safe_* type for this brief. Note it as a follow-up.

class Schema__Ignore_Reason(Type_Safe):
    rel_path     : Safe_Str__File_Path = None
    is_ignored   : bool                = False
    reason_code  : Safe_Str            = None   # see allowed values in §3a.4
    matched_rule : Safe_Str            = None
    description  : Safe_Str            = None
```

**Round-trip invariant required** — add a unit test asserting `from_json(obj.json()).json() == obj.json()` (this is the standard project rule; see source brief §3a test 9).

### 3c. Mirror the blanket-rule removal in three call sites

Use the Edit tool at these exact locations. After these edits the only place where dotfile decisions are made is `Vault__Ignore.should_ignore_*`.

| File                                                      | Line(s)        | Current                                                                                                   | Change                                                                                                  |
|-----------------------------------------------------------|----------------|-----------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------|
| `sgit_ai/core/Vault__Bare.py`                             | 109, 111       | `dirs[:] = [d for d in dirs if os.path.join(root, d) != sg_vault_dir and not d.startswith('.')]` <br> `if filename.startswith('.'): continue` | Replace with a `Vault__Ignore` lookup. Use `load_gitignore(directory)` once before the walk; then `should_ignore_dir` / `should_ignore_file` per entry. Pattern: same as `Vault__Sync__Base._scan_local_directory`. Continue to drop `.sg_vault` by exact match on the absolute path. |
| `sgit_ai/core/actions/merge/Vault__Merge.py`              | 108, 119       | `dirs[:] = [d for d in dirs if d != '.sg_vault' and not d.startswith('.')]`                                | Same approach: lift `Vault__Ignore` outside the walk; filter dirs via `should_ignore_dir`. Keep the `d != '.sg_vault'` explicit guard (defence-in-depth; `.sg_vault` is in `ALWAYS_IGNORED_DIRS` but the explicit check stays).                                                            |
| `sgit_ai/core/actions/push/Vault__Sync__Push.py`          | 504-506        | `if '.sg_vault' in dirs: dirs.remove('.sg_vault')` <br> `dirs[:] = [d for d in dirs if not d.startswith('.')]` | Drop only line 506 (the blanket filter). Keep the `.sg_vault` removal on lines 504-505. The walk is looking for `*.conflict` files in the working tree; after the change, conflict files inside `.claude/` etc. become visible — which is correct. |

**Do NOT touch:**
- `sgit_ai/core/Vault__Sync__Base.py:160` (empty-dir cleanup; source brief §2b is explicit).
- `sgit_ai/core/actions/branch/Vault__Branch_Switch.py` (already uses `Vault__Ignore`; inherits fix).

### 3d. CLI command `sgit inspect ignored`

Per source brief §2c/§2d, three modes: default walk, `--rules`, `--why <path>`. Add to `sgit_ai/plugins/inspect/CLI__Inspect.py` mirroring the `inspect tree` block at lines 22-26. New handler method `cmd_inspect_ignored` on `CLI__Vault` (or wherever `cmd_inspect_tree` lives — match the existing dispatch pattern; do not invent a new class).

**Output format** — match source brief §2c verbatim (those mockups are the spec). One small clarification:
- The default-mode walk should respect the same `Vault__Ignore` instance used for tracking. **Do not call `os.walk` recursively into directories that are themselves ignored** — that would print every file under `node_modules/`. Group output as: "Hardcoded dirs", "Hardcoded files", "Gitignore patterns" — show each *top-level* ignored item, not its contents. Source brief's mockup already does this (`node_modules/` shown once, not 50k files inside).

**Exit codes:** all three modes return 0 on success. `--why <path>` returns 0 whether the path is tracked or ignored; only a non-existent path produces a non-zero exit (source brief §3b test 8).

---

## 4. Tests

### 4a. Existing tests to flip (`tests/unit/sync/test_Vault__Ignore.py`)

| Lines     | Test                                          | Change                                                                                                        |
|-----------|-----------------------------------------------|---------------------------------------------------------------------------------------------------------------|
| 42-47     | `test_always_ignored__all_entries`            | Update the expected set literal to match the new 22-entry `ALWAYS_IGNORED_DIRS`.                              |
| 52-54     | `test_dotfile_ignored` (`.hidden`)            | Flip assertion: `.hidden` is now **tracked** (`is False`). Rename to `test_unknown_dotfile_is_tracked`.       |
| 56-58     | `test_dotfile_in_subdir` (`src/.env`)         | Still ignored — but now via `ALWAYS_IGNORED_FILES`, not the blanket rule. Keep the assertion; rename to `test_env_file_in_subdir_still_ignored` to reflect the reason. |
| 60-62     | `test_dotdir_ignored` (`.vscode`)             | Still ignored — but now via `ALWAYS_IGNORED_DIRS`. Keep assertion; rename to `test_vscode_in_always_ignored_dirs`. |

No other test files reference dotfile-blanket behaviour (grep `'startswith.*\\.\\b\|hidden'` returns only the file above and unrelated matches).

### 4b. New tests in `tests/unit/sync/test_Vault__Ignore.py`

Add all 10 tests from source brief §3a. Two clarifications:

- **Test 6** (`test_gitignore_negation_includes_specific_dotfile`): the source brief example uses `.env*\n!.env.example`. Since `.env.example` is now in `ENV_TEMPLATE_ALLOWLIST`, this test passes via either path. Add a **second** assertion: `Vault__Ignore` (no gitignore) also returns `should_ignore_file('.env.example') is False`. That covers the template-allowlist case directly.
- **Test 8** (`test_explain_returns_schema_ignore_reason_for_ignored_file`): also add a `.env.staging` case asserting `reason_code='env_secret_glob'`, `matched_rule='.env*'` — covers the new path.

### 4c. New tests in `tests/unit/plugins/inspect/test_CLI__Inspect__Ignored.py`

All 8 tests from source brief §3b. No deltas.

### 4d. Test path conventions

- No `__init__.py` in `tests/` (CLAUDE.md project rule).
- Tests use **real `Vault__Ignore` instances and real tempdirs** — no mocks.
- Run with `pytest tests/unit/ -n auto` to keep the suite under ~2 min.

---

## 5. CLI registration — exact snippet to add

In `sgit_ai/plugins/inspect/CLI__Inspect.py`, between the `stats` and `diff-state` blocks (lines 35-37 area), add:

```python
# inspect ignored
ign_p = insp_sub.add_parser('ignored', help='Audit what is excluded from vault tracking')
ign_p.add_argument('--rules', action='store_true', default=False,
                   help='Print the curated ignore sets (no filesystem walk)')
ign_p.add_argument('--why',   default=None, metavar='PATH',
                   help='Explain whether and why <path> is ignored or tracked')
ign_p.add_argument('directory', nargs='?', default='.',
                   help='Vault directory (default: .)')
ign_p.set_defaults(func=self.vault.cmd_inspect_ignored)
```

Implement `cmd_inspect_ignored` in the same class that hosts `cmd_inspect_tree` (locate by `grep -rn 'cmd_inspect_tree' sgit_ai/`).

---

## 6. Deliverables (in order, one commit per item)

| # | Commit subject                                                              | Files touched                                                                              |
|---|-----------------------------------------------------------------------------|--------------------------------------------------------------------------------------------|
| 1 | `Drop blanket dotfile rule in Vault__Ignore + expand curated sets`          | `sgit_ai/core/Vault__Ignore.py`, `tests/unit/sync/test_Vault__Ignore.py` (flip + new)      |
| 2 | `Schema__Ignore_Reason + Vault__Ignore.explain()`                           | `sgit_ai/schemas/inspect/__init__.py`, `sgit_ai/schemas/inspect/Schema__Ignore_Reason.py`, `sgit_ai/core/Vault__Ignore.py`, tests |
| 3 | `Mirror dotfile-rule change in Vault__Bare, Vault__Merge, Vault__Sync__Push` | the 3 files in §3c; any existing tests touching them re-run green                          |
| 4 | `sgit inspect ignored (default, --rules, --why)`                            | `sgit_ai/plugins/inspect/CLI__Inspect.py`, new handler, `tests/unit/plugins/inspect/test_CLI__Inspect__Ignored.py` |
| 5 | `docs: release note for dotfile-tracking change`                            | CHANGELOG (or equivalent) + release-note paragraph as draft (see §7).                      |

Each commit must:
- pass `pytest tests/unit/ -n auto`
- keep KNOWN_VIOLATIONS unchanged
- be self-contained (no half-applied edits)

After commit 5, push to `claude/improve-cli-hidden-files-RcT0m` with `git push -u origin claude/improve-cli-hidden-files-RcT0m`. **Do not open a PR** — Opus reviews the diff first.

---

## 7. Release-note draft (Sonnet writes this)

Sonnet drafts a short paragraph for the release notes — one or two sentences, plus one example. Suggested skeleton:

> **Dotfile tracking** — `sgit` no longer blanket-ignores files and directories
> whose names start with `.`. Common-but-safe dotfiles (`.claude/`, `.github/`,
> `.editorconfig`, `.devcontainer/`) are now tracked by default; the curated
> `ALWAYS_IGNORED_DIRS` / `ALWAYS_IGNORED_FILES` sets still exclude IDE/build
> caches and known-secret files (`.env*` except `.env.example` and similar
> templates, `id_rsa`, `.netrc`, …). Run `sgit inspect ignored` to audit
> what's currently excluded and `sgit inspect ignored --why <path>` to
> understand any individual decision.

Place it in whatever changelog/release-notes file the repo uses (`grep -rn 'CHANGELOG\|RELEASE' --include='*.md' .` — let Sonnet locate). If no such file exists, **stop and ask** rather than creating one.

---

## 8. Verification checklist (must pass before pushing)

Adopt source brief §6 verbatim, plus:

- [ ] `.env.staging` is ignored via `env_secret_glob`; `.env.example` is tracked.
- [ ] `sgit inspect ignored --why .env.staging` reports `reason_code='env_secret_glob'`, `matched_rule='.env*'`.
- [ ] `Schema__Ignore_Reason` round-trips (`from_json(obj.json()).json() == obj.json()`).
- [ ] `Vault__Sync__Push.py:506` no longer contains `not d.startswith('.')`.
- [ ] `Vault__Branch_Switch.py` is untouched.
- [ ] Release-note draft committed.
- [ ] Branch pushed; no PR opened.

---

## 9. Out of scope (carry forward to a future brief)

Same as source brief §5, plus:
- Generic glob support for `ALWAYS_IGNORED_FILES` beyond the `.env*` special case.
- A `Safe_Str__Ignore_Reason_Code` enum-style Safe_Str — keep `Safe_Str` for v1; promote later if a third caller appears.
- `.sgignore` file support.
- A default `.gitignore` template on `sgit init`.
