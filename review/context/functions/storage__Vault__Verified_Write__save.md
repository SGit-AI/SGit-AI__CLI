## `save` in sgit_ai/storage/Vault__Verified_Write.py (L72-L88)

```python
# L76-L88
if not self.is_store_path(file_id):
    return self.REFUSED
verdict = self.classify(file_id, data, read_key=read_key)
if verdict == self.REFUSED:
    return self.REFUSED
try:
    local_path = Vault__Path_Guard().safe_join(base_dir, file_id)
except Vault__Unsafe_Path_Error:
    return self.REFUSED
os.makedirs(os.path.dirname(local_path), exist_ok=True)
with open(local_path, 'wb') as f:
    f.write(data)
return verdict
```

**Purpose:** The only sanctioned way host-served bytes reach `.sg_vault/bare`: refuse unless (a) the file id names a leaf of the bare store, (b) a content-addressed id hashes to its bytes, (c) the join stays inside `base_dir`. Threat model §5 "Content addressing + verify-before-write" — "0.21: now on every download path".

**Inputs & Assumptions:**
- `base_dir` (str): the `.sg_vault` directory (`sg_dir`). Trust: trusted. Callers: `Clone__Workspace.save_file` L63, `Vault__Sync__Pull._fetch_missing_objects._save` L281, `Vault__Sync__Sparse._save_verified` L229, `Vault__Sync__Scope` L71 (+ L120 writer), `Vault__Sync__Fsck._repair_object` L226, `Vault__Sync__Status` L269 (writer), `Vault__Publish__Bundles.extract_verified` L75, `Step__Move__Validate_Local._try_repair_missing` L183.
- `file_id` (str): **untrusted** — a host-returned key (`fid` from `api.batch_read(...).items()`: Scope L70-L71), a bundle zip member (`Publish__Bundles` L73-L75), or a client-built `f'bare/data/{oid}'` where `oid` came from a decrypted tree/commit (Pull L280-L282, Sparse L112, Fsck L223, Move L181).
- `data` (bytes): untrusted host bytes.
- `read_key`: accepted and ignored by `classify` (L43, L47-L49: "deliberately NO ... fallback").
- Implicit: `self.crypto` (lazily defaulted, L62-L63).

**Outputs & Effects:**
- Returns `VERIFIED` after writing, or `REFUSED` having written nothing (L77, L80, L84).
- Writes `local_path` with a plain `open(..., 'wb')` — overwrites whatever is there (no collision check as in `Vault__Object_Store.store`; for an id that verified, same-id means same-bytes at the id's width only up to the 48-bit/128-bit hash, TM-R07).
- Non-content-addressed ids (`bare/refs/x`, `bare/indexes/x`, `bare/keys/x`, `bare/branches/x`, `bare/pending/x`, `bare/cache/*/x`) are `VERIFIED` without any check (L60-L61) and written: for those, this function provides containment only, not integrity (threat model §4: "mutable files are not [self-verifying]").

**Block-by-Block:**

```python
# L76-L77  is_store_path
```
- **What:** Regex `^bare/(data|refs|indexes|keys|branches|pending)/[^/]+$ | ^bare/cache/(value|pointer)/[^/]+$` (L18-L19) then `not is_protected(fid)`.
- **Why here:** A host id like `local/vault_key`, `local/config.json` or `../x` must never reach disk (docstring L30-L33). First because it is the cheapest and the broadest.
- **Assumes:** `[^/]+` is the right leaf shape. It admits `.` and `..` as leaves (`bare/data/..`) — `safe_join` at L82 then rejects `..` (L137) and `.` resolves to the directory itself (`full == base_abs/bare/data`, allowed by L142; `open(dir,'wb')` would raise `IsADirectoryError` **uncaught**). It admits a leaf with a backslash (`bare/data/..\\x`): on POSIX that is one filename; `safe_join` L137 splits on `\\` too and rejects the `..`. It admits NUL bytes and other odd characters; `open` raises `ValueError` on NUL, uncaught.
- **Establishes:** `file_id` is a two- or three-level bare-store leaf.

```python
# L78-L80  classify
```
- **What:** For `obj-cas-imm-*` leaves, `crypto.object_id_matches(file_id, data or b'')`; otherwise `VERIFIED`.
- **Assumes:** `object_id_matches` (`Vault__Crypto.py:L200-L203`) compares `compute_object_id(ciphertext, n)` where `n` is the id's own hex length (12 or 32, `object_id_hex_len` L192-L198, else 0 → False). So `bare/data/obj-cas-imm-<13 hex>` is REFUSED (width 0), and an id whose hex is upper-case never matches (`hexdigest()` is lower-case) → REFUSED.
- **Establishes:** for content-addressed ids, `sha256(data)[:n] == id` — the host cannot substitute bytes (`tests/security/test_Security__Fixed__Host_Substitution.py`, `tests/unit/review/...`).

```python
# L81-L84  safe_join
```
- **What:** Containment (and the protected-name check again) on `base_dir + file_id`.
- **Why here:** After the regex, this is "belt and braces"; it is also where in-tree symlinks under `.sg_vault/bare` are refused (`has_link_component`).
- **Establishes:** `local_path` under `base_dir`, no link component at check time.

```python
# L85-L87  write
```
- **What:** `makedirs` + plain overwrite.
- **Assumes:** nothing swapped a link in between L82 and L86 (same TOCTOU shape as every `safe_join` caller; A6).

**Cross-Function Dependencies:**
- Callees: `is_store_path` L29 (internal), `classify` L43 (internal), `Vault__Path_Guard.safe_join` (internal to storage), `Vault__Crypto.object_id_matches` (external-source-available, read: L200-L203).
- Callers and how they treat `REFUSED`: Clone → recorded in `integrity_failures`, run continues (L64-L68); Pull → warning + `failures[fid]` (L283-L289); Sparse `_save_verified` → raises `Vault__Integrity_Error` (L229-L231); Scope → not counted (L71); Fsck → `False` (L226); Bundles → `refused` list (L77-L78); Move → not repaired (L183); Status → `writer` constructed at L269, use not read here.
- Download paths that do **not** use this function: `Vault__Sync__Base.fetch_tree_lazy` L624-L630 and L645-L654 write `os.path.join(sg_dir,'bare','data', tree_id|oid)` with a plain `open('wb')`, no verification, no `safe_join`; `oid = fid.replace('bare/data/', '')` (L649) takes the **host's** returned key. No caller of `fetch_tree_lazy` exists in `sgit_ai/` (grep), so the path is dead code in the package but present. `Vault__Key_Fetch.fetch` L47-L50 writes `bare/keys/<kid>` with `kid` regex-checked at L33 and `_is_public_key` (decrypts under read key) at L45 — no `safe_join`, containment comes from `KEY_ID__REGEX`. `Vault__Sync._fetch_branch_for_switch` L207-L210 writes `bare/refs/<ref_id>` where `ref_id = str(meta.head_ref_id)` (a `Safe_Str__Ref_Id`, strict regex) — no `safe_join`; the bytes are the server's raw ref, decrypted first at L193 (so they are authentic under the read key) and the signature policy ran at L204.
- Tests: `tests/security/test_Security__Fixed__Host_Substitution.py` (`test_fsck_repair_refuses_substituted_bytes`, `test_vault_move_auto_repair_never_launders_a_substitution`, `test_clone_refuses_a_head_with_a_substituted_blob`).

**Open Questions:**
- `bare/data/.` as a file id → `IsADirectoryError` out of `open` (L86), uncaught here; whether any caller's `try/except` covers it (Pull `_save` has none at L276-L290 in the part read).
- Whether `Vault__Sync__Status` (L269) ever writes through its `writer` or only verifies — not read past L285.
