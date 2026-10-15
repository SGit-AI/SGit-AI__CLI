## `should_ignore_file` in sgit_ai/core/Vault__Ignore.py (L126-L149)

```python
# L127-L149
if Vault__Path_Guard().is_protected(rel_path):      # structural: never tracked-won (A2)
    return True
if rel_path in self.tracked_paths:                   # tracked-wins
    return False
filename = rel_path.rsplit('/', 1)[-1] if '/' in rel_path else rel_path
if filename in ALWAYS_IGNORED_FILES:  return True
if self._is_env_secret(filename):     return True
if self._matches(rel_path, is_dir=False): return True
if self.tracked_dirs and '/' in rel_path:
    parts = rel_path.split('/')
    for i in range(1, len(parts)):
        if self._dir_matches_ignore_rule('/'.join(parts[:i])):
            return True
return False
```

**Purpose:** Whether a working-copy file is excluded from every scan (status, commit, push, diff, stash, revert, switch, bare). Order: structural refusal → tracked-wins → always-ignored names → `.env*` secret glob → `.gitignore` → ancestor-directory rules (only when a tracked set is loaded, because a walk descends into an ignored directory only when it holds tracked files — comment L139-L143).

**Inputs & Assumptions:**
- `rel_path` (str, `/`-separated, relative to the vault root): from `os.walk` (`Vault__Sync__Base.py:L434`, `Vault__Bare.py:L121`, `Vault__Revert.py:L149`, `Vault__Branch_Switch.py:L438,L462`, `Vault__Diff.py:L827`, `Vault__Stash.py:L222`). Trust: filesystem-derived names.
- Implicit: `self.patterns` (from `.gitignore`), `self.tracked_paths`/`tracked_dirs` (from the vault head via `load_tracked_from_vault`). Type_Safe gives each a fresh empty collection per instance (annotations L72-L74 with no default, per CLAUDE.md rule 4).
- Precondition: callers that scan a vault **must** have loaded the tracked set, or tracked-wins is off and a newly-added rule records tracked files as deletions (class docstring L62-L70, decision 17). Established by every scan site checked: `Vault__Sync__Base` L411, `Vault__Revert` L139, `Vault__Branch_Switch` L451, `Vault__Diff` L816, `Vault__Stash` L209, `Vault__Merge` L109/L127, `Vault__Sync__Push` L971 — **except** `Vault__Branch_Switch._checkout_committed` L429 (`Vault__Ignore().load_gitignore(directory)` with no `load_tracked_from_vault`) and `Vault__Bare._list_working_copy_files` L110 (same). Both use the result to decide what to **delete** (Switch L441-L444: files not in `flat_map`; Bare L53-L56: every listed file). For Switch, a file that is ignored-by-rule but tracked in the head is skipped by the walk and therefore *not deleted* — conservative. For Bare (`clean`), likewise not deleted. So the missing tracked set makes those two sites delete less, not more. Recorded; not a finding.

**Outputs & Effects:** Pure bool. `is_protected` runs first so a structural path is ignored even when `tracked_paths` holds it (A2; `tests/unit/sync/test_Vault__Ignore__Tracked_Wins.py::Test_A2__Structural_Not_Written_On_Checkout`).

**Block-by-Block:**
- L128-L129: `is_protected` — `.git/`, `.sg_vault*/`, 8.3 and stream spellings, backup zips. Never grandfathered.
- L130-L131: tracked-wins — a tracked `.env`, `id_rsa`, `.github/x` stays tracked (`tests/security/test_Security__Known_Gaps.py::test_TM_R09__a_tracked_env_file_stays_tracked`; TM-R09 accepted).
- L133-L136: `ALWAYS_IGNORED_FILES` (L34-L47) exact basenames; `_is_env_secret` (L183-L186): any basename starting with `.env` except the three templates (L51) — so `.envrc` is also ignored (`tests/unit/sync/test_Vault__Ignore.py::test_envrc_and_similar_startswith_env_are_ignored`).
- L137-L138: `.gitignore` patterns, last match wins (`_matches`).
- L144-L148: ancestor rule check, gated on `self.tracked_dirs` being non-empty. When the tracked set is loaded but **empty** (fresh vault, or `Vault__Head_Paths.flat` failed — it returns `{}` on any exception, L70-L71), this block is skipped; that is fine because `should_ignore_dir` then prunes ignored dirs before their files are seen (L112-L116).

**Cross-Function Dependencies:**
- Callees: `Vault__Path_Guard.is_protected`, `_is_env_secret`, `_matches`, `_dir_matches_ignore_rule`.
- Callers: listed above (8 walk sites).
- Coupling with `Vault__Head_Paths.flat` (L20-L71): it fails open to `{}` on any exception; the A6 review note (L30-L40) argues the scan fails loudly in the same conditions so tracked-wins cannot be silently lost — pinned by `tests/unit/sync/test_Vault__Ignore__Tracked_Wins.py::Test_A6__Fail_Open_Coupling::test_head_unreadable_makes_scan_fail_loud`. One case where they diverge: `Vault__Head_Paths.flat` runs `_init_components` itself (L45) and swallows `Vault__Client_Too_Old_Error`? No — it swallows **all** exceptions including that one; the scan's own `_init_components` would raise it first. Consistent.

**Open Questions:**
- The two scan sites without a tracked set (Switch L429, Bare L110) — confirmed delete-less, but whether that was intended is for the authors.
