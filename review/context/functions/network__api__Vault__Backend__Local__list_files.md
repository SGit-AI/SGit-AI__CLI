## `list_files` in sgit_ai/network/api/Vault__Backend__Local.py (L34-L50)

**Purpose:** Recursive listing of the folder (or `root/prefix`), returning sorted `/`-separated paths relative to `root`.

**Inputs & Assumptions:** `prefix` joined onto root (L37) — same containment note as `read`. `os.walk` follows no symlinks by default (`followlinks=False`), but files that *are* symlinks are listed as files.

**Outputs & Effects:** sorted list; `[]` when the directory does not exist (L41-L42). Mirrors `Vault__API__Static.list_files`'s local branch (Vault__API__Static.py:L205-L211).

**Cross-Function Dependencies:** no callers in `sgit_ai/`. Tests: `test_Vault__Backend__Local.py` L37-L60, L93.

**Open Questions:** none.
