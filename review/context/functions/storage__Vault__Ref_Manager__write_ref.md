## `write_ref` in sgit_ai/storage/Vault__Ref_Manager.py (L16-L32)

```python
# L17-L32
path = self._ref_path(ref_id)
os.makedirs(os.path.dirname(path), exist_ok=True)
try:
    old = self.read_ref(ref_id, read_key)
except Exception:
    old = None
from sgit_ai.storage.Vault__Reflog import Vault__Reflog
Vault__Reflog(vault_path=self.vault_path).append(ref_id, old, commit_id)
if read_key and self.crypto:
    data       = json.dumps({'commit_id': commit_id}).encode()
    ciphertext = self.crypto.encrypt(read_key, data)
    with open(path, 'wb') as f: f.write(ciphertext)
else:
    with open(path, 'w') as f: f.write(commit_id)
```

**Purpose:** Move a local ref (`bare/refs/<ref_id>`) to `commit_id`, recording old→new in the per-clone reflog first. Every local head move — commit, pull merge, clone branch creation, push's named-ref update, revert/reset, migration — goes through here.

**Inputs & Assumptions:**
- `ref_id` (str): joined into the path unvalidated (L78-L79). Sources: `str(meta.head_ref_id)` from the branch index (`Safe_Str__Ref_Id`, strict `^ref-pid-(muw|snw)-[0-9a-f]{12}$` → no separators possible once it has passed the schema), or `'ref-pid-…' + derive_ref_file_id(...)` (HMAC hex). All callers checked pass one of these two forms (`Vault__Sync.py:L110-L111`, `Vault__Sync__Commit.py:L172,L324`, `Vault__Sync__Pull.py:L63`, `Vault__Sync__Push.py:L366`, `Vault__Branch_Switch.py:L91,L107,L223,L235`, `Vault__Ignore__Apply.py:L82`, `Step__Pull__*`, `Step__Clone__Create_Clone_Branch.py:L35`, `Step__Move__Write_Sentinel_Commits.py:L117`, `Migration__Tree_IV_Determinism.py:L364`). The adversary fixture writes `'ref-pid-snw-' + 'a'*12` (`tests/security/test_Security__Known_Gaps.py:L110-L111`).
- `commit_id` (str): the new head. Trust: from local commit creation, or from a server ref the caller already decrypted (pull/switch). **Not shape-checked here**: `json.dumps({'commit_id': commit_id})` accepts any string, including `''` (`Vault__Branch_Switch.py:L223,L235` pass `source_commit_id or ''`).
- `read_key` (bytes or None) and `self.crypto`: when either is falsy the ref is written **plaintext** (L30-L32). No caller in `sgit_ai/` passes a falsy key knowingly (all pass `read_key`/`c.read_key`); the plaintext branch is reachable if `crypto` is left unset — `Vault__Sync__Pull.py:L274` and `Vault__Sync__Status.py:L271` construct `Vault__Ref_Manager()` with no `vault_path`/`crypto`, but only to satisfy `Vault__Commit`'s constructor (they never call `write_ref` on it). `nothing found` that forbids the plaintext branch; `tests/unit/objects/test_Vault__Ref_Manager.py::test_write_and_read_ref_plaintext` exercises it deliberately.
- Implicit: `vault_path` (sanitised `Safe_Str__Vault_Path`, see `storage__Vault__Object_Store__object_path.md`).

**Outputs & Effects:**
- Overwrites `bare/refs/<ref_id>` (plain `open('wb')`, follows a symlink at the path — A6).
- Appends to `.sg_vault/local/reflog.jsonl` via `Vault__Reflog.append` (L31-L46 of that file: never raises; skipped when `old == new`; file capped at 1000 entries by `_trim` L64-L69 which rewrites via `Vault__Secret_File`).
- No compare-and-swap, no rewind check here — those are the callers' job (`Vault__Sync__Push` L201 `get_ref_file_hash` for the server CAS; `Vault__Ref_Guard`/`last_remote_head` for rewinds, not in slice).
- The ref ciphertext carries no associated data binding it to `ref_id` (AES-GCM with `None` AAD, `Vault__Crypto.encrypt` L298) — TM-R03, `tests/security/test_Security__Known_Gaps.py::test_TM_R03__ref_ciphertext_is_not_bound_to_its_ref_id`.

**Block-by-Block:**
- L19-L22: read the old value for the reflog; any failure (missing, undecryptable) → `None`. A ref whose ciphertext the key cannot open is thus overwritten silently here; the *callers* decide whether an unreadable server ref is an error (`Vault__Unreadable_Ref_Error` exists in `Vault__Errors.py:L112`, raised elsewhere).
- L24: reflog before the write — if the write then fails, the reflog claims a move that did not happen; `append` never raises so a reflog failure never blocks the write.
- L26-L29: encrypt `{"commit_id": …}`; fresh random IV per write (`encrypt` L295-L296).

**Cross-Function Dependencies:**
- Callees: `_ref_path` L78, `read_ref` L34 (internal), `Vault__Reflog.append` (external-source-available, read), `Vault__Crypto.encrypt` L294-L299 (read).
- Callers: listed above (14 sites).
- Shared state: `bare/refs/<ref_id>` with `read_ref`, `get_ref_file_hash`, `ref_exists`, `list_refs`, and the two unguarded writers `Vault__Sync._fetch_branch_for_switch` L207-L210 (writes the server's raw bytes so push's CAS matches, L209 comment — bypassing the reflog) and `Vault__Verified_Write.save` (for `bare/refs/<x>` ids during clone/pull — also bypassing the reflog).

**Open Questions:**
- `commit_id` shape is established by no one in this function; see `read_ref` for the consequence on the read side.
- Whether any production path reaches the plaintext branch (L30-L32).
