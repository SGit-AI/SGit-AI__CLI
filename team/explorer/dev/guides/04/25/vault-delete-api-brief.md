# API Brief: Vault Delete Endpoint

**Requested by:** CLI team  
**Date:** 25 April 2026  
**Priority:** Medium — needed for vault lifecycle management

---

## What We Need

A single API endpoint that deletes all server-side files belonging to a vault.
The CLI will call this from a new `sgit vault delete` command.

---

## Endpoint Specification

```
DELETE /api/vault/{vault_id}
```

### Request Headers

```
x-sgraph-vault-write-key: <write_key>
Content-Type: application/json
```

### Request Body

```json
{
  "vault_id": "<vault_id>"
}
```

The `vault_id` is required in **both** the URL path and the request body.
The duplication is intentional — it forces the caller to explicitly name what
they are deleting and prevents accidental deletion from a mis-wired request.

### Success Response — `200 OK`

```json
{
  "status": "deleted",
  "vault_id": "<vault_id>",
  "files_deleted": 142
}
```

### Error Responses

| Status | Condition |
|--------|-----------|
| `401 Unauthorized` | `write_key` missing or invalid for this vault |
| `404 Not Found` | vault does not exist on the server |
| `409 Conflict` | vault_id in body does not match vault_id in URL |
| `500 Internal Server Error` | partial deletion — see notes below |

---

## Authentication & Authorisation

### How `write_key` works

Every vault has a master key (`vault_key`) stored only in the local
`.sg_vault/local/vault_key` file. The `write_key` is a deterministic
derivative of `vault_key` (HKDF-SHA256). The server validates the
`write_key` against the key material stored in `bare/keys/` for that vault.

This is the same mechanism used by `PUT /api/vault/write/{vault_id}` and
`POST /api/vault/batch/{vault_id}` — no new auth mechanism is needed.

### Why cross-vault deletion is impossible

1. **URL-scoped storage:** All vault files are stored under a path prefixed
   by `vault_id` (e.g. `{vault_id}/bare/data/…`). A request to
   `DELETE /api/vault/vault-A` can only ever touch files under `vault-A/`.

2. **write_key is vault-specific:** The `write_key` is derived from the vault's
   own master key. A valid `write_key` for vault-A will fail validation on
   vault-B because the key material in vault-B's `bare/keys/` was derived from
   a different master key. There is no shared or cross-vault key.

3. **Double confirmation:** Requiring `vault_id` in both the URL and the body
   means both the routing layer and the application layer independently verify
   the target vault before any deletion begins.

---

## What Gets Deleted

Everything under the vault's storage prefix:

```
{vault_id}/bare/data/       ← all encrypted blobs, commits, trees
{vault_id}/bare/refs/       ← all branch refs
{vault_id}/bare/keys/       ← vault key material
{vault_id}/bare/indexes/    ← branch indexes
```

This is a **hard delete** — no soft delete, no recovery. The caller is
responsible for ensuring the local working copy (`.sg_vault/`) is also
removed if desired (the CLI will offer a `--local` flag for this).

---

## Idempotency

The endpoint should be idempotent: if the vault has already been deleted,
return `200` (or `404`) rather than an error. This allows safe retries if
the client receives a network error after the server completed the deletion.

---

## Partial Deletion Handling

If the server deletes some files and then fails (e.g. S3 error mid-walk),
return `500` with a body indicating how many files were deleted before the
failure. The CLI will surface this to the user and suggest retrying. Since
files are deleted from storage, retrying is safe (already-deleted files are
a no-op).

---

## CLI Command (for reference)

The CLI team will implement `sgit vault delete` once this endpoint exists.
Expected behaviour:

```bash
# Delete vault from server only (keep local working copy)
sgit vault delete <vault-key>

# Delete from server AND wipe local directory
sgit vault delete <vault-key> --local

# Skip confirmation prompt (for scripting)
sgit vault delete <vault-key> --yes
```

The `vault-key` argument is the same token used by `sgit clone` — it encodes
both the `vault_id` and the `write_key`, so the CLI can authenticate without
any extra login step.

The CLI will print a confirmation prompt before deleting:

```
About to permanently delete vault <vault_id> from the server.
This cannot be undone. Type the vault ID to confirm: _
```

---

## Security Checklist for Implementation

- [ ] Validate `write_key` header before touching any files
- [ ] Verify body `vault_id` matches URL `vault_id` (return 409 if not)
- [ ] Scope all file operations to `{vault_id}/` prefix — never accept
      a `vault_id` containing `/`, `..`, or other path traversal characters
- [ ] Log the deletion event (vault_id, timestamp, IP, files_deleted)
- [ ] Rate-limit: at most N delete requests per write_key per hour
- [ ] No admin bypass — even internal tooling must supply a valid write_key

---

## Out of Scope for This Request

- Soft delete / trash / recovery — not needed now
- Deleting individual branches within a vault — separate feature
- Audit trail retention after deletion — separate feature
