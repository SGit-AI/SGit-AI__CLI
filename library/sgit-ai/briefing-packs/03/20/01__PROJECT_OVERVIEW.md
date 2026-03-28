# 01 — Project Overview

**Author:** Librarian
**Audience:** Everyone

## What is sgit-ai?

sgit-ai is a **Python CLI tool** that syncs **end-to-end encrypted vaults** between
a local filesystem and the SG/Send Transfer API. Think of it as **"git for encrypted
vaults"** — it uses git-like concepts (commits, branches, push, pull, merge) but every
object stored on the server is AES-256-GCM encrypted. The server never sees plaintext.

```
 +-----------------+        encrypted        +------------------+
 |   Local Files   |  <--- sgit push/pull -->  |  SG/Send Server  |
 |  (plaintext)    |        (AES-GCM)        |  (ciphertext)    |
 +-----------------+                         +------------------+
         |                                           |
    vault key                                   zero knowledge
  (passphrase:id)                             (no keys, no names)
```

## Identity

| Property          | Current Value              | Target Value        |
|-------------------|---------------------------|---------------------|
| PyPI package      | `sg-send-cli`             | `sgit-ai`           |
| CLI command       | `sgit` (already aliased)  | `sgit` (primary)    |
| Python import     | `sg_send_cli`             | TBD (rename needed) |
| Domain            | —                         | `sgit.ai`           |
| GitHub repo       | `SG_Send__CLI`            | TBD                 |

## Current Version: v0.8.10 (Alpha)

The tool is functional end-to-end for single-user and basic multi-user workflows:

### What Works
- `sgit init` — Create a new encrypted vault
- `sgit clone <vault-key> <dir>` — Clone from remote server
- `sgit commit` — Snapshot working directory into encrypted commit
- `sgit push` — Upload encrypted objects to server
- `sgit pull` — Fetch + three-way merge from server
- `sgit status` — Show uncommitted changes
- `sgit branches` — List all branches (named + clone)
- `sgit log` — Show commit history (with `--graph`)
- `sgit pki keygen/sign/verify/encrypt/decrypt` — PKI operations
- `sgit fsck` — Vault integrity check + repair
- `sgit inspect/inspect-tree/cat-object` — Debug tools
- `.gitignore` support for file exclusion

### What Doesn't Work Yet
- Multi-remote support (schema exists, not wired)
- Change pack integration (schema + GC exist, not battle-tested)
- File deletion propagation across clones (known bug)
- Browser-to-CLI interop (partial — 404s on some paths)

## Architecture at a Glance

```
                      +-------------------+
                      |     CLI Layer     |
                      | CLI__Main/Vault   |
                      +--------+----------+
                               |
                      +--------v----------+
                      |   Sync Engine     |
                      | Vault__Sync       |
                      | Vault__Merge      |
                      | Vault__Sub_Tree   |
                      +--------+----------+
                               |
              +----------------+----------------+
              |                |                |
     +--------v------+ +------v-------+ +------v-------+
     |   Objects     | |   Crypto     | |    API       |
     | Object_Store  | | Vault__Crypto| | Vault__API   |
     | Ref_Manager   | | PKI__Crypto  | | batch/read   |
     | Commit        | | Key_Manager  | | write/list   |
     +--------+------+ +------+-------+ +--------------+
              |                |
     +--------v----------------v--------+
     |        Schemas + Safe Types      |
     | Schema__Object_Commit            |
     | Schema__Object_Tree[_Entry]      |
     | Safe_Str__Vault_Id, etc.         |
     +----------------------------------+
```

## Key Design Decisions

1. **Content-Addressable Storage (CAS)** — Objects are stored by SHA-256 hash of
   their ciphertext. ID format: `obj-cas-imm-{hash12}`. Immutable once stored.

2. **Dual-Branch Model** — Every vault has a "named" branch (shared, remote-canonical)
   and per-clone "clone" branches (local state). Push merges clone → named.

3. **Self-Describing IDs** — Every identifier encodes its type:
   - `obj-cas-imm-*` — content-addressed immutable object
   - `ref-pid-muw-*` — named branch ref (passphrase-derived, mutable, write-protected)
   - `ref-pid-snw-*` — clone branch ref
   - `branch-named-*` / `branch-clone-*` — branch IDs
   - `key-rnd-imm-*` — cryptographic key
   - `idx-pid-muw-*` — branch index

4. **Zero-Knowledge Server** — The server stores opaque blobs. File names, directory
   structure, commit messages, and branch names are all encrypted. The server cannot
   read, search, or index vault contents.

5. **Type_Safe Framework** — All data modelling uses `osbot_utils.type_safe`. No raw
   Python primitives (`str`, `int`, `dict`) as class fields. Every field has a domain-
   specific type with validation built in.

## Team Structure

The project uses two coordinated teams:

- **Explorer Team** — Builds new features (Architect, Dev, QA, DevOps, Librarian, Historian)
- **Villager Team** — Refactors and improves quality (Architect, Dev, QA, AppSec, Designer, DevOps, Sherpa)

See `team/explorer/CLAUDE.md` and `team/villager/CLAUDE.md` for role definitions.
