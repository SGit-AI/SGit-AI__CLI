# Architecture Decisions — Vault v2 (2026-03-14)

Decisions made by project lead to unblock Phase 0+ implementation.

## 1. PKI Reserved Fields in Commit Schema

**Decision:** Yes, include PKI reserved fields (`branch_id`, `signature`, `author_key_id`, `author_signature`, `attestations`) in `Schema__Object_Commit` from the start.

**Rationale:** Avoids a schema migration later. Fields are nullable so they don't break Mode 1 (no PKI).

## 2. Mode 1 Unsigned Commits

**Decision:** Unsigned commits are allowed. If the user has no PKI setup, commits are created without signatures.

**Rationale:** "No unsigned commits" applies when PKI is configured. Mode 1 (vault-key-only) users should not be blocked from using the tool.

## 3. Tree Entry Encryption (`name_enc`/`size_enc`)

**Decision:** No double encryption. The `_enc` suffixes are naming conventions only. The entire tree object is already encrypted when stored. Within the decrypted tree JSON, field names like `name_enc` simply indicate that these values are sensitive, but they are not individually encrypted a second time.

**Rationale:** Double encryption adds complexity without meaningful security benefit since the tree object is already AES-GCM encrypted.

## 4. Batch Endpoint (Gap #6)

**Decision:** Assume the backend will support the batch endpoint. Build the client now.

**Rationale:** Client-side implementation can proceed independently. Backend team will implement the endpoint.

## 5. `write-if-match` for First Push

**Decision:** For the initial push (when remote ref does not exist), use a simple write (no `match` parameter). Optimistic locking via `write-if-match` only applies to subsequent pushes where a prior ref value exists.

**Rationale:** Simplifies implementation. Create-if-absent semantics can be added later if race conditions become a real issue.
