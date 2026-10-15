## `exists` in sgit_ai/network/api/Vault__Backend.py (L45-L50)

**Purpose:** `read` succeeds → True; `FileNotFoundError`/`RuntimeError` → False. Any other exception (e.g. `URLError` from a dead host through `Vault__Backend__API`) propagates.

**Inputs & Assumptions:** `file_id`. Reads the whole object to test existence (no HEAD).

**Cross-Function Dependencies:** overridden by `Vault__Backend__Local.exists` (L52-L54 of that file: `os.path.isfile`). Tests: `test_Vault__Backend.py` L37-L55. No callers in `sgit_ai/`.

**Open Questions:** none.
