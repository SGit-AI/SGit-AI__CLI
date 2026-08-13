# Brief — Drop blanket dotfile exclusion + add `inspect ignored` command

**Date:** 2026-05-07
**Audience:** SGit Dev Agent (after the v0.14.x vault-ops sprint, before visualisation)
**Scheduling:** ships as the last item in the v0.14.x brief pack. Estimated effort: ~½ day.
**Author:** Villager orchestrator (Opus)

---

## 1. Why this exists

Today, `sgit_ai/core/Vault__Ignore.py:42,48` unconditionally excludes any file or directory whose name starts with `.` from being tracked. This silently drops `.claude/`, `.github/`, `.devcontainer/`, `.editorconfig`, `.dockerignore`, and similar files that users almost always want tracked. The blanket rule is a bug masquerading as a feature — it's stricter than git's default and not user-overridable through `.gitignore`.

The fix: drop the blanket rule, rely on a curated `ALWAYS_IGNORED_DIRS` + new `ALWAYS_IGNORED_FILES` for the genuinely-toxic names, and let users opt out via `.gitignore` for everything else. Plus a new `sgit inspect ignored` command so users can audit what's being excluded and why.

---

## 2. Code changes

### 2a. `Vault__Ignore.py` — drop the blanket rule, expand the curated sets

Current state (lines 5–16, 38–50):

```python
ALWAYS_IGNORED_DIRS = {'.sg_vault', '.git', 'node_modules', '__pycache__',
                       '.venv', '.tox', '.nox', '.eggs', '.mypy_cache',
                       '.pytest_cache', '.ruff_cache'}

def should_ignore_dir(self, rel_dir: str) -> bool:
    dir_name = rel_dir.rsplit('/', 1)[-1] if '/' in rel_dir else rel_dir
    if dir_name in ALWAYS_IGNORED_DIRS:
        return True
    if dir_name.startswith('.'):                  # ← DROP this branch
        return True
    return self._matches(rel_dir, is_dir=True)

def should_ignore_file(self, rel_path: str) -> bool:
    filename = rel_path.rsplit('/', 1)[-1] if '/' in rel_path else rel_path
    if filename.startswith('.'):                   # ← REPLACE with explicit set
        return True
    return self._matches(rel_path, is_dir=False)
```

New state:

```python
ALWAYS_IGNORED_DIRS = {
    '.sg_vault'    ,           # vault internal metadata
    '.git'         ,           # git internals
    'node_modules' ,           # npm packages
    '__pycache__'  ,           # Python bytecode cache
    '.venv'        ,           # Python virtual environments
    '.tox'         ,           # tox test runner
    '.nox'         ,           # nox test runner
    '.eggs'        ,           # setuptools build
    '.mypy_cache'  ,           # mypy type checker
    '.pytest_cache',           # pytest cache
    '.ruff_cache'  ,           # ruff linter cache
    '.idea'        ,           # JetBrains IDE workspace
    '.vscode'      ,           # VS Code workspace settings
    '.cache'       ,           # generic build/tooling cache
    '.parcel-cache',           # Parcel bundler cache
    '.next'        ,           # Next.js build output
    '.nuxt'        ,           # Nuxt.js build output
    '.terraform'   ,           # Terraform local state cache
    '.svelte-kit'  ,           # SvelteKit build output
    '.turbo'       ,           # Turbo cache
    '.DS_Store'    ,           # macOS Finder metadata (also a file; included here for safety)
    '.AppleDouble' ,           # macOS metadata
}

ALWAYS_IGNORED_FILES = {
    '.env'              ,      # environment file with secrets
    '.env.local'        ,      # environment file with secrets
    '.env.production'   ,      # environment file with secrets
    '.env.development'  ,      # environment file with secrets
    '.netrc'            ,      # FTP/HTTP credentials
    '.pgpass'           ,      # PostgreSQL credentials
    '.git-credentials'  ,      # git credentials file
    'id_rsa'            ,      # SSH private key
    'id_ed25519'        ,      # SSH private key
    'id_ecdsa'          ,      # SSH private key
    'id_dsa'            ,      # SSH private key
    '.npmrc'            ,      # may contain auth tokens
    '.pypirc'           ,      # PyPI credentials
}

# .env.example / .env.sample / .env.template are NOT in the set —
# templates without secrets should be tracked.

def should_ignore_dir(self, rel_dir: str) -> bool:
    dir_name = rel_dir.rsplit('/', 1)[-1] if '/' in rel_dir else rel_dir
    if dir_name in ALWAYS_IGNORED_DIRS:
        return True
    return self._matches(rel_dir, is_dir=True)

def should_ignore_file(self, rel_path: str) -> bool:
    filename = rel_path.rsplit('/', 1)[-1] if '/' in rel_path else rel_path
    if filename in ALWAYS_IGNORED_FILES:
        return True
    return self._matches(rel_path, is_dir=False)
```

`fnmatch` glob support for `ALWAYS_IGNORED_FILES`? Not for v1 — exact-name matches only. If we need globs later (e.g. `*.pem`, `*.key`) those can go in default `.gitignore` patterns rather than the hardcoded set.

### 2b. Mirror the same change in three other files

Each location duplicates the `startswith('.')` blanket logic. Fix all four places consistently:

- `sgit_ai/core/Vault__Bare.py:109,111` — drop the `not d.startswith('.')` and `if filename.startswith('.')` checks. Continue to special-case `.sg_vault` (the vault's own metadata dir must always be excluded from its own walks).
- `sgit_ai/core/actions/merge/Vault__Merge.py:108,119` — drop both `not d.startswith('.')` checks. Keep the `d != '.sg_vault'` filter.
- `sgit_ai/core/Vault__Sync__Base.py:160` — keep this one. It's the empty-dir-cleanup path that skips removing dot-prefixed dirs after deletions; not related to what's tracked. Leave alone.

After these four edits, ALL ignore decisions flow through `Vault__Ignore.should_ignore_*`.

### 2c. New CLI command: `sgit inspect ignored`

Add to `sgit_ai/plugins/inspect/CLI__Inspect.py`. Three modes:

```
sgit inspect ignored [<directory>]                # default: list ignored paths in <dir>
sgit inspect ignored --rules                      # print the curated sets (no walk)
sgit inspect ignored --why <path>                 # explain why <path> is ignored (or report 'tracked')
```

**Default mode (no flag):** walk the working directory, list every file that would be ignored, grouped by reason:

```
$ sgit inspect ignored
Ignored in /path/to/vault:

  Hardcoded dirs (ALWAYS_IGNORED_DIRS):
    .git/                                    — git internals
    .venv/                                   — Python virtual environments
    node_modules/                            — npm packages

  Hardcoded files (ALWAYS_IGNORED_FILES):
    .env                                     — environment file with secrets
    config/.netrc                            — FTP/HTTP credentials

  .gitignore patterns:
    dist/                                    — matched by 'dist/'
    *.log                                    — 14 files matched (build.log, app.log, ...)
    secrets/keys.pem                         — matched by 'secrets/'

Total: 1,247 files ignored, 38 tracked.
```

The output should be a real audit — visible, scannable, parseable.

**`--rules` mode:** dump the two hardcoded sets and the gitignore patterns from `<dir>/.gitignore`. No filesystem walk. Useful when a user wonders "what counts as ignored without me checking?":

```
$ sgit inspect ignored --rules
Hardcoded directory exclusions (ALWAYS_IGNORED_DIRS):
  .sg_vault, .git, node_modules, __pycache__, .venv, .tox, .nox,
  .eggs, .mypy_cache, .pytest_cache, .ruff_cache, .idea, .vscode,
  .cache, .parcel-cache, .next, .nuxt, .terraform, .svelte-kit,
  .turbo, .DS_Store, .AppleDouble

Hardcoded file exclusions (ALWAYS_IGNORED_FILES):
  .env, .env.local, .env.production, .env.development,
  .netrc, .pgpass, .git-credentials, id_rsa, id_ed25519,
  id_ecdsa, id_dsa, .npmrc, .pypirc

.gitignore patterns (from /path/to/vault/.gitignore):
  dist/                  (directory only)
  *.log                  (basename glob)
  secrets/               (directory only)
  !secrets/.gitkeep      (negated)

42 lines, 27 effective patterns.
```

**`--why <path>` mode:** ask about a specific path. Outputs one of:

```
$ sgit inspect ignored --why .claude/agent.md
.claude/agent.md is TRACKED.

$ sgit inspect ignored --why .env
.env is IGNORED — matched by ALWAYS_IGNORED_FILES (environment file with secrets).

$ sgit inspect ignored --why dist/main.js
dist/main.js is IGNORED — parent directory 'dist/' matched by .gitignore pattern 'dist/'.
```

This is the killer feature for debugging "why isn't sgit picking up this file?" — turn a confused user into one who can act in three seconds.

### 2d. CLI handler `cmd_inspect_ignored` in `CLI__Inspect.py`

Pure logic; no prompts, no destructive ops. Wraps `Vault__Ignore` with a small introspection helper class — propose a new `Vault__Ignore.explain(rel_path)` method that returns a structured `Schema__Ignore_Reason` (Type_Safe round-trip enforced):

```python
class Schema__Ignore_Reason(Type_Safe):
    rel_path     : Safe_Str__File_Path = None
    is_ignored   : bool                = False
    reason_code  : Safe_Str            = None    # 'always_ignored_dir' | 'always_ignored_file' | 'gitignore_pattern' | 'tracked'
    matched_rule : Safe_Str            = None    # the specific dir name / file name / pattern
    description  : Safe_Str            = None    # human-readable reason text
```

The `--why` mode dumps one of these; the default-mode walk uses the same schema internally to group output by `reason_code`.

---

## 3. Tests

In `tests/unit/core/test_Vault__Ignore.py` (extend existing) and `tests/unit/plugins/inspect/test_CLI__Inspect__Ignored.py` (new).

### 3a. Vault__Ignore semantics

1. `test_dotfile_not_in_always_ignored_files_is_tracked` — `.claude/notes.md` is tracked; `.editorconfig` is tracked; `.github/workflows/ci.yml` is tracked.
2. `test_dotdir_not_in_always_ignored_dirs_is_tracked` — `.claude/` is walked; `.devcontainer/` is walked.
3. `test_always_ignored_dirs_excluded` — every entry in the set is excluded; spot-check `.idea`, `.vscode`, `.next`.
4. `test_always_ignored_files_excluded` — every entry in the set is excluded; spot-check `.env`, `id_rsa`, `.netrc`.
5. `test_gitignore_pattern_overrides_default_track` — `.gitignore` containing `.claude/` excludes `.claude/`; without the pattern, it's tracked.
6. `test_gitignore_negation_includes_specific_dotfile` — `.gitignore` with `.env*\n!.env.example` ignores `.env` (also still hardcoded), but `.env.example` is tracked.
7. `test_explain_returns_schema_ignore_reason_for_tracked_file` — `Vault__Ignore.explain('foo.py')` returns `is_ignored=False`, `reason_code='tracked'`.
8. `test_explain_returns_schema_ignore_reason_for_ignored_file` — `.explain('.env')` returns `is_ignored=True`, `reason_code='always_ignored_file'`, `matched_rule='.env'`.
9. `test_explain_round_trip` — `Schema__Ignore_Reason` survives `from_json(obj.json()).json() == obj.json()`.
10. `test_no_blanket_dotfile_exclusion` — explicit regression test: a `.fooBar` file (not in any hardcoded set, not matched by any default `.gitignore`) is tracked.

### 3b. CLI inspect ignored

1. `test_inspect_ignored_default_lists_all_excluded_paths` — set up a vault with `.git/`, `.venv/`, `.env`, `dist/`, and a tracked `.claude/notes.md`; run the command; assert all four ignored items appear, the tracked one doesn't.
2. `test_inspect_ignored_groups_by_reason_code` — output has separate sections for ALWAYS_IGNORED_DIRS, ALWAYS_IGNORED_FILES, and gitignore patterns.
3. `test_inspect_ignored_rules_prints_sets` — `--rules` flag outputs both sets verbatim.
4. `test_inspect_ignored_rules_prints_gitignore_patterns` — `--rules` includes the parsed gitignore.
5. `test_inspect_ignored_why_tracked_file` — `--why path/to/foo.py` (tracked) outputs `"is TRACKED"`.
6. `test_inspect_ignored_why_ignored_by_set` — `--why .env` outputs the `always_ignored_file` reason.
7. `test_inspect_ignored_why_ignored_by_pattern` — `--why dist/foo.js` (under a gitignored dir) outputs the gitignore pattern reason.
8. `test_inspect_ignored_why_with_nonexistent_path` — `--why some/nonexistent/file` outputs a clear "no such file" rather than crashing.

### 3c. Integration with existing tests

There are existing tests that rely on dotfile-blanket-exclusion behaviour. Find and update them. Likely candidates (run `grep -rn 'startswith.*\\.\\b\|hidden' tests/`):

- `tests/unit/core/test_Vault__Ignore.py` — the existing tests for the blanket rule will need their assertions inverted.
- Any test asserting that `.foo` is excluded from a commit/scan should switch to either: (a) using a `.gitignore` to assert the file IS excluded, or (b) asserting it's tracked.

Expect ~5-10 tests to need updating. Small.

---

## 4. CLI registration

In `sgit_ai/plugins/inspect/CLI__Inspect.py`, add the `ignored` subparser to whatever pattern the inspect namespace already uses. Mirror the existing `inspect tree` / `inspect object` registration style.

---

## 5. Out of scope

- **Glob support in `ALWAYS_IGNORED_FILES`** — exact-name matches only. Globs (`*.pem`, `*.key`) belong in default `.gitignore` patterns.
- **Default `.gitignore` template on `sgit init`** — could be a future feature; skip for now. The hardcoded sets cover the most dangerous names.
- **`.sgignore`** — separate sgit-specific ignore file. Defer.
- **Migration warnings** — no real users yet (Dinis 2026-05-07); the change can land as a clean break. The brief intentionally does NOT include a "first-commit warning" mechanism. If the change ships and produces a noisy `sgit status` on existing vaults, the user runs `sgit inspect ignored` to audit and adds patterns to `.gitignore` as needed.

---

## 6. Verification checklist

When done:

- All ~18 new tests pass.
- `sgit inspect ignored` works in three modes against a real vault.
- Existing tests updated; full suite green (~3,275+ tests).
- KNOWN_VIOLATIONS unchanged (still 7).
- `Schema__Ignore_Reason` round-trips.
- A test vault with `.claude/notes.md` and `.editorconfig` produces a commit that includes both files.
- A test vault with `.env` produces a commit that does NOT include `.env`, AND `sgit inspect ignored --why .env` correctly identifies the reason.

Estimated effort: ~½ day total (Vault__Ignore + Vault__Bare + Vault__Merge edits ~1.5h, schema + explain method ~1h, CLI handler ~1h, tests ~1.5h).
