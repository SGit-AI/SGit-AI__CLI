# 02 — Architecture

**Author:** Architect
**Audience:** Architects, Senior Developers

## Layer Architecture

The system has 5 layers with strict dependency direction (top → bottom only):

```
 Layer 5: CLI          sg_send_cli/cli/
 Layer 4: Sync         sg_send_cli/sync/
 Layer 3: Objects      sg_send_cli/objects/
 Layer 3: API          sg_send_cli/api/
 Layer 3: Crypto       sg_send_cli/crypto/
 Layer 3: PKI          sg_send_cli/pki/
 Layer 3: Secrets      sg_send_cli/secrets/
 Layer 2: Schemas      sg_send_cli/schemas/
 Layer 1: Safe Types   sg_send_cli/safe_types/
```

**Rule:** A module may only import from its own layer or below. Never upward.

## Dependency Graph (ASCII)

```
                    CLI__Main
                   /         \
             CLI__Vault    CLI__PKI
             /    |    \       |
            /     |     \      |
   CLI__Progress  |  CLI__Token_Store
         CLI__Credential_Store
                  |
            Vault__Sync  <-- orchestrator, the "brain"
           /  |   |   \   \
          /   |   |    \    \
 Vault__  Vault__ Vault__ Vault__  Vault__
 Merge    Fetch   Batch   Sub_Tree Branch_Manager
    \       |       |       |        /
     \      |       |       |       /
      +-----+-------+-------+-----+
      |                            |
 Vault__Object_Store    Vault__Ref_Manager
 Vault__Commit          Vault__Key_Manager
      |                      |
      +----------+-----------+
                 |
           Vault__Crypto    PKI__Crypto
                 |
      Schema__Object_Commit
      Schema__Object_Tree[_Entry]
      Schema__Branch_Meta
      Schema__Branch_Index
      ...16 more schemas...
                 |
      Safe_Str__Vault_Id
      Safe_Str__Object_Id
      Safe_Str__Branch_Id
      ...39 more safe types...
```

## Package Inventory

### Layer 1: Safe Types (`sg_send_cli/safe_types/`) — 44 types

All are subclasses of `Safe_Str`, `Safe_UInt`, or `Enum`:

| Category    | Count | Examples                                              |
|-------------|-------|-------------------------------------------------------|
| Enums       | 4     | Enum__Branch_Type, Enum__Sync_State, Enum__Batch_Op, Enum__Provenance_Mode |
| Safe_Str    | 35    | Safe_Str__Vault_Id, Safe_Str__Object_Id, Safe_Str__Branch_Id, Safe_Str__Encrypted_Value, ... |
| Safe_UInt   | 5     | Safe_UInt__File_Size, Safe_UInt__Timestamp, Safe_UInt__Vault_Version, ... |

Each Safe_Str has: `regex`, `max_length`, `allow_empty`, `trim_whitespace`.

### Layer 2: Schemas (`sg_send_cli/schemas/`) — 21 classes

| Schema                        | Purpose                                    |
|-------------------------------|--------------------------------------------|
| Schema__Object_Commit         | Git-like commit: tree_id, parents, msg_enc |
| Schema__Object_Tree           | Directory listing (entries array)           |
| Schema__Object_Tree_Entry     | File/folder entry (all _enc fields)        |
| Schema__Object_Ref            | HEAD pointer (encrypted commit_id)         |
| Schema__Branch_Meta           | Branch metadata (id, name, type, keys)     |
| Schema__Branch_Index          | List of all branches                       |
| Schema__Local_Config          | Per-clone local config (my_branch_id)      |
| Schema__Vault_Config          | Vault-level config                         |
| Schema__Vault_Meta            | Vault metadata (id, name, version)         |
| Schema__Vault_Index[_Entry]   | Legacy vault file index                    |
| Schema__Vault_Policy          | Access control policy (future)             |
| Schema__Remote_Config         | Remote server config                       |
| Schema__Transfer_File         | API transfer metadata                      |
| Schema__Batch_Request         | Batch API request envelope                 |
| Schema__Batch_Operation       | Individual batch operation                 |
| Schema__Change_Pack           | Pending change bundle                      |
| Schema__Tracking_State        | Sync tracking state                        |
| Schema__PKI_Key_Pair          | RSA/EC key pair                            |
| Schema__PKI_Public_Key        | Public key for contacts                    |
| Schema__Secret_Entry          | Encrypted secret in credential store       |

### Layer 3: Core Services

**Crypto (`sg_send_cli/crypto/`)** — 3 classes:
- `Vault__Crypto` — AES-256-GCM encrypt/decrypt, PBKDF2, HKDF, content hashing
- `PKI__Crypto` — RSA-4096 + ECDSA P-256 key generation, sign, verify
- `Vault__Key_Manager` — Branch key pair storage and retrieval

**Objects (`sg_send_cli/objects/`)** — 4 classes:
- `Vault__Object_Store` — CAS blob storage (store/load/exists/verify)
- `Vault__Ref_Manager` — Encrypted mutable references (HEAD pointers)
- `Vault__Commit` — Create/load commit objects, signature verification
- `Vault__Inspector` — Read-only vault inspection (for debug commands)

**API (`sg_send_cli/api/`)** — 6 classes:
- `Vault__API` — HTTP client (read/write/delete/batch/list)
- `Vault__Backend` — Abstract backend interface
- `Vault__Backend__API` — Remote server backend
- `Vault__Backend__Local` — Local filesystem backend (for testing)
- `Vault__API__In_Memory` — In-memory backend (for testing)
- `Transfer__Envelope` — API payload wrapper (deprecated)
- `API__Transfer` — Transfer-based API client (deprecated)

**PKI (`sg_send_cli/pki/`)** — 2 classes:
- `PKI__Keyring` — Local key pair management
- `PKI__Key_Store` — Persistent key storage

**Secrets (`sg_send_cli/secrets/`)** — 1 class:
- `Secrets__Store` — AES-GCM encrypted credential store

### Layer 4: Sync Engine (`sg_send_cli/sync/`) — 12 classes

| Class                    | Responsibility                                    |
|--------------------------|---------------------------------------------------|
| Vault__Sync              | **Orchestrator** — init, commit, status, pull, push, clone, fsck |
| Vault__Sub_Tree          | Build/flatten/checkout hierarchical encrypted trees |
| Vault__Merge             | Three-way merge with conflict detection            |
| Vault__Fetch             | Download missing objects, LCA computation          |
| Vault__Batch             | Build and execute batch push operations             |
| Vault__Branch_Manager    | Create/load/save branches and branch index          |
| Vault__Storage           | Filesystem layout (.sg_vault/bare/local/)           |
| Vault__Bare              | Bare vault checkout/clean (no working copy)         |
| Vault__Change_Pack       | Create pending change bundles                       |
| Vault__GC                | Drain pending change packs into object store        |
| Vault__Remote_Manager    | Multi-remote config management                      |
| Vault__Ignore            | .gitignore parsing and file exclusion               |
| Vault__Components        | Component bag for _init_components()                |

### Layer 5: CLI (`sg_send_cli/cli/`) — 6 classes

| Class                   | Responsibility                              |
|-------------------------|---------------------------------------------|
| CLI__Main               | Argument parser, command dispatch, error handling |
| CLI__Vault              | Vault command implementations               |
| CLI__PKI                | PKI command implementations                 |
| CLI__Progress           | Progress callback for push/pull/clone       |
| CLI__Token_Store        | Access token and base URL persistence       |
| CLI__Credential_Store   | Encrypted vault key storage                 |
| CLI__Debug_Log          | Network traffic logging                     |

## Filesystem Layout

```
my-vault/                        <-- working directory (plaintext files)
  |-- hello.txt
  |-- docs/
  |     |-- readme.md
  |
  |-- .sg_vault/                 <-- vault metadata (NEVER committed to git)
        |-- bare/                <-- shared structure (synced to server)
        |     |-- data/          <-- CAS objects (commits, trees, blobs)
        |     |     |-- obj-cas-imm-a1b2c3d4e5f6
        |     |     |-- obj-cas-imm-f6e5d4c3b2a1
        |     |     +-- ...
        |     |-- refs/          <-- mutable HEAD pointers
        |     |     |-- ref-pid-muw-abc123def456
        |     |     +-- ref-pid-snw-789012345678
        |     |-- keys/          <-- public signing keys
        |     |     +-- key-rnd-imm-...
        |     |-- indexes/       <-- branch index
        |     |     +-- idx-pid-muw-...
        |     |-- branches/      <-- (reserved)
        |     +-- pending/       <-- change packs awaiting drain
        |           +-- pack-{uuid}/
        |
        +-- local/               <-- per-clone private data (NEVER synced)
              |-- config.json    <-- {"my_branch_id": "branch-clone-..."}
              |-- vault_key      <-- passphrase:vault_id
              |-- debug          <-- "on" or "off"
              |-- token          <-- access token (if saved)
              |-- base_url       <-- server URL (if saved)
              +-- keys/          <-- private signing keys (PEM)
```

## Object Relationship Diagram

```
  ref-pid-muw-... (named HEAD)     ref-pid-snw-... (clone HEAD)
         |                                |
         v                                v
  obj-cas-imm-... (commit)         obj-cas-imm-... (commit)
  {                                {
    schema: "commit_v1"              schema: "commit_v1"
    tree_id -------+                 tree_id -------+
    parents: [...]  |                 parents: [...]  |
    message_enc     |                 message_enc     |
    branch_id       |                 branch_id       |
    signature       |                 signature       |
  }                 |               }                 |
                    v                                 v
            obj-cas-imm-... (root tree)       obj-cas-imm-... (root tree)
            {                                 {
              schema: "tree_v1"                 schema: "tree_v1"
              entries: [                        entries: [
                {                                 {
                  blob_id ---> obj-cas-imm-...      blob_id ---> obj-cas-imm-...
                  name_enc: "base64..."             name_enc: "base64..."
                  size_enc: "base64..."             size_enc: "base64..."
                  content_hash_enc: "..."           content_hash_enc: "..."
                },                                },
                {                                 {
                  tree_id ---> obj-cas-imm-...      tree_id ---> obj-cas-imm-...
                  name_enc: "base64..." (folder)    name_enc: "base64..." (folder)
                }                                 }
              ]                                 ]
            }                                 }
```

## Critical Architectural Properties

1. **Immutability** — Objects in `bare/data/` are write-once. The ID is the SHA-256
   hash of the ciphertext. If the content changes, the ID changes.

2. **Encryption boundary** — Plaintext exists only in-memory and in the working
   directory. Everything in `bare/` is encrypted. Everything in `local/` is private
   to the clone and never synced.

3. **Server-agnostic storage** — The server is a dumb key-value store. It stores
   `{vault_id}/{file_id} → bytes`. No server-side logic beyond auth and CAS.

4. **Deterministic key derivation** — Given the same passphrase and vault_id, you
   get the same read_key, write_key, ref_file_id, and branch_index_file_id on any
   machine. This is how clones find each other without a server directory.
