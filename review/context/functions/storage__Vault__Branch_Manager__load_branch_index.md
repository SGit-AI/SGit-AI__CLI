## `load_branch_index` in sgit_ai/storage/Vault__Branch_Manager.py (L88-L97)

```python
# L89-L97
path = self.storage.index_path(directory, index_id)
with open(path, 'rb') as f: ciphertext = f.read()
data  = json.loads(self.crypto.decrypt(read_key, ciphertext))
index = Vault__Index_Reader().parse(data)
Vault__Format().check_client(index)
return index
```

**Purpose:** Read, decrypt, parse and gate the local branch index. Every command that touches branches goes through here (≈60 call sites), including `_init_components` → `_apply_vault_format` (L357) on every operation.

**Inputs & Assumptions:**
- `index_id`: HMAC-derived at every caller (`c.branch_index_file_id`, `keys['branch_index_file_id']`).
- The file bytes: written by `save_branch_index` or by `Vault__Verified_Write.save` from the host (clone/pull: `bare/indexes/<id>` is not content-addressed, so VERIFIED unchecked — containment only). Authenticity comes from AES-GCM under the read key at L92 (`decrypt` L301-L305 raises `cryptography.exceptions.InvalidTag` on tamper). Freshness is **not** established here: a host-replayed older index decrypts fine (TM-R29; `Vault__Format` docstring L76-L77 "fails open").
- `FileNotFoundError` propagates when the index is absent (callers check `if not index_id` first, which is about the *id*, not the file).

**Outputs & Effects:** Returns the schema; raises `Vault__Client_Too_Old_Error` when `min_client` parses and exceeds the installed version (`Vault__Format.check_client` L83-L96: unparseable `min_client` → no minimum; unparseable client version → never refused). Side effects: `parse` may append to `Vault__Index_Reader.WARNED` indirectly? No — `parse` does not warn; only `warn_new`/`warn_skipped` do, and they are called by `Step__Clone__Download_Index` L106.

**Block-by-Block:**
- L92: `json.loads(decrypt(...))` — decrypted bytes trusted as UTF-8 JSON; `UnicodeDecodeError`/`JSONDecodeError` propagate.
- L94: `parse` — strict on branches/format/features/min_client, lenient (carry) on tags; drops unknown top-level keys silently (see `parse`).
- L96: the client gate. Its claim is "refuse by name when the vault needs a newer client"; because `min_client` follows whatever copy is on disk, a host that serves an older index removes the gate for existing clones too (TM-R29).

**Cross-Function Dependencies:** Callees `Vault__Storage.index_path`, `Vault__Crypto.decrypt`, `Vault__Index_Reader.parse`, `Vault__Format.check_client` (all read). Callers: see grep list in the index (every action module). `_apply_vault_format` L356-L361 catches everything except `Vault__Client_Too_Old_Error` and proceeds at format 1 — so a corrupt index makes `_init_components` succeed and the *next* explicit `load_branch_index` in the action raise.

**Open Questions:**
- Freshness/pinning of `format`: the threat model says "a clone never lowers the format number it has seen" — that pin is not in this function or in `Vault__Format` as read; it must live in the merge code (`Vault__Index_Sync`, not read).
