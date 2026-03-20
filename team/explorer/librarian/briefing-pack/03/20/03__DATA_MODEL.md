# 03 — Data Model

**Author:** Architect
**Audience:** Architects, Developers

## Overview

All data is modelled using the `osbot_utils.type_safe.Type_Safe` framework.
Every field uses a domain-specific Safe_* type — never raw `str`, `int`, or `dict`.

## Schema Class Hierarchy

```
Type_Safe (osbot_utils)
 |
 +-- Schema__Object_Commit        # commit object (stored encrypted in CAS)
 +-- Schema__Object_Tree          # tree object (directory listing)
 +-- Schema__Object_Tree_Entry    # single file/folder in a tree
 +-- Schema__Object_Ref           # mutable ref (HEAD pointer)
 +-- Schema__Branch_Meta          # branch metadata
 +-- Schema__Branch_Index         # index of all branches
 +-- Schema__Local_Config         # per-clone config
 +-- Schema__Vault_Config         # vault-level config
 +-- Schema__Vault_Meta           # vault identity
 +-- Schema__Vault_Index          # file index (legacy)
 +-- Schema__Vault_Index_Entry    # single file in index (legacy)
 +-- Schema__Vault_Policy         # access policy (future)
 +-- Schema__Remote_Config        # remote server config
 +-- Schema__Transfer_File        # API transfer wrapper
 +-- Schema__Batch_Request        # batch API envelope
 +-- Schema__Batch_Operation      # single batch op
 +-- Schema__Change_Pack          # pending changes bundle
 +-- Schema__Tracking_State       # sync state tracking
 +-- Schema__PKI_Key_Pair         # PKI key pair
 +-- Schema__PKI_Public_Key       # PKI public key (for contacts)
 +-- Schema__Secret_Entry         # encrypted credential
```

## Core Schemas in Detail

### Schema__Object_Commit

The fundamental unit of history. Stored encrypted in CAS.

```python
class Schema__Object_Commit(Type_Safe):
    schema           : Safe_Str__Schema_Version  # 'commit_v1'
    tree_id          : Safe_Str__Object_Id       # root tree: obj-cas-imm-{hash}
    parents          : list[Safe_Str__Object_Id] # parent commit IDs (0=init, 1=normal, 2=merge)
    timestamp_ms     : Safe_UInt__Timestamp       # milliseconds since epoch
    message_enc      : Safe_Str__Encrypted_Value  # AES-GCM(read_key, message) → base64
    branch_id        : Safe_Str__Branch_Id        # which branch created this commit
    signature        : Safe_Str__Signature        # ECDSA P-256 signature (base64)
    author_key_id    : Safe_Str__Author_Key_Id    # (reserved for future)
    author_signature : Safe_Str__Signature        # (reserved for future)
    attestations     : list[Safe_Str__Signature]  # (reserved for future)
```

**Lifecycle:** Created by `Vault__Commit.create_commit()`, stored via `Vault__Object_Store.store()`.

### Schema__Object_Tree

Directory listing. Each tree maps to one directory level.

```python
class Schema__Object_Tree(Type_Safe):
    schema  : Safe_Str__Schema_Version           # 'tree_v1'
    entries : list[Schema__Object_Tree_Entry]     # files and sub-folders
```

### Schema__Object_Tree_Entry

A single file or sub-directory in a tree.

```python
class Schema__Object_Tree_Entry(Type_Safe):
    blob_id          : Safe_Str__Object_Id        # file → obj-cas-imm-{hash} (mutual exclusive with tree_id)
    tree_id          : Safe_Str__Object_Id        # folder → obj-cas-imm-{hash}
    name_enc         : Safe_Str__Encrypted_Value  # AES-GCM(read_key, filename) → base64
    size_enc         : Safe_Str__Encrypted_Value  # AES-GCM(read_key, str(size)) → base64
    content_hash_enc : Safe_Str__Encrypted_Value  # AES-GCM(read_key, sha256[:12]) → base64
    content_type_enc : Safe_Str__Encrypted_Value  # AES-GCM(read_key, mime_type) → base64
```

**Important:** The server only sees `blob_id`/`tree_id` and encrypted metadata.
File names, sizes, and content hashes are all encrypted. The server cannot list
or search vault contents.

### Schema__Branch_Meta

```python
class Schema__Branch_Meta(Type_Safe):
    branch_id      : Safe_Str__Branch_Id          # branch-named-{hex16} or branch-clone-{hex16}
    name           : Safe_Str__Branch_Name        # human-readable name ("current", "local")
    branch_type    : Enum__Branch_Type            # NAMED or CLONE
    head_ref_id    : Safe_Str__Ref_Id             # ref-pid-muw-{hex} or ref-pid-snw-{hex}
    public_key_id  : Safe_Str__Key_Id             # key-rnd-imm-{hex}
    private_key_id : Safe_Str__Key_Id             # key-rnd-imm-{hex} (named only)
    creator_branch : Safe_Str__Branch_Id          # parent branch (clones only)
    created_at     : Safe_UInt__Timestamp
```

### Schema__Branch_Index

```python
class Schema__Branch_Index(Type_Safe):
    schema   : Safe_Str__Schema_Version           # 'branch_index_v1'
    branches : list[Schema__Branch_Meta]
```

## Self-Describing ID Format

Every identifier in the system follows a 4-segment pattern:

```
{type}-{derivation}-{mutability}-{value}

type:        obj, ref, key, idx, branch
derivation:  cas (content-addressed), pid (passphrase-derived), rnd (random)
mutability:  imm (immutable), muw (mutable-write-protected), snw (single-node-write)
value:       hex hash or random hex
```

| ID Pattern           | Meaning                            | Example                     |
|----------------------|------------------------------------|-----------------------------|
| `obj-cas-imm-*`     | CAS immutable object (blob/tree/commit) | `obj-cas-imm-a1b2c3d4e5f6` |
| `ref-pid-muw-*`     | Named branch HEAD (passphrase-derived) | `ref-pid-muw-abc123def456` |
| `ref-pid-snw-*`     | Clone branch HEAD                  | `ref-pid-snw-789012345678`  |
| `idx-pid-muw-*`     | Branch index                       | `idx-pid-muw-fedcba987654`  |
| `branch-named-*`    | Named branch ID                    | `branch-named-a1b2c3d4e5f67890` |
| `branch-clone-*`    | Clone branch ID                    | `branch-clone-f6e5d4c3b2a19876` |
| `key-rnd-imm-*`     | Cryptographic key ID               | `key-rnd-imm-abc123`       |

## Object Store Layout

All objects live in `.sg_vault/bare/data/`:

```
bare/data/
  |-- obj-cas-imm-a1b2c3d4e5f6    <-- encrypted blob (file content)
  |-- obj-cas-imm-b2c3d4e5f6a1    <-- encrypted tree (directory listing)
  |-- obj-cas-imm-c3d4e5f6a1b2    <-- encrypted commit
  +-- ...
```

**Storage invariant:** `object_id == SHA256(ciphertext)[:12]` (with `obj-cas-imm-` prefix).
This means you can verify integrity by re-hashing the file content.

## Flat Map Representation

The `Vault__Sub_Tree.flatten()` method converts the tree hierarchy into a flat dict:

```python
{
    "hello.txt": {
        "blob_id":      "obj-cas-imm-a1b2c3d4e5f6",
        "size":         42,
        "content_hash": "7d4e8f2a1b3c",
        "content_type": "text/plain"
    },
    "docs/readme.md": {
        "blob_id":      "obj-cas-imm-f6e5d4c3b2a1",
        "size":         128,
        "content_hash": "3c1b2a8f4e7d",
        "content_type": "text/markdown"
    }
}
```

This flat map is used for:
- `status` — compare flat map vs. working directory
- `merge` — three-way merge operates on flat maps
- `commit` — build new tree from working directory + old flat map (blob reuse)

## Round-Trip Invariant

Every schema class must satisfy:

```python
obj = Schema__Object_Commit(schema='commit_v1', tree_id='obj-cas-imm-a1b2c3d4e5f6', ...)
assert Schema__Object_Commit.from_json(obj.json()).json() == obj.json()
```

This is tested for all schema classes in the test suite.
