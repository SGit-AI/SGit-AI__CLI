## `_check_lease` in sgit_ai/core/actions/push/Vault__Sync__Push.py (L937-L959)

**Purpose:** `--force-with-lease`: the server's named head must be the leased commit (the one given, else the last remote head this clone **accepted**); if so, return the server's current ref bytes (base64) as the compare-and-swap match so that a push landing between this check and the write is still not clobbered. `push` then sets `force=False` (L206) so the ref op is `write-if-match`.

**Inputs & Assumptions:**
- `lease` (str): `''` → baseline from `remote_heads.json` (`_read_remote_baseline`, which status never moves — review B2); a commit id or unique prefix otherwise (resolved locally by `obj_store.resolve_id`, Vault__Object_Store.py:L99-L119; a `ValueError` for an ambiguous prefix is swallowed L951-L954 and the raw text compared).
- Server read: `api.read(vault_id, f'bare/refs/{named_ref_id}')` (L949) — **not** wrapped in try/except: a 404 (`RuntimeError` from `_api_error`) or a dead host (`URLError`) propagates as that error, not as a lease error.

**Outputs & Effects:**
- Raises `Vault__Push_Lease_Error` when no expectation can be formed (L946-L948) or when the server's head ≠ expected (L955-L958: "someone pushed since. Nothing was written").
- Returns `b64(raw)` or `None` when `raw` is empty (an empty 2xx body → `None` → plain write in `build_push_operations`, since `force` is False and `expected_ref_hash` is None).

**Block-by-Block:**
```python
# L945-L950
expected = str(lease or '') or (self._read_remote_baseline(directory, storage, named_ref_id) or '')
if not expected: raise Vault__Push_Lease_Error(...)
raw     = self.api.read(str(vault_id), f'bare/refs/{named_ref_id}')
current = Vault__Sync__Status(...)._parse_ref(raw, read_key) if raw else ''
```
- **Assumes:** `_parse_ref` (Vault__Sync__Status.py:L247-L253) returns `''` for undecryptable bytes → `current=''` → mismatch → lease error (never a blind write over an unreadable ref; `_require_readable_server_ref` at `push` L86 already refused that case).

```python
# L955-L959
if (current or '') != expected: raise Vault__Push_Lease_Error(...)
return base64.b64encode(raw).decode('ascii') if raw else None
```
- **Establishes:** the ref write will be CAS against the exact bytes just read. A host that serves the leased commit's ciphertext (replayed, TM-R03) passes the check; the CAS then matches those bytes. `nothing found` beyond decrypt-equals-expected.
- Tests: `tests/unit/review/test_Tags_Reflog_Lease.py::Test_Force_With_Lease` (refuses when a teammate pushed and writes nothing; allows a deliberate rewind when the remote is where we saw it; explicit commit must match); `tests/security/test_Security__Fixed__Baselines.py::test_B2__status_does_not_satisfy_the_lease`.

**Cross-Function Dependencies:** callees `Vault__Sync__Base._read_remote_baseline` L224-L225 (may raise `Vault__Ref_Rewind_Error` on a damaged record), `Vault__API.read`, `Vault__Sync__Status._parse_ref`, `Vault__Object_Store.resolve_id`. Caller: `push` L205 (`lease is not None and not first_push`). CLI: `--force-with-lease` sets `force=True` and passes `lease` (CLI__Vault.py:L1205-L1210), so the pull at L165 is skipped and this check is the only freshness test before the write.

**Open Questions:**
- unclear; `--force-with-lease` on a **first push** (`first_push=True`) skips this function (L204) and keeps `force=True` → plain write; whether that is intended (a first push has nothing to lease against) — observation.
