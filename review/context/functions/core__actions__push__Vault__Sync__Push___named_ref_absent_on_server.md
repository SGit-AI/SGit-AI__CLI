## `_named_ref_absent_on_server` in sgit_ai/core/actions/push/Vault__Sync__Push.py (L901-L914)

**Purpose:** True **only** when the server itself says the named ref does not exist (`not_found` → ABSENT). Unknown (offline, per-file error, omitted from the reply) is False, so the compare-and-swap against what this clone last saw is kept (docstring L902-L904; review d3b8eef S10). The True answer is what turns the ref write into a plain `write` (`push` L202-L203).

**Inputs & Assumptions:** `vault_id`, `named_ref_id`. Server read: `batch_read([fid], failures=...)`.

**Outputs & Effects:**
```python
# L908-L914
try: found = self.api.batch_read(str(vault_id), [fid], failures=failures) or {}
except Exception: return False
failure = failures.get(fid)
return (fid in found and not found[fid] and failure is not None and failure.classification == Enum__Fetch_Failure_Class.ABSENT)
```
- **Establishes:** three conditions must all hold: the server **mentioned** the id (`fid in found` — the live `_batch_read_chunk` only adds keys for ids in the reply), with no data, and classified ABSENT (`status in ('not_found','404')`, Vault__API.py:L222-L223). A TRANSIENT/FORBIDDEN per-file status → False (test `tests/security/test_Security__Fixed__Index_Overwrite.py::test_S10__a_per_file_read_error_never_turns_the_ref_write_into_a_blind_write`, `Flaky_Ref_API` returns TRANSIENT).
- **Assumes:** the host's `not_found` is honest. A host that answers `not_found` for a ref it holds gets a plain write of the ref (overwriting whatever it holds) — the same host could also just serve any ref it likes, so the gain is only against the CAS. `nothing found` beyond the server's word (TM-R33 covers the honest race; the hostile-host version is TM-R01/A1 territory).
- With the in-memory double, `batch_read` always answers every id (ABSENT when missing, Vault__API__In_Memory.py:L90-L104).

**Cross-Function Dependencies:** callee `Vault__API.batch_read` → `_batch_read_chunk` → `_classify_per_file_status`. Caller: `push` L202 (only when `not first_push and lease is None`).

**Open Questions:** none.
