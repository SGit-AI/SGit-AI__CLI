# 05 — Sync Engine

**Author:** Developer
**Audience:** Developers

## Overview

The sync engine (`Vault__Sync`) orchestrates all vault operations. It's the "brain"
that connects crypto, objects, API, and branch management into user-facing workflows.

## Branch Model

Every vault has exactly two types of branches:

```
  +------------------+          +------------------+
  |  NAMED BRANCH    |          |  CLONE BRANCH    |
  |  "current"       |          |  "local"         |
  |                  |          |                  |
  |  Shared HEAD     |          |  Per-clone HEAD  |
  |  (canonical)     |          |  (local state)   |
  |                  |          |                  |
  |  ref-pid-muw-*   |          |  ref-pid-snw-*   |
  +--------+---------+          +--------+---------+
           |                             |
           v                             v
     commit A  <------  parent  ------  commit B (merge commit)
     commit C  <------  parent  ------  commit B
```

**Named branch** — The "main" branch. Shared among all clones. Push updates this.
**Clone branch** — Per-clone working branch. Commit writes here. Pull merges named → clone.

### Why Two Branches?

This design avoids the "force push" problem. Each clone commits to its own branch,
then push atomically moves the named branch forward. If two clones push simultaneously,
the second one will pull first (fetch-first pattern), merge, then push.

## Operation Flows

### `sgit init`

```
  User runs: sgit init my-vault

  1. Create directory (must be empty)
  2. Generate vault_key = "{random24}:{random8}"
  3. Derive keys (read_key, write_key, ref_file_id, branch_index_file_id)
  4. Create .sg_vault/bare/{data,refs,keys,indexes,pending,branches}
  5. Create .sg_vault/local/
  6. Generate EC P-256 key pairs for named + clone branches
  7. Create named branch "current" (branch-named-{hex16})
  8. Create clone branch "local" (branch-clone-{hex16})
  9. Create empty root tree -> store as obj-cas-imm-*
  10. Create init commit (tree_id=root, parents=[], msg="init") -> store
  11. Write refs: named HEAD = commit_id, clone HEAD = commit_id
  12. Save branch index (encrypted)
  13. Save local config (my_branch_id = clone branch ID)
  14. Save vault_key to .sg_vault/local/vault_key
  15. Return {directory, vault_key, vault_id, branch_id}
```

### `sgit commit`

```
  User runs: sgit commit "add files"

  1. Read vault_key -> derive keys
  2. Load branch index -> find clone branch
  3. Read clone branch HEAD ref -> parent_commit_id
  4. Load parent commit -> flatten old tree (for blob reuse)
  5. Scan working directory (respecting .gitignore)
  6. Build sub-trees bottom-up:

     Working directory:             Sub-tree construction:
     hello.txt                      root tree
     docs/readme.md                   +-- blob entry (hello.txt)
     docs/guide.md                    +-- tree entry (docs/)
                                            +-- blob entry (readme.md)
                                            +-- blob entry (guide.md)

  7. For each file:
     - Compute content_hash = SHA256(plaintext)[:12]
     - If content_hash matches old entry AND old blob_id exists -> reuse blob
     - Otherwise: encrypt(read_key, content) -> store -> new blob_id
     - Create tree entry with encrypted metadata (name_enc, size_enc, etc.)
  8. Store tree objects bottom-up (leaf dirs first, root last)
  9. Load clone branch signing key
  10. Create commit object:
      - tree_id = root_tree_id
      - parents = [parent_commit_id]
      - message_enc = encrypt(read_key, message)
      - branch_id = clone_branch_id
      - signature = ECDSA(signing_key, commit_json)
  11. Encrypt and store commit -> commit_id
  12. Update clone branch HEAD ref -> commit_id
  13. Return {commit_id, branch_id, message}
```

### `sgit push`

```
  User runs: sgit push

  1. Check for uncommitted changes -> reject if dirty
  2. If not first push: pull first (fetch-first pattern)
     - If pull results in conflicts -> reject, user must resolve
  3. Re-read refs (may have changed after pull)
  4. If clone HEAD == named HEAD -> nothing to push
  5. Snapshot named ref hash for CAS (write-if-match)
  6. Load clone commit -> flatten tree
  7. Load named commit -> flatten tree (if exists)
  8. Compute object delta:
     - New blobs = clone blobs - named blobs
     - Commit chain from clone HEAD to named HEAD
  9. Build batch operations:

     +-------------------------------------------+
     | Batch Operations                          |
     +-------------------------------------------+
     | WRITE bare/data/obj-cas-imm-... (new blob)|
     | WRITE bare/data/obj-cas-imm-... (commit)  |
     | WRITE bare/data/obj-cas-imm-... (tree)    |
     | WRITE bare/refs/ref-pid-muw-... (new HEAD)|
     +-------------------------------------------+

  10. Execute batch (or individual uploads as fallback)
  11. Update local named ref to match clone ref
  12. Return {status, commit_id, objects_uploaded, commits_pushed}

  First push is special:
  - Upload entire bare/ directory structure first
  - Skip the pull step (server is empty)
```

### `sgit pull`

```
  User runs: sgit pull

  1. Auto-drain pending change packs (GC)
  2. Read config -> find clone branch and named branch
  3. Fetch remote named ref from server
  4. Download any missing objects reachable from remote commit
  5. Read local clone HEAD and remote named HEAD

  6. If clone HEAD == named HEAD -> "Already up to date"

  7. Find LCA (Lowest Common Ancestor):

     clone HEAD                 named HEAD
         |                         |
         v                         v
     commit D                  commit E
         |                         |
         v                         v
     commit C  <--- LCA --->   commit C
         |                         |
         v                         v
     commit B                  commit B

  8. Flatten three trees:
     - base_map  = LCA commit tree (common ancestor)
     - ours_map  = clone HEAD tree (local state)
     - theirs_map = named HEAD tree (remote state)

  9. Three-way merge:

     For each path in (base ∪ ours ∪ theirs):
     +-----------------------------------------------------------+
     | Base | Ours | Theirs | Ours==Base | Theirs==Base | Result  |
     +-----------------------------------------------------------+
     |  Y   |  Y   |   Y   |    Y       |     Y        | Keep    |
     |  Y   |  Y   |   Y   |    Y       |     N        | Theirs  |
     |  Y   |  Y   |   Y   |    N       |     Y        | Ours    |
     |  Y   |  Y   |   Y   |    N       |     N (same) | Ours    |
     |  Y   |  Y   |   Y   |    N       |     N (diff) | CONFLICT|
     |  N   |  N   |   Y   |    -       |     -        | Add     |
     |  N   |  Y   |   N   |    -       |     -        | Keep    |
     |  Y   |  Y   |   N   |    Y       |     -        | Delete  |
     |  Y   |  Y   |   N   |    N       |     -        | CONFLICT|
     |  Y   |  N   |   Y   |    -       |     Y        | Delete  |
     |  Y   |  N   |   Y   |    -       |     N        | CONFLICT|
     |  Y   |  N   |   N   |    -       |     -        | Delete  |
     +-----------------------------------------------------------+

  10. If conflicts:
      - Write .conflict files with "theirs" version
      - Save merge state to local/merge_state.json
      - Return {status: 'conflicts', conflicts: [...]}
      - User resolves, then runs `sgit commit`

  11. If no conflicts:
      - Checkout merged file map to working directory
      - Remove deleted files
      - Build merged tree from flat map
      - Create merge commit (parents = [clone_HEAD, named_HEAD])
      - Update clone branch HEAD ref
      - Return {status: 'merged', commit_id, added, modified, deleted}
```

### `sgit clone`

```
  User runs: sgit clone my-passphrase:abc12345 my-vault

  1. Derive keys from vault_key
  2. Create directory + bare structure
  3. List all files on server with prefix 'bare/'
  4. Download every file into local .sg_vault/bare/
  5. Load branch index -> find named branch "current"
  6. Create new clone branch (branch-clone-{hex16}) with fresh EC key pair
  7. Set clone HEAD = named HEAD
  8. Add clone branch to branch index
  9. Save pending_registration.json (uploaded on first push)
  10. Create local config + save vault_key
  11. If named HEAD exists:
      - Walk commit tree, download any missing objects
      - Checkout working copy from HEAD tree
  12. Return {directory, vault_key, vault_id, branch_id}
```

## Sub-Tree Model

Files are organized in a hierarchical tree structure mirroring the directory layout:

```
  Working directory:          Object store:

  hello.txt                   root tree (obj-cas-imm-aaa)
  docs/                         +-- blob_id: obj-cas-imm-111 (hello.txt)
    readme.md                   +-- tree_id: obj-cas-imm-bbb (docs/)
    api/                              +-- blob_id: obj-cas-imm-222 (readme.md)
      spec.json                       +-- tree_id: obj-cas-imm-ccc (api/)
                                            +-- blob_id: obj-cas-imm-333 (spec.json)
```

**Build direction:** Bottom-up (deepest directories first, root last).
**Flatten direction:** Top-down (root first, recursing into sub-trees).

## Blob Reuse Optimization

On commit, if a file's `content_hash` hasn't changed since the previous commit,
the existing blob_id is reused without re-encrypting:

```
  if old_flat_entries[path].content_hash == new_content_hash:
      blob_id = old_flat_entries[path].blob_id    # reuse!
  else:
      blob_id = encrypt_and_store(content)         # new blob
```

This makes commits fast when only a few files change.

## Conflict Resolution

When pull detects a conflict:

```
  my-vault/
    |-- document.txt            <-- "ours" version (your local changes)
    |-- document.txt.conflict   <-- "theirs" version (remote changes)
```

The user:
1. Edits `document.txt` to resolve the conflict
2. Deletes `document.txt.conflict`
3. Runs `sgit commit` to finalize the merge

Or runs `sgit merge-abort` to restore pre-merge state.
