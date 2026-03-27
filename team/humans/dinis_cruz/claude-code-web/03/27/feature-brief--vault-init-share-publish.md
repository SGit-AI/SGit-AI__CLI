# Feature Brief: vault init / share / publish (+ export + uninit + diff)

**Date:** 2026-03-27  
**Status:** Revised — user feedback incorporated 2026-03-27  
**Branch:** `claude/new-explorer-team-cHLXU`  

---

## 1. Summary of Commands

| Command      | Phase | Description |
|---|---|---|
| `sgit init`  | 1 | Init vault in a non-empty directory (existing files, interactive UX + `--restore` mode) |
| `sgit share` | 1 | Generate Simple Token, upload encrypted vault snapshot to Transfer API |
| `sgit diff`  | 2 | File-level + content-level diff (working copy vs commit or remote) |
| `sgit uninit`| 3 | Remove `.sg_vault/` — always creates auto-backup zip first |
| `sgit publish` | 4 | Package vault as multi-level encrypted zip, upload via Transfer API |
| `sgit export`  | 4 | Package vault as local zip archive (same structure as publish, no upload) |

---

## 2. Command Specifications

### 2.1 `sgit init` — Init in Non-Empty Directory

**Current behaviour (from `Vault__Sync.init`):**
```python
if os.path.exists(directory):
    entries = os.listdir(directory)
    if entries:
        raise RuntimeError(f'Directory is not empty: {directory}')
```
The vault cannot be initialised into a directory that already has files.

**Proposed new behaviour:**

- Add `--existing` flag: `sgit init --existing <directory>` — skips the non-empty check
- When a non-empty directory is detected and `--existing` is **not** supplied, display an
  interactive prompt:
  ```
  Directory '<dir>' is not empty (42 files found).
  Initialise vault here anyway? [y/N]:
  ```
- After vault creation, display a second prompt:
  ```
  Commit all existing files now? [Y/n]:
  ```
  If yes, run an auto-commit equivalent to `sgit commit "Initial commit"` on the
  already-present files.

**`--restore` mode:**

If a `.vault__*.zip` file is found in the current directory, `sgit init` offers to restore
the vault from it:
```
sgit init --restore [directory]

Found vault backup: .vault__27-Mar-v0.3.0__1743033600.zip
Restore vault from this backup? [Y/n]:

Vault restored from backup.
  Vault ID:  a1b2c3d4
  Branch:    branch-clone-<hex>
```
This enables a round-trip: `sgit uninit` → backup created → `sgit init --restore` → vault
back in place.

**CLI changes needed:**
- `CLI__Vault.cmd_init` — add `--existing` and `--restore` flag handling + interactive prompts
- `Vault__Sync.init` — accept `allow_nonempty: bool = False` parameter to bypass the guard
- `Vault__Sync.restore_from_backup(zip_path)` — unzip `.sg_vault/` from backup archive
- No changes to Type_Safe schemas required

---

### 2.2 `sgit share` — Share via Simple Token

**What it does:**
1. Reads the vault's working copy (current HEAD tree, not uncommitted changes)
2. Generates a Simple Token (`word-word-NNNN` from CLI 320-word wordlist)
3. Derives `transfer_id = SHA-256(token)[:12]`
4. Derives AES-256-GCM key via PBKDF2
5. Encrypts and uploads a zip of the vault files to the Transfer API
6. Prints the token for the user to share

**UX:**
```
sgit share [directory] [--files <glob>]

Generating share token...
  Token:       maple-river-7291
  Transfer ID: 3f8a91bc2d04
  Files:       12 file(s), 48.3 KB

Upload complete. Share this token:

  maple-river-7291

Anyone with this token can download and decrypt the vault snapshot at:
  https://send.sgraph.ai/#maple-river-7291
```

**What is uploaded:** A flat zip of the vault's working copy files, AES-256-GCM encrypted.
This is a **snapshot** — not the bare vault structure. Recipients get the files, not the
vault history.

**New classes needed:**
- `Simple_Token` (Type_Safe, in `sgit_ai/transfer/`)
- `Safe_Str__Simple_Token` (regex `^[a-z]+-[a-z]+-\d{4}$`)
- `Vault__Share` (Type_Safe, in `sgit_ai/transfer/`)
- `CLI__Share` (in `sgit_ai/cli/`)

---

### 2.3 `sgit uninit` — Remove Vault Metadata (with Auto-Backup)

**What it does:**
1. **Always creates a local backup zip first** — naming convention:
   `.vault__{folder_name_spaces_removed}__timestamp.zip`
   where `timestamp = int(time.time())`.
   Example: folder `"27-Mar | v0.3.0 before and after"` →
   `.vault__27-Mar|v0.3.0beforeandafter__1743033600.zip`
   The dot prefix makes the file hidden on Unix systems (intentional).
2. Removes `.sg_vault/` directory (vault history and metadata only)
3. Leaves all working files intact
4. **No vault-ID confirmation prompt** — the auto-backup is the safety net

**UX:**
```
sgit uninit [directory]

Creating vault backup...
  Backup: .vault__27-Mar|v0.3.0beforeandafter__1743033600.zip (2.4 MB)

Removing .sg_vault/ from 27-Mar/...
  Working files: untouched (42 files)

Done. To restore this vault later:
  sgit init --restore .
```

**Round-trip:**
```
sgit uninit    →  backup created  →  sgit init --restore  →  vault restored
```

**No new schemas needed.** Simple filesystem operation + zip write.

---

### 2.4 `sgit diff` — Working Copy vs Commit / Remote

**What it does:**
- **File-level diff:** which files added/modified/deleted (extends `sgit status`)
- **Content-level diff:** unified diff output for text files
- **Binary files:** show size difference and SHA-256 hash only (no content diff)

**Modes:**
```
sgit diff [directory]              # working copy vs last local commit (HEAD)
sgit diff [directory] --remote     # working copy vs named branch HEAD (remote)
sgit diff [directory] <commit-id>  # working copy vs specific commit
```

**UX (text file):**
```
--- a/README.md  (commit abc123)
+++ b/README.md  (working copy)
@@ -1,3 +1,5 @@
 # My Project
+## Overview
+Added this section.
 Some content here.
```

**UX (binary file):**
```
~ images/photo.jpg  (binary)
    commit: 259,072 bytes  sha256: a1b2c3...
    local:  312,459 bytes  sha256: f9e8d7...
```

**New classes needed:**
- `Vault__Diff` (Type_Safe, in `sgit_ai/sync/`)
- `Schema__Diff_Result` + `Schema__Diff_File` schemas
- `CLI__Diff` (in `sgit_ai/cli/`)

---

### 2.5 `sgit publish` — Multi-Level Encrypted Zip + Upload

See Section 3 for the full zip schema. In brief:

- Packages vault files into a multi-level encrypted zip
- Outer layer encrypted with Simple Token derived key (AES-256-GCM)
- Inner layer encrypted with vault key (or password or PKI — phase 1: vault key only)
- Uploads outer zip to Transfer API
- Prints token

**UX:** Similar to `sgit share` but with additional output describing the inner key type.

---

### 2.6 `sgit export` — Local Vault Archive

**Use case:** Ephemeral vaults inside git repos — create vault, collaborate with LLM,
package the vault as a local zip for future continuation. Enables "vault archive" concept
and multi-agent collaboration with full provenance.

Same parent zip structure as `sgit publish` (Section 3), but:
- Output is a **local file** — default naming: `.vault__{folder_name_spaces_removed}__timestamp.zip`
  (same convention as `sgit uninit` backup — the formats are intentionally identical)
- No Transfer API upload
- User chooses whether to protect the inner layer with a key (prompted interactively,
  or via `--no-encrypt`)

**UX:**
```
sgit export [directory] [--output <file>] [--no-encrypt]

Exporting vault archive...
  Files:        12 file(s), 48.3 KB
  Inner key:    vault key (AES-256-GCM)
  Archive:      .vault__27-Mar|v0.3.0beforeandafter__1743033600.zip

Export complete: .vault__27-Mar|v0.3.0beforeandafter__1743033600.zip
```

Note: an `sgit uninit` backup is effectively a `sgit export` with the same naming
convention. Both can be restored via `sgit init --restore`.

---

## 3. Multi-Level Encryption Zip Schema (THE KEY ARCHITECTURE)

This is the locked-down schema for both `publish` and `export`. This section defines the
**exact structure** that all future work must conform to.

### 3.1 Outer Zip Structure

The outer zip is the file transferred or stored. Its structure:

```
<transfer-id>.zip            <-- outer zip (AES-256-GCM encrypted with Simple Token key)
├── manifest.json            <-- cleartext AFTER outer decryption
├── inner.zip.enc            <-- the actual files, encrypted with inner key
└── decryption-key.bin       <-- inner key, encrypted with vault key (or password/PKI)
```

### 3.2 manifest.json Schema

Cleartext after first decryption. Describes the contents and key hierarchy.

```json
{
  "schema":        "vault_archive_v1",
  "vault_id":      "<vault-id>",
  "created_at":    "<ISO-8601 timestamp>",
  "files":         12,
  "total_bytes":   49459,
  "inner_key_type": "vault_key",
  "inner_key_id":  "<vault-id>",
  "description":   "optional human description",
  "provenance": {
    "branch_id":   "<clone-branch-id>",
    "commit_id":   "<head-commit-id>",
    "author_key":  "<public-key-fingerprint-or-null>"
  }
}
```

**`inner_key_type` values (Phase 1):**
- `"vault_key"` — inner key is encrypted with the AES vault read-key
- `"none"` — inner zip is not encrypted (plain zip)

**`inner_key_type` values (Phase 2 — PKI expansion):**
- `"password"` — inner key is encrypted with PBKDF2-derived password key
- `"pki"` — inner key is encrypted with recipient's EC P-256 public key

### 3.3 inner.zip.enc

A standard zip file encrypted with AES-256-GCM. Contains the vault's working copy files
as-of the latest commit (HEAD tree). File paths are relative to the vault root.

```
inner.zip
├── README.md
├── data/
│   ├── file1.json
│   └── file2.txt
└── images/
    └── photo.jpg
```

### 3.4 decryption-key.bin

Binary file. The 32-byte AES inner key, encrypted with:
- `vault_key` mode: `AES-256-GCM(read_key_bytes, inner_key)`
- `none` mode: absent (no file)
- `pki` mode (future): ECIES-encrypted with recipient's public key

### 3.5 Outer Encryption

The entire outer zip assembly is encrypted as a single AES-256-GCM blob using the
Simple Token derived key before upload. On download, the token is used to decrypt
the outer zip, yielding `manifest.json`, `inner.zip.enc`, and `decryption-key.bin`.

### 3.6 Two-Step Decryption Protocol

```
Step 1: outer decryption
  token -> PBKDF2 -> outer_key
  AES-256-GCM-Decrypt(outer_key, outer_zip_enc) -> outer_zip

Step 2: inner decryption
  outer_zip/decryption-key.bin: AES-256-GCM-Decrypt(vault_read_key, ...) -> inner_key
  AES-256-GCM-Decrypt(inner_key, inner.zip.enc) -> inner.zip

Result: working files
```

### 3.7 New Schemas Needed

```python
# sgit_ai/schemas/Schema__Vault_Archive_Manifest.py
class Schema__Vault_Archive_Manifest(Type_Safe):
    schema         : Safe_Str__Schema_Version  = None   # 'vault_archive_v1'
    vault_id       : Safe_Str__Vault_Id        = None
    created_at     : Safe_Str__ISO_Timestamp   = None
    files          : Safe_UInt__File_Count
    total_bytes    : Safe_UInt__File_Size
    inner_key_type : Safe_Str__Key_Type        = None   # 'vault_key' | 'none' | 'pki'
    inner_key_id   : Safe_Str__Vault_Id        = None
    description    : Safe_Str__Commit_Message  = None
    provenance     : Schema__Archive_Provenance = None

# sgit_ai/schemas/Schema__Archive_Provenance.py
class Schema__Archive_Provenance(Type_Safe):
    branch_id  : Safe_Str__Branch_Id  = None
    commit_id  : Safe_Str__Object_Id  = None
    author_key : Safe_Str__SHA256     = None    # key fingerprint or None

# New safe types needed:
# Safe_Str__Key_Type       — 'vault_key' | 'none' | 'pki' | 'password'
# Safe_UInt__File_Count    — unsigned int, number of files
```

---

## 4. Simple Token Implementation Plan

See `simple-tokens-technical-brief.md` for the full reference.

### 4.1 New Type_Safe Classes

```
sgit_ai/transfer/
├── __init__.py
├── Simple_Token.py          # derives transfer_id + key from token string
├── Simple_Token__Wordlist.py  # CLI 320-word wordlist + generator
└── Vault__Transfer.py       # high-level: share, download, verify
```

### 4.2 Simple_Token Class

```python
class Simple_Token(Type_Safe):
    token : Safe_Str__Simple_Token = None

    def derive_transfer_id(self) -> str: ...
    def derive_key(self) -> bytes: ...
    def is_valid(self) -> bool: ...

    @classmethod
    def generate(cls) -> 'Simple_Token': ...
```

### 4.3 New Safe Types

```python
# Safe_Str__Simple_Token
class Safe_Str__Simple_Token(Safe_Str):
    regex           = re.compile(r'^[a-z]+-[a-z]+-\d{4}$')
    max_length      = 64
    allow_empty     = False
    trim_whitespace = True
```

---

## 5. Answers to Q8–Q11 (Codebase Research)

### Q8: Do we have diff of current local changes vs commits / remotes?

**What exists:**
- `Vault__Sync.status(directory)` — returns `{added, modified, deleted, clean}` by
  comparing the working directory against the last commit on the current clone branch.
  This is used by `sgit status`.
- `Vault__Inspector.inspect_commit_chain()` and `format_commit_log()` — show the full
  commit log (`sgit log`, `sgit inspect-log`).
- `Vault__Inspector.inspect_tree()` — shows the file list at HEAD (`sgit inspect-tree`).

**What does NOT exist:**
- No `diff` command showing line-level or byte-level differences between versions
- No ability to diff working copy against a specific commit by ID
- No ability to diff clone branch vs named branch (remote) at the file content level
  (only at the commit-ID level, inferred from `status`)
- No `diff` CLI command in `CLI__Main.build_parser()`

**Gap:** Diff against (a) a specific past commit and (b) the named/remote branch are both
missing. Only presence/absence and modification-flag are available; no content-level diff.

---

### Q9: Do we have revert or stash?

**What exists:**
- `Vault__Sync.merge_abort(directory)` — aborts an in-progress merge by restoring the
  pre-merge working copy from the stored `clone_commit_id`. This is the only restore
  operation. CLI command: `sgit merge-abort`.
- `Vault__Bare.checkout(directory, vault_key)` — checks out HEAD tree into working copy
  from a bare vault. Can be used as a manual "hard reset" pattern if the vault key is
  available and the user is comfortable using the lower-level command.

**What does NOT exist:**
- No `revert` command (restore a specific file or all files to a past commit state)
- No `stash` / `stash pop` mechanism
- No `reset --hard` equivalent
- No way to restore individual files without restoring the entire tree

**Gap:** Both revert and stash are missing entirely.

---

### Q10: Do we have named branch switching locally?

**What exists:**
- `Vault__Sync.branches(directory)` / `sgit branches` — lists all branches
- `Vault__Branch_Manager.create_clone_branch()` — creates a new clone branch
- `Vault__Branch_Manager.create_named_branch()` — creates a new named branch
- `Schema__Local_Config.my_branch_id` — stores the current active branch ID

**What does NOT exist:**
- No `branch switch` / `checkout <branch>` command
- No way to update `my_branch_id` in `local_config` without manual JSON editing
- No `branch create` CLI command (branch creation only happens during `init` and `clone`)

**Design constraint noted by the user:** Any changes to named branches need to be made on
a **new clone branch** for provenance. This means switching to a named branch directly
is intentionally disallowed — the correct pattern is to create a new clone branch that
tracks the named branch.

**Gap:** No CLI support for branch switching. Creating new clone branches targeting
different named branches also has no CLI command.

---

### Q11: Named branch private key — is it on the bare?

**What exists (confirmed by code):**

In `Vault__Branch_Manager.create_named_branch()`:
```python
priv_key_id = 'key-rnd-imm-' + self.key_manager.generate_key_id()
private_key, public_key = self.key_manager.generate_branch_key_pair()
self.key_manager.store_public_key(pub_key_id, public_key, read_key)
self.key_manager.store_private_key(priv_key_id, private_key, read_key)   # stored in bare
```

In `Vault__Branch_Manager.create_clone_branch()`:
```python
# NO store_private_key to bare
self.key_manager.store_private_key_locally(pub_key_id, private_key, local_dir)  # local only
```

And in `Schema__Branch_Meta`:
```python
private_key_id : Safe_Str__Key_Id = None   # None for clone branches (private key stored locally)
```

**Answer to Q11:** YES, this is correct. The only private key stored in the bare vault
structure is the **named branch's private key** (stored encrypted in `bare/keys/`).
The clone branch's private key is stored **locally only** (in `.sg_vault/local/`).

**Why:** The named branch private key needs to be accessible to any collaborator who clones
the vault and wants to write commits that are signed as coming from the named branch's
identity. The clone branch private key is ephemeral and personal — it never leaves the
local machine.

---

## 6. Implementation Phases

### Phase 1 — Simple Token + Share (immediate)

1. `Simple_Token` class + `Safe_Str__Simple_Token` safe type
2. 320-word CLI wordlist (inline Python constant in `Simple_Token__Wordlist.py`)
3. `Vault__Transfer` class (encrypt flat zip with Simple Token key, upload to Transfer API)
4. `CLI__Share` + `sgit share` CLI command
5. Tests: unit tests for token derivation with interop test vectors

### Phase 2 — Diff (enables collaboration workflow)

6. `Schema__Diff_Result` + `Schema__Diff_File` schemas
7. `Vault__Diff` class — file-level + content-level diff
   - Text files: unified diff output
   - Binary files: size + SHA-256 hash comparison only
8. `CLI__Diff` + `sgit diff` CLI command (working copy vs HEAD, vs remote, vs commit-id)
9. Tests: diff test cases including binary file handling

### Phase 3 — Init UX + Uninit (with auto-backup)

10. `Vault__Sync.init` — `allow_nonempty` parameter
11. `Vault__Sync.restore_from_backup(zip_path)` — restore from `.vault__*.zip`
12. `CLI__Vault.cmd_init` — `--existing` + `--restore` flags + interactive prompts
13. `CLI__Vault.cmd_uninit` — auto-backup then filesystem cleanup, no confirmation prompt
14. Export zip naming: `.vault__{folder_name_spaces_removed}__int(time.time()).zip`

### Phase 4 — Multi-Level Zip (Publish + Export)

15. `Schema__Vault_Archive_Manifest` schema
16. `Schema__Archive_Provenance` schema
17. New safe types: `Safe_Str__Key_Type`, `Safe_UInt__File_Count`
18. `Vault__Archive` class — builds the multi-level zip structure
19. `CLI__Publish` + `sgit publish` CLI command
20. `CLI__Export` + `sgit export` CLI command (same zip format, local file output)
21. Tests: round-trip encrypt/decrypt with test vectors

### Phase 5 — Revert / Stash (separate feature)

22. `Vault__Revert` class — restore files from a past commit
23. `Vault__Stash` class — save/restore uncommitted changes
24. New CLI commands: `sgit revert`, `sgit stash`, `sgit stash pop`

### Phase 6 — Branch Switching (separate feature, requires design)

25. Clone branch creation targeting any named branch
26. `sgit branch new <name> [--from <named-branch>]`
27. `sgit switch <branch-id>` — updates `local_config.my_branch_id`
28. Provenance design: switching always creates new clone branch, never mutates existing

---

## 7. All New Type_Safe Classes Required

| Class | Location | Purpose |
|---|---|---|
| `Safe_Str__Simple_Token` | `safe_types/` | Validates `word-word-NNNN` pattern |
| `Safe_Str__Key_Type` | `safe_types/` | `vault_key` / `none` / `pki` / `password` |
| `Safe_UInt__File_Count` | `safe_types/` | Number of files in archive |
| `Simple_Token` | `transfer/` | Derives transfer_id and AES key from token string |
| `Simple_Token__Wordlist` | `transfer/` | 320-word CLI wordlist (inline) + `generate()` |
| `Vault__Transfer` | `transfer/` | Encrypt/upload/download zip via Transfer API |
| `Vault__Archive` | `transfer/` | Build multi-level encrypted zip structure |
| `Vault__Share` | `transfer/` | High-level `share` operation |
| `Vault__Diff` | `sync/` | File-level + content-level diff |
| `Schema__Vault_Archive_Manifest` | `schemas/` | manifest.json schema (vault_archive_v1) |
| `Schema__Archive_Provenance` | `schemas/` | Branch/commit provenance inside manifest |
| `Schema__Diff_Result` | `schemas/` | Overall diff result (files changed, summary) |
| `Schema__Diff_File` | `schemas/` | Per-file diff (path, type, text/binary, content) |
| `CLI__Share` | `cli/` | `sgit share` command handler |
| `CLI__Publish` | `cli/` | `sgit publish` command handler |
| `CLI__Export` | `cli/` | `sgit export` command handler |
| `CLI__Diff` | `cli/` | `sgit diff` command handler |

---

## 8. Resolved Questions

| # | Question | Resolution |
|---|---|---|
| OQ-1 | `sgit share` upload format | **(a) raw AES-256-GCM blob** — content is already encrypted. `sgit publish` uses full multi-level zip. |
| OQ-2 | Transfer API file ID | Derived client-side: `SHA-256(token)[:12]`. No API lookup needed. |
| OQ-3 | Wordlist storage | **Inline Python constant** in `Simple_Token__Wordlist.py`. User may also pass `--token word-word-NNNN` directly. |
| OQ-4 | Export zip naming | **`.vault__{folder_name_spaces_removed}__int(time.time()).zip`** — dot prefix hides on Unix. Same format for `uninit` backup and `export`. |
| OQ-5 | Diff scope | **Both levels required:** file/folder level (added/modified/deleted) AND content-level unified diff for text files. Binary files: size + SHA-256 hash difference only. |
| OQ-6 | `sgit uninit` safety | **No confirmation prompt needed.** Auto-backup created before removal is the safety net. |

---

## 9. Branch Model Reference (for context)

The existing vault model has exactly two branch types:

- **Named branch** (`Enum__Branch_Type.NAMED`) — the "canonical" branch
  - Private key stored encrypted in `bare/keys/` (accessible to all clones)
  - HEAD ref stored in `bare/refs/`
  - Example: `branch-named-<hex>`

- **Clone branch** (`Enum__Branch_Type.CLONE`) — one per local clone
  - Private key stored only in `.sg_vault/local/` (never uploaded)
  - HEAD ref stored in `bare/refs/`
  - Example: `branch-clone-<hex>`
  - `creator_branch` field points to the named branch it was cloned from

The current workflow:
```
clone branch  --commit-->  clone HEAD
clone HEAD    --push-->    named HEAD    (via batch API + CAS)
named HEAD    --pull-->    clone HEAD    (three-way merge)
```

All new features (`share`, `publish`, `export`) operate on HEAD of the clone branch
(or the named branch, if explicitly requested).

---

---

## 10. Future Ideas (Not in Scope)

### Image Compression (`sgit compress`)
Compress images in the working directory in-place (JPEG, PNG — GIFs untouched).
Requires Pillow. Not added to `pyproject.toml`. If Pillow is not installed, print:
```
Pillow is not installed. To use image compression:
  pip install Pillow
```
Changes are in-place and not auto-committed. Deferred pending a future `sg-send-utils`
optional package that will bundle utilities with optional heavy dependencies.

### PKI Inner Key Encryption
Phase 2 expansion of the multi-level zip schema: `inner_key_type = "pki"` — encrypt
the inner zip key with a recipient's EC P-256 public key (ECIES). Allows publishing
to a named recipient without sharing a password. Depends on PKI infrastructure work
(see PKI briefs).

---

*Brief authored 2026-03-27 by Developer (Explorer team)*
*Revised 2026-03-27 — user feedback: compress deferred, uninit auto-backup, diff added, all OQs resolved*
