# 07 — API Layer

**Author:** Developer
**Audience:** Developers, Backend Engineers

## Server Protocol

The CLI communicates with the SG/Send server via a simple HTTP REST API.
The server is a **key-value store** — it stores `{vault_id}/{file_id} → bytes`.

Default server: `https://dev.send.sgraph.ai`

## Authentication

All write operations require two credentials passed as HTTP headers:

| Header                       | Purpose                           |
|------------------------------|-----------------------------------|
| `x-sgraph-access-token`     | User's access token (identity)    |
| `x-sgraph-vault-write-key`  | Vault write key (authorization)   |

Read operations (GET) require no authentication.

## Endpoints

### Write a File

```
PUT /api/vault/write/{vault_id}/{file_id}

Headers:
  Content-Type: application/octet-stream
  x-sgraph-access-token: {token}
  x-sgraph-vault-write-key: {write_key}

Body: raw bytes (ciphertext)

Response: {"status": "ok"}
```

### Read a File

```
GET /api/vault/read/{vault_id}/{file_id}

Response: raw bytes (ciphertext)
```

### Delete a File

```
DELETE /api/vault/delete/{vault_id}/{file_id}

Headers:
  x-sgraph-access-token: {token}
  x-sgraph-vault-write-key: {write_key}

Response: {"status": "ok"}
```

### List Files

```
GET /api/vault/list/{vault_id}?prefix={prefix}

Response: {"files": ["bare/data/obj-cas-imm-...", ...]}
```

### Batch Operations

```
POST /api/vault/batch/{vault_id}

Headers:
  Content-Type: application/json
  x-sgraph-access-token: {token}
  x-sgraph-vault-write-key: {write_key}

Body:
{
  "operations": [
    {
      "op": "write",
      "file_id": "bare/data/obj-cas-imm-abc123",
      "data": "base64-encoded-ciphertext"
    },
    {
      "op": "write-if-match",
      "file_id": "bare/refs/ref-pid-muw-def456",
      "data": "base64-encoded-new-ref",
      "match": "sha256-of-current-content"
    },
    {
      "op": "read",
      "file_id": "bare/data/obj-cas-imm-789abc"
    }
  ]
}

Response:
{
  "status": "ok",
  "results": [
    {"file_id": "bare/data/obj-cas-imm-abc123", "status": "ok"},
    {"file_id": "bare/refs/ref-pid-muw-def456", "status": "ok"},
    {"file_id": "bare/data/obj-cas-imm-789abc", "status": "ok", "data": "base64..."}
  ]
}
```

**Batch operation types:**
- `write` — Unconditional write
- `write-if-match` — CAS write (reject if current content hash doesn't match)
- `delete` — Delete a file
- `read` — Read a file (included in batch results)

**Atomicity:** If any `write-if-match` fails, the entire batch is rejected.

## File ID Naming Convention

All file IDs sent to the server follow the vault's internal path structure:

```
bare/data/{object_id}           # CAS objects (blobs, trees, commits)
bare/refs/{ref_id}              # Mutable HEAD pointers
bare/keys/{key_id}              # Public signing keys
bare/indexes/{index_id}         # Branch index
bare/branches/{branch_id}       # (reserved)
bare/pending/pack-{uuid}/{...}  # Change packs
```

## API Client Implementation

```
sg_send_cli/api/Vault__API.py

class Vault__API(Type_Safe):
    base_url     : Safe_Str__Base_URL
    access_token : Safe_Str__Access_Token
    debug_log    : object

    Methods:
      setup()                                    # set default base_url
      write(vault_id, file_id, write_key, payload) -> dict
      read(vault_id, file_id) -> bytes
      delete(vault_id, file_id, write_key) -> dict
      batch(vault_id, write_key, operations) -> dict
      batch_read(vault_id, file_ids) -> dict     # convenience: batch of reads
      list_files(vault_id, prefix) -> list[str]
```

Uses Python's `urllib.request` (no external HTTP library dependency).

## Push Batch Strategy

When pushing, the CLI builds batch operations in this order:

```
  1. New blob objects           (WRITE bare/data/obj-cas-imm-...)
  2. New tree objects           (WRITE bare/data/obj-cas-imm-...)
  3. New commit objects         (WRITE bare/data/obj-cas-imm-...)
  4. Named branch ref update   (WRITE bare/refs/ref-pid-muw-...)
```

If batch fails, falls back to individual uploads.

## Error Handling

API errors are wrapped in `RuntimeError` with detailed diagnostics:

```
API Error: HTTP 403 Forbidden
  Request:  PUT https://dev.send.sgraph.ai/api/vault/write/abc123/bare/data/obj-cas-imm-...
  Headers:  {"x-sgraph-access-token": "abcd1234...(64 chars)", ...}
  Payload:  4096 bytes
  Response: {"error": "invalid write key"}
```

Sensitive headers (tokens, keys) are masked in error output.

## Backend Abstraction

The API layer supports multiple backends for testing:

```
Vault__Backend (abstract)
  |-- Vault__Backend__API        # real HTTP calls to server
  |-- Vault__Backend__Local      # local filesystem (unit tests)
  +-- Vault__API__In_Memory      # in-memory dict (unit tests)
```

## Known API Gaps

1. **No retry logic** — API calls fail immediately on 5xx errors. No exponential backoff.
2. **No pagination** — `list_files` returns all files. May fail on large vaults.
3. **write-if-match on server** — Server supports it but the CLI doesn't always use CAS
   for ref updates (optimistic locking is partial).
