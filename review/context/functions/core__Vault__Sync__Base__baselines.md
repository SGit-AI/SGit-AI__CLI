## `_accepted_head` in sgit_ai/core/Vault__Sync__Base.py (L227-L237)

**Purpose:** "The head this clone last accepted for a named branch ('' if never)." The `last_known` of every rewind check. A record that is unreadable, or missing once it existed, refuses (L1) unless `accept_rewind`.

**Inputs & Assumptions:** `directory`, `storage`, `accept_rewind` (bool), `ref_id` (named ref id).

**Outputs & Effects:** str; raises `Vault__Ref_Rewind_Error` (from `_remote_baselines`) unless `accept_rewind`, in which case `''` (L234-L237) — so `--accept-rewind` also means "trust the server's current head when my own record is damaged" (test `test_accept_rewind_rebuilds_the_record`).

**Cross-Function Dependencies:** callee `_read_remote_baseline` (L224-L225) → `_remote_baselines`. Callers: `Step__Pull__Fetch_Remote_Ref.execute` L78-L84, `Step__Pull__RO__Load_Named_Head.execute` L74-L80.

---

## `_remote_baselines` in sgit_ai/core/Vault__Sync__Base.py (L161-L191)

**Purpose:** `{named_ref_id: commit_id}` from `local/remote_heads.json`, with the legacy single `last_remote_head` migrated for pre-per-branch clones.

**Block-by-Block:**
- L169-L181: if the file exists, parse; `not a dict` or any exception ⇒ `Vault__Ref_Rewind_Error` ("unreadable … run: sgit pull --accept-rewind"). Entries with empty key or value are dropped (L176).
- L182-L186: file absent but `config.json` says `remote_heads_file: true` ⇒ raise ("missing"). The marker is set by `_mark_remote_heads_file` (L208-L222) the first time the per-branch file is written.
- L187-L191: no file, no marker ⇒ the legacy `last_remote_head` (written at clone time, `Step__Clone__Setup_Local_Config` L30) attributed to the tracked branch (`_tracked_named_ref_id` L263-L271, which swallows everything to `''`).

**Assumes:** `config.json` and `remote_heads.json` are this user's files (0600 via `Vault__Secret_File`). A local attacker (A6) who can edit them can set any baseline — outside the model (same user).

**Tests:** `test_Security__Fixed__Baselines.py::test_a_damaged_record_refuses_the_rewind` (both `corrupt` and `deleted`), `::test_a_clone_from_before_per_branch_baselines_keeps_its_baseline`, `::test_the_legacy_field_is_cleared_once_the_record_exists`.

---

## `_write_remote_baseline` in sgit_ai/core/Vault__Sync__Base.py (L239-L254)

**Purpose:** Record `ref_id → commit_id` as accepted. Called only after an accept (pull `_accept`, RO checkout, switch's never-fetched-branch fetch, push).

**Block-by-Block:**
- L243-L246: load the current record; a `Vault__Ref_Rewind_Error` (damaged) is swallowed and the record **starts afresh** — the comment says this is reached only after an accepted head. The callers do guarantee that: `_accept` runs after `_guard_rewind` which itself ran `_accepted_head` (raising on damage unless `accept_rewind`), so by construction a damaged record reaches here only with `--accept-rewind`.
- L247-L249: unchanged and file exists ⇒ no write.
- L250-L254: set or pop, then `_save_remote_baselines` → `Vault__Secret_File.write` (0600, unique temp, fsync, rename; `sgit_ai/crypto/Vault__Secret_File.py:L14-L35`) and `_mark_remote_heads_file`.

**Assumes:** `ref_id` is a safe filename? — it is a JSON key, not a path; fine.

**Cross-Function Dependencies:** callers listed in `_accept` record. Test `test_no_fixed_tmp_name` (Baselines).

**Open Questions:** none.
