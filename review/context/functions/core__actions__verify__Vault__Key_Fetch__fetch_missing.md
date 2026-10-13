## `fetch_missing` in sgit_ai/core/actions/verify/Vault__Key_Fetch.py (L27-L52)

**Purpose:** Brings a teammate's public-key file (`bare/keys/<id>`) into a clone that predates it, so that commits signed by that teammate stop classifying as `no-key`. It is the only code that writes into `bare/keys/` from server data.

**Inputs & Assumptions:**
- `c` (Vault__Components): `vault_id`, `read_key`, `key_manager`. Trust: trusted.
- `key_ids` (iterable): ids to fetch. Trust: **semi-trusted** — they come from a decrypted commit's `author_key_id` (`Vault__Signatures._key_for` L34) or from the decrypted index's branch entries (`branch_key_ids` L24-L25, called from `Step__Pull__Load_Branch_Info._refresh_index` L41 and `Vault__Sync.verify_signatures` L270).
- `self.api` (Vault__API | None): `None` means no fetch (L35).
- `self.tried` (list[Safe_Str__Key_Id]): per-instance memo so an id is asked for once per run (L31, L37).
- Implicit: the server's `bare/keys/<id>` files; the local `bare/keys/` directory.
- Precondition: none. The function never raises by contract (L29-L30).

**Outputs & Effects:**
- Returns the number of key files saved.
- **State write:** `bare/keys/<kid>` created with the server's exact ciphertext (L47-L50), via plain `open(..., 'wb')` — not `Vault__Verified_Write` (keys are not content-addressed, so there is nothing to verify by hash) and not `Vault__Secret_File` (the file is read-key ciphertext of a *public* key, world-readable is fine by design).
- Network: one `batch_read` (L39).

**Block-by-Block:**

```python
# L31-L37
tried  = {str(k) for k in self.tried}
wanted = sorted({str(k) for k in (key_ids or [])
                 if k and KEY_ID__REGEX.match(str(k)) and str(k) not in tried
                 and not c.key_manager.key_exists(str(k))})
if not wanted or self.api is None:
    return 0
self.tried.extend(Safe_Str__Key_Id(k) for k in wanted)
```
- **What:** Filter to well-formed (`^key-rnd-imm-[0-9a-f]{8,64}$`, `Safe_Str__Key_Id.py:L5`), not-yet-tried, not-yet-local ids.
- **Why here:** The regex is the path-safety gate for L47 (`_key_path(kid)` is an `os.path.join`); `key_exists` means an existing local key file is **never overwritten** by this function.
- **Assumes:** that a key file already on disk is the right one — a clone keeps the first `bare/keys/<id>` it ever saw. Nothing re-fetches or compares. (Which is consistent with ids being random and immutable, `generate_key_id` → `secrets.token_hex(8)`, `Vault__Key_Manager.py:L21-L22`.)
- **Establishes:** `wanted` ⊆ safe filenames; each will be asked for at most once per `Vault__Key_Fetch` instance.
- **Depended on by:** L39, L45.

```python
# L38-L41
try:
    blobs = self.api.batch_read(str(c.vault_id), [f'bare/keys/{k}' for k in wanted]) or {}
except Exception:
    return 0
```
- **What:** One batch read; any transport failure → 0 saved.
- **Assumes:** `Vault__API.batch_read` (L125-L165) returns `{file_id: bytes|None}`; it does not itself verify anything. A fetched key reaches disk only after L45.
- **Depended on by:** L43-L51.

```python
# L43-L51
for fid, blob in blobs.items():
    kid = str(fid).rsplit('/', 1)[-1]
    if not blob or kid not in wanted or not self._is_public_key(blob, c.read_key):
        continue
    path = c.key_manager._key_path(kid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(blob)
    saved += 1
```
- **What:** Save each returned blob that (a) names an id we asked for and (b) decrypts under the read key to `{"type": "public", "pem": "...PUBLIC KEY..."}`.
- **Why here:** `kid not in wanted` means the *server's* file_id (not ours) is what names the file, but it is accepted only if it equals one we requested — the host cannot steer the write to another name. `_is_public_key` runs **before** the write: verify-then-accept for key files.
- **Assumes:** AES-GCM under the read key is the authenticity check (`_is_public_key` L55-L59 → `crypto.decrypt`). This proves "a read-key holder wrote this key file", not "the vault owner did" (TM-R01; `tests/security/test_Security__Known_Gaps.py::test_TM_R01__signatures_required_stops_unsigned_but_not_self_signed`).
- **Establishes:** every file this function writes is read-key ciphertext of a public-key JSON.
- **Depended on by:** `_key_for` L35-L38 on the same run (the key is now `key_exists`).

**Cross-Function Dependencies:**
- Callee `_is_public_key` (internal, L54-L59): `json.loads(decrypt(...))`, `type == 'public'`, `'PUBLIC KEY' in pem`; any exception → `False`. It does not try to *import* the PEM; a syntactically broken PEM that contains the marker is saved, and `load_public_key` then raises, which `_key_for` turns into `no-key`.
- Callee `Vault__API.batch_read` (external-source-available, L125-L165): chunks of 50, parallel; per-file 502 fallbacks (L167-L265, not read in full here).
- Callers: `_key_for` (one id, on demand); `Step__Pull__Load_Branch_Info._refresh_index` L39-L41 (every branch's key, after the index refresh, inside a `try` that only re-raises `Vault__Client_Too_Old_Error`); `Vault__Sync.verify_signatures` L269-L270.
- Shared state: `bare/keys/` with `Vault__Branch_Manager.create_clone_branch` (L62, writes this clone's own public key) and `Step__Clone__…` bulk fetch (clone downloads keys for every branch; module docstring L2-L3 of Key_Fetch).
- Invariant coupling: the "key file this clone lacks is fetched" rule closes the gap `test_a_clone_older_than_a_teammate_accepts_the_teammates_signed_commits` (`tests/unit/review/test_Signature_Policy_And_Rewind__Fixes.py`) tests.

**Open Questions:**
- unclear; `_key_path` is a private method of `Vault__Key_Manager` called from another class (L47). Not a correctness issue; noted because `store_public_key` (L24-L31) is the public writer and does the same `open(...,'wb')`.
