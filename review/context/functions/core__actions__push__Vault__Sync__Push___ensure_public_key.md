## `_ensure_public_key` in sgit_ai/core/actions/push/Vault__Sync__Push.py (L916-L935)

**Purpose:** Non-first pushes: if the server lacks `bare/keys/<this clone's public_key_id>`, upload it with a plain `write`, so teammates do not see this clone's commits as `no-key`. Best effort: every exception is swallowed (L934-L935).

**Inputs & Assumptions:** `c.key_manager` (local `bare/keys/`), `clone_meta.public_key_id` (from the branch index), `vault_id`, `write_key`.

**Outputs & Effects:**
- Server read: `batch_read([fid])`; if `found.get(fid)` is truthy → return (L925-L927). Any bytes count as "present" — no check that they are *this* key; the server could hold a different key under that id (a read-key holder can mint one, TM-R01): `nothing found`.
- Server write: `api.batch(vault_id, write_key, [write bare/keys/<kid>])` with the local file's bytes (L928-L932) — **directly via `api.batch`**, not `Vault__Batch`, so the reply is not passed through `_checked`; a non-ok reply is ignored (L934). The file is whatever `key_manager._key_path(kid)` holds; assumed public: `nothing found`.

**Cross-Function Dependencies:** callees `Vault__Key_Manager.key_exists/_key_path` (L69-L79), `Vault__API.batch_read/batch`. Caller: `push` L142.

**Open Questions:** none.
