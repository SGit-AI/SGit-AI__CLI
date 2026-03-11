# Reality Document — Current Capabilities

**Date:** 11 March 2026
**Version:** v0.1.0 (post-Session 1)
**Status:** Active development

---

## What Exists Today

### Test Coverage

- **421 tests total, all passing**
- Safe_* types: validation, edge cases, type preservation
- Schemas: instantiation, round-trip json <-> from_json
- Crypto: interop vectors, round-trip encrypt/decrypt, full pipeline
- CLI commands: init, clone, pull, push, status, remote-status, inspect, log
- PKI: keygen, export, import, sign, verify, encrypt, decrypt
- Secrets store: secret entry management
- Object store: content-addressable storage, commit chain, tree management
- Sync engine: full clone/pull/push lifecycle

### Package Structure

```
sg_send_cli/
├── _version.py                    # VERSION = 'v0.1.0'
├── safe_types/                    # 19 Safe_* domain types
│   ├── Safe_Str__Vault_Id.py
│   ├── Safe_Str__Transfer_Id.py
│   ├── Safe_Str__Vault_Passphrase.py
│   ├── Safe_Str__Vault_Key.py
│   ├── Safe_Str__SHA256.py
│   ├── Safe_Str__Access_Token.py
│   ├── Safe_Str__Vault_Name.py
│   ├── Safe_Str__File_Path.py
│   ├── Safe_Str__File_Id.py
│   ├── Safe_Str__Write_Key.py
│   ├── Safe_Str__Object_Id.py
│   ├── Safe_Str__Commit_Message.py
│   ├── Safe_Str__ISO_Timestamp.py
│   ├── Safe_Str__Base_URL.py
│   ├── Safe_Str__Vault_Path.py
│   ├── Safe_Str__Secret_Key.py
│   ├── Safe_Str__Key_Fingerprint.py
│   ├── Safe_UInt__File_Size.py
│   └── Enum__Sync_State.py
├── schemas/                       # 9 Type_Safe schemas
│   ├── Schema__Vault_Meta.py
│   ├── Schema__Vault_Config.py
│   ├── Schema__Vault_Index_Entry.py
│   ├── Schema__Vault_Index.py
│   ├── Schema__Transfer_File.py
│   ├── Schema__Object_Ref.py
│   ├── Schema__Object_Tree.py / Schema__Object_Tree_Entry.py
│   ├── Schema__Object_Commit.py
│   ├── Schema__Secret_Entry.py
│   └── Schema__PKI_Key_Pair.py / Schema__PKI_Public_Key.py
├── crypto/                        # Encryption engines
│   ├── Vault__Crypto.py           # AES-256-GCM, PBKDF2, HKDF
│   └── PKI__Crypto.py            # X25519 key exchange, Ed25519 signing
├── objects/                       # Content-addressable object store
│   ├── Vault__Object_Store.py     # SHA-256 addressed blob storage
│   ├── Vault__Ref_Manager.py      # HEAD ref tracking
│   └── Vault__Inspector.py        # Dev tools: tree, log, stats, cat-object
├── sync/                          # Sync engine
│   ├── Vault__Sync.py            # clone, pull, push, status, remote-status
│   └── Vault__Legacy_Guard.py    # Migration from pre-object-store format
├── secrets/                       # Secret management
│   └── Secrets__Store.py
├── pki/                           # Public Key Infrastructure
│   ├── PKI__Keyring.py           # Local key pair management
│   └── PKI__Key_Store.py         # Key storage
├── api/                           # Server communication
│   └── Vault__API.py             # Transfer API client (read/write/delete)
└── cli/                           # CLI interface
    ├── __init__.py               # Entry point delegation
    ├── CLI__Main.py              # Argument parser, subcommand routing
    ├── CLI__Vault.py             # Vault commands (init, clone, pull, push, etc.)
    ├── CLI__PKI.py               # PKI commands (keygen, sign, verify, encrypt, decrypt)
    └── CLI__Token_Store.py       # Access token persistence
```

### CLI Commands (16 total)

**Vault lifecycle:**
| Command | Description |
|---------|-------------|
| `init <dir>` | Create new empty vault, register on server |
| `clone <key> [dir]` | Clone remote vault to local (with progress UI) |
| `pull [dir]` | Pull remote changes to local |
| `push [dir]` | Push local changes to remote |
| `status [dir]` | Show local changes vs committed tree |
| `remote-status [dir]` | Compare local vs remote vault state |

**Dev/inspect tools:**
| Command | Description |
|---------|-------------|
| `inspect [dir]` | Vault state overview |
| `inspect-object <id>` | Object details |
| `inspect-tree [dir]` | Current tree entries |
| `inspect-log [dir]` | Commit chain (supports --oneline, --graph) |
| `inspect-stats [dir]` | Object store statistics |
| `cat-object <id>` | Decrypt and display object contents |
| `log [dir]` | Alias for inspect-log |
| `derive-keys <key>` | Show derived vault keys (debug) |

**PKI commands:**
| Command | Description |
|---------|-------------|
| `pki keygen` | Generate X25519 + Ed25519 key pair |
| `pki list` | List local key pairs |
| `pki export <fp>` | Export public key bundle (JSON) |
| `pki import <file>` | Import contact public key |
| `pki contacts` | List imported contacts |
| `pki sign <file>` | Ed25519 detached signature |
| `pki verify <file> <sig>` | Verify detached signature |
| `pki encrypt <file>` | X25519 hybrid encryption for recipient |
| `pki decrypt <file>` | Decrypt with local key |

### Recent Additions (this session)

1. **Clone progress UI** — Real-time progress bar with emoji indicators:
   - Key derivation and metadata download status
   - Per-file progress bar with count, size, and filename
   - Summary box with total files, size, version, commit ID, elapsed time
   - Dynamic column sizing for clean terminal alignment

### Proven Workflows

- Creating and syncing vaults from inside Claude Code
- Teams integrating vaults into their workflows
- Lambda function integration (vault as config store)
- Deploy service using vault for EC2.json deployment configs

### Architecture Highlights

- **Content-addressable object store**: SHA-256 addressed blobs, git-like commit/tree model
- **End-to-end encryption**: All data encrypted client-side (AES-256-GCM) before upload
- **Key derivation**: Single vault key derives vault_id, read_key, write_key, file IDs via HKDF
- **Browser interop**: Crypto operations match Web Crypto API byte-for-byte
- **Type_Safe throughout**: Zero raw primitives, all fields are Safe_* domain types
- **Progress callbacks**: UI-agnostic on_progress pattern in sync layer

---

## Known Limitations

1. **Full clone required** — No way to access individual files without cloning entire vault (13+ seconds for 25 files / 248 KB). Critical blocker for Lambda cold-start scenarios.
2. **No concurrent file downloads** — Files downloaded sequentially during clone/pull
3. **No partial pull** — Cannot pull a subset of files
4. **No branching** — Single linear commit history only
5. **No merge** — Conflict resolution not yet implemented

## What's In Progress

- **Cloneless vault access** — Design phase: browse, view, and download individual files without full clone (see architect/dev documents)
