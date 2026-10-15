## `read_ref` in sgit_ai/storage/Vault__Ref_Manager.py (L34-L45)

```python
# L35-L45
path = self._ref_path(ref_id)
if not os.path.isfile(path):
    return None
if read_key and self.crypto:
    with open(path, 'rb') as f: ciphertext = f.read()
    data = json.loads(self.crypto.decrypt(read_key, ciphertext))
    return data.get('commit_id')
else:
    with open(path, 'r') as f: return f.read().strip()
```

**Purpose:** The local head of a ref: `None` when absent, else the `commit_id` field of the decrypted JSON (or the plaintext file in keyless mode).

**Inputs & Assumptions:**
- `ref_id`: as in `write_ref` (schema- or HMAC-shaped at every caller checked).
- `read_key`/`crypto`: keyless mode reads plaintext (L43-L45).
- The file's bytes: authentic under the read key (AES-GCM tag, `decrypt` L301-L305 raises `InvalidTag` on tampering) but **chosen by any read-key holder** and **not bound to this `ref_id`** (TM-R03). `data.get('commit_id')` is returned **without shape validation**: it may be `None` (key absent), a non-string (int, list, dict), or any string. Callers then use it as an object id (`Vault__Object_Store.load(commit_id)` → `os.path.join(vault_path, 'bare/data', commit_id)`) or compare it. **nothing found** in this slice that checks `isinstance(..., str)` or the `obj-cas-imm-` shape between `read_ref` and `load`; whether `Vault__Commit.load_commit` or `Vault__Ref_Guard` does is outside the slice (not read).
- `json.loads` of a decrypted non-JSON payload raises `JSONDecodeError`; a non-dict JSON (e.g. a list) makes `.get` raise `AttributeError`. Both propagate to callers; `write_ref` L19-L22 swallows them, `Vault__Head_Paths.flat` L70 swallows everything.

**Outputs & Effects:** Pure read. Returns str/None/other.

**Cross-Function Dependencies:**
- Callees `_ref_path`, `Vault__Crypto.decrypt`.
- Callers (sample of the ~25): `write_ref` L19; `Vault__Head_Paths.flat` L55 (`if not head: return {}` — a falsy non-string passes as "no head"); `Vault__Revert` L111; `Vault__Bare._get_head_tree_id` L102-L105 (`object_store.load(commit_id)` directly); `Vault__Sync__Sparse` L222 (`or ''`); `Vault__Sync.fetch`/`_fetch_branch_for_switch` L190, L201; `Vault__Publish` L63 (`str(c.ref_file_id)`); `Vault__Restore` L165; `Vault__Inspector` L603; `CLI__Cache` L58; migration L116, L178, L362.
- Tests: `tests/unit/objects/test_Vault__Ref_Manager.py` (`test_write_and_read_ref_encrypted`, `test_read_ref_missing_returns_none`); `tests/security/test_Security__Known_Gaps.py::test_TM_R03__...`; `tests/unit/review/test_Review__eed8084.py::Test_F3__A_Server_Ref_That_Does_Not_Decrypt_Is_Reported_Everywhere`.

**Open Questions:**
- Where (if anywhere) the `commit_id` read here is validated against `Safe_Str__Object_Id` before reaching `Vault__Object_Store.object_path`. Candidates not read: `Vault__Commit.load_commit`, `Vault__Ref_Guard`, `Vault__Incoming_Check`.
