# `explain` and `_explain_dir_rule` in sgit_ai/core/Vault__Ignore.py

## `explain` (L188-L254)

**Purpose:** `sgit vault ignore explain`: a `Schema__Ignore_Reason` saying whether and why a path is ignored. Report-only; must agree with `should_ignore_file`/`should_ignore_dir`.

**Order (L193-L251):** `is_protected` → `always_ignored_dir`/structural (L193-L199); for a dir: `_explain_dir_rule`, overridden to not-ignored when `rel_path in tracked_dirs` (L201-L210); for a file: tracked (L212-L217) → `ALWAYS_IGNORED_FILES` (L218-L223) → `.env*` (L224-L229) → **ancestor dir rules unconditionally** (L230-L242) → `.gitignore` (L243-L249) → not ignored (L251-L254).

**Where it differs from `should_ignore_file`:** (1) the ancestor check here is not gated on `self.tracked_dirs` and runs **before** the `.gitignore` match, whereas `should_ignore_file` runs `.gitignore` first (L137) and ancestors only when `tracked_dirs` is non-empty (L144). For an untracked file under an ignored directory with no tracked set loaded, `explain` says "parent directory ignored" and `should_ignore_file` says False — but the walk would have pruned that directory, so the file never reaches `should_ignore_file`; the verdict differs only on direct calls (tests, `CLI__Vault` L2373 which loads the tracked set first). (2) `explain` does not apply tracked-wins to a file under a grandfathered dir — same as `should_ignore_file` (comment L230-L232). Recorded as a divergence in *reason ordering*, not in outcome on the walk path.

Both branches of the `Vault__Path_Guard` import are local (L189-L190) — report-only code path.

## `_explain_dir_rule` (L256-L283)
Rules alone, no tracked exemption: `ALWAYS_IGNORED_DIRS` → prefix (`.sg_vault_old_*`) → `.gitignore` (`_matches(is_dir=True)` + `_find_matching_pattern` for the rule text) → not ignored. Mirrors `_dir_matches_ignore_rule` (L118-L124) with reasons attached; the two are maintained separately (`nothing found` that ties them together beyond `tests/unit/sync/test_Vault__Ignore.py::test_explain_*`).

**Callers:** `CLI__Vault` L2373, L2401, L2415. Tests: `tests/unit/sync/test_Vault__Ignore.py::test_explain_*`, `tests/unit/schemas/test_Schema__Ignore_Reason.py`.
