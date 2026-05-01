# F05 — `delete_on_remote` Authorisation & Idempotency

**Severity:** LOW (CLI side); MEDIUM if real server fails to enforce auth
**Class:** Authorisation / authentication
**Disposition:** ACCEPTED with one TEST GAP escalated to QA
**Files:** `sgit_ai/sync/Vault__Sync.py:1724-1734`,
`sgit_ai/api/Vault__API.py:200-211`,
`sgit_ai/api/Vault__API__In_Memory.py:85-90`,
`sgit_ai/cli/CLI__Vault.py:956-985`

## 1. The Wire Contract

```python
# Vault__API.py:207-211
url     = f'{self.base_url}/api/vault/destroy/{vault_id}'
headers = {'Content-Type': 'application/json',
           'x-sgraph-vault-write-key': write_key}
return self._request('DELETE', url, headers, body)
```

Authentication via the `x-sgraph-vault-write-key` header. Authorisation is the
server's responsibility.

## 2. CLI Pre-flight Guards (Verified OK)

`CLI__Vault.cmd_delete_on_remote` (line 956-985):
1. `c = sync._init_components(directory)` — loads write_key from local config.
2. `if not c.write_key: raise RuntimeError('read-only clone')` — line 964.
3. If not `--yes`: prompt for vault_id confirmation; abort on mismatch.
4. Calls `sync.delete_on_remote(directory)` which re-checks `c.write_key`
   (line 1732-1733).

The double-check is correct defensive coding.

## 3. Confirmation Prompt — Echoes Vault ID

`cmd_delete_on_remote` (lines 967-972) prints the vault_id and asks the user
to type it back. The user's typed input is read via `sys.stdin.readline()`
which **does** echo to the terminal. The vault_id itself is not secret (it
appears in S3 paths and server logs by design), so echoing is fine.

`answer != c.vault_id` aborts. **Verified safe**: a typo cannot accidentally
delete.

## 4. Idempotency

- `Vault__API__In_Memory.delete_vault` (line 85-90) returns
  `files_deleted=0` if no files matched. Tested in
  `Test_Vault__API__In_Memory__Delete_Vault.test_delete_vault_idempotent`.
- The CLI prints "was already absent from the server" when `files_deleted==0`.
- No exception on second call. **Idempotent ✓**.

## 5. Server-Side Ciphertext Destruction — UNVERIFIED

The Villager AppSec role assumes the server is hostile. **Whether
`delete_vault` truly destroys ciphertexts on disk** depends on the server
implementation (out of repo scope).

Realistic worry:
- Server stores objects in S3. `delete_vault` lists prefix and DELETEs each
  key. DELETE is a soft-delete on versioned buckets — older versions
  recoverable for the bucket's retention period.
- Server has separate logs / audit trail — these may persist ciphertexts
  indefinitely.
- CDN edge caches may retain copies for the cache TTL.

**This is the threat-model boundary.** Document explicitly: "delete_on_remote
issues a destruction request; clients cannot verify destruction. Any party
who captured a ciphertext snapshot before deletion can still attempt to
decrypt with the (also-captured) key."

## 6. Test Coverage

`tests/unit/sync/test_Vault__Sync__Delete_Rekey.py:13-99` covers:
- Returns deleted status ✓
- Clears server files ✓
- Other vaults survive ✓
- Idempotent ✓
- Read-only clone raises ✓
- Local intact after delete ✓

**Gaps:**
- **No test asserts the `x-sgraph-vault-write-key` header is sent**. The
  In-Memory implementation accepts any string and ignores it. Mutation M10
  (drop the auth header in `Vault__API.delete_vault`) would NOT be detected
  by current unit tests because they only run against the In-Memory API.
  **Escalate to QA Phase 3** for a real-API integration test.
- No test verifies that `delete_vault` is called with the write_key from the
  local config (vs. a stale cached value).
- No test covers the "wrong write_key" rejection path — In-Memory does not
  enforce, so this can only be tested against a real server.

## 7. Probe-Token Guard?

The plan asked: "does delete-on-remote require a simple-token guard like
probe?" → **No, and that's correct**. Probe is a public lookup; delete is
authenticated. Different threat models. No guard needed.

## 8. Disposition

- **Verified-safe at CLI layer.**
- **Test gap (M10):** auth header presence — escalate to QA + DevOps for
  real-server integration test.
- **Document:** server-side destruction is best-effort, not cryptographically
  enforced.
- **No code change needed.**
