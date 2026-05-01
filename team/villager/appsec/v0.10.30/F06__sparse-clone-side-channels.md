# F06 — Sparse Clone, On-Demand Fetch, Cat: Server-Side Access Patterns

**Severity:** LOW (residual)
**Class:** Server-side access-pattern side channel
**Disposition:** ACCEPTED-RISK / DOCUMENT
**Files:** `sgit_ai/sync/Vault__Sync.py` (`clone_read_only`, `sparse_fetch`,
`sparse_cat`), `sgit_ai/sync/Vault__Fetch.py`, CLI command handlers in
`sgit_ai/cli/CLI__Vault.py:1267-1330`

## 1. What the Server Sees

When a sparse clone is followed by selective `fetch` / `cat`:

1. Initial clone downloads:
   - `bare/indexes/{branch_index_file_id}` (1 GET)
   - `bare/refs/{ref-pid-muw-...}` (per branch, 1 GET each)
   - `bare/keys/{public_key_id}` (per branch)
   - `bare/data/{commit_id}` (walk commit chain)
   - `bare/data/{tree_id}` for every tree in the chain
2. Per `fetch <path>`: 1 GET on `bare/data/{blob_id}` for the path's blob.
3. Per `cat <path>`: same as fetch but does not save to working dir (still
   one GET).

**The server sees a sequence of `(vault_id, blob_id)` tuples** with timestamps
and source IPs. Combined with the deterministic tree IDs (F01), this lets
the server build a partial map: "which subtrees of vault X did this client
visit, in which order".

## 2. What the Server Cannot See

- **Plaintext file paths.** The blob_id is `obj-cas-imm-{sha256(ciphertext)[:12]}`,
  which is content-addressable but the content is encrypted with random IV
  (blobs use `encrypt`, not `encrypt_deterministic`). So blob_id leaks no
  content equality. Verified at `Vault__Crypto.encrypt` line 195-200.
- **Plaintext blob content.** AES-GCM, intact.
- **Read key or write key.** No key sent.

## 3. Cross-Vault Linkability

Because clone-mode persists `read_key_hex` in `clone_mode.json` (F07), if
the same client clones two vaults that share content (e.g., a fork), the
server sees:

- vault_A `bare/data/{blob_X}`
- vault_B `bare/data/{blob_Y}`

But blob_X != blob_Y because each vault encrypts the same plaintext with a
different `read_key`, producing different ciphertexts and hence different
blob_ids. **Cross-vault content overlap is NOT visible to the server.**

Within one vault, two identical files have one shared blob (CAS via
`compute_object_id`). The server sees one `bare/data/{blob_X}` GET,
serves it once. It learns "two paths in vault_A point to the same content"
ONLY because the **tree** entries reference the same blob_id. Reading the
encrypted tree gives the server this view.

## 4. Plaintext in Progress Output

`CLI__Vault.cmd_fetch` (line 1276) prints:

```
label = 'all files' if (fetch_all or not path) else f"'{path}'"
```

→ `Fetching '{path}'…`.

That `path` is the user-supplied plaintext path. **It goes to local stdout
only.** Not transmitted. **Acceptable** — the user typed it.

`cmd_cat` (line 1325) prints `sync.sparse_cat(...)` content — plaintext file
body to stdout. Intentional (`cat` semantics). User's responsibility to not
pipe to a wider audience.

## 5. Debug Log Hygiene

`API__Transfer` and `Vault__API` have a `debug_log` parameter. If enabled,
it logs HTTP method + URL + body length. URL contains `{vault_id}/{file_id}`
— both opaque hashes. **No plaintext path or filename appears in the URL.**
Debug log is safe.

**One concern:** `sgit_ai/cli/CLI__Debug_Log.py` may log request bodies (need
to verify). For uploads (push), the body is encrypted ciphertext — fine.
For DELETE on `delete_vault`, the body is `{'vault_id': '...'}` — the
vault_id is server-known. **No leak.**

## 6. Timing-Channel Surface

Each `fetch <path>` is one GET over the wire. The server can time the
client's arrival pattern, but not derive plaintext from timing. Request
sizes are encrypted blob sizes, which the client already revealed by
asking for `bare/data/{blob_id}` whose ciphertext length is on the server.
**No new timing leak**.

## 7. Recommendation

- Document in the CLI man page: "Sparse fetch reveals to the server which
  encrypted blobs you access. If access patterns are sensitive (e.g.,
  reading a specific file at a specific time signals something), use a
  full clone instead."
- Consider a `--prefetch-decoy <N>` option that fetches N random blobs
  alongside the requested one. Not for v0.10.30 — escalate to Architect
  if this is a real product requirement.

## 8. Test Coverage

Existing tests `test_Vault__Sync__Clone.py`, `test_Vault__Fetch.py`,
`test_Vault__Sync__Multi_Clone.py` verify functional correctness of clone
and fetch. **No tests assert side-channel properties** (e.g., "the server
sees only the requested blob_id, not the path"). For an accepted-risk
finding this is okay; if the access pattern is later considered sensitive,
QA should add a `test_fetch_only_calls_one_blob_id` integration test.

## 9. Disposition

- **Document only.** No code change.
- **Optional product feature** (decoy prefetch) → Architect.
