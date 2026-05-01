# Addendum: CLI Surgical Vault Editing — Implementation Review

**Addendum to:** `05__brief__cli-surgical-write-commands (1).md`
**Date:** 27 April 2026
**Author:** CLI Team (Dev)

---

## Overview

The brief is well-researched and the implementation sketches are close to correct.
Five changes are needed before implementation begins: one critical bug fix, one
command consolidation, one path correction, and two scope expansions from the Open
Questions list.

---

## Change 1 — Critical: `write_file()` must write to disk

### The problem

The brief specifies `write_file()` as "Does NOT touch the working directory."
This creates a broken state that prevents `sgit push` from working.

After `sgit write content/hero.md ./vault`:
1. The blob is stored in the **local object store** (`.sg_vault/bare/data/`)
2. A new HEAD commit contains `content/hero.md` in the tree
3. `content/hero.md` is **not on disk**

`push()` calls `status()` before uploading and rejects if the working copy is
dirty. `status()` computes `deleted = files_in_HEAD - files_on_disk`. In sparse
mode, deleted is further filtered to files whose blob **exists in the local
object store**. Since `write_file()` just stored the blob there, the file
registers as "deleted." Push fails:

```
RuntimeError: Working directory has uncommitted changes.
              Commit your changes before pushing.
```

The agent script at the end of the brief would fail at `sgit push`.

### The fix

`write_file()` must write the content to disk as its final step:

```python
# Keep working copy in sync so status() stays clean
dest = os.path.join(directory, path)
os.makedirs(os.path.dirname(dest), exist_ok=True)
with open(dest, 'wb') as f:
    f.write(content)
```

The brief's phrasing "Does NOT touch the working directory" was intended to
contrast with `commit()`, which *scans* the entire working directory. `write_file()`
is surgical — it modifies exactly one entry in the flat map without scanning
anything. Writing the single output file to disk is correct and necessary; it
keeps vault state consistent, status clean, and push working.

### Updated AC-3

> AC-3: `sgit write` does not **scan** the working directory — only the named
> file is added or replaced.

(Remove "Does not touch the working directory" from the spec; replace with "does
not scan".)

---

## Change 2 — `sgit read` → extend `sgit cat` instead

### The problem

`sgit cat <path>` already exists and prints decrypted file content to stdout.
`sgit read <path>` (no flags) does exactly the same thing. Two commands with
identical default behaviour will confuse users and agents alike.

### The fix

Drop the `sgit read` command. Add `--id` and `--json` as new flags to the
existing `sgit cat` command:

```bash
# Existing — unchanged
sgit cat content/hero.md ./vault
→ <decrypted content>

# New flag — blob ID only, zero network
sgit cat content/hero.md ./vault --id
→ obj-cas-imm-aaa111

# New flag — full metadata, zero network
sgit cat content/hero.md ./vault --json
→ { "path": "content/hero.md", "blob_id": "obj-cas-imm-aaa111",
    "size": 1024, "content_type": "text/markdown", "fetched": true }
```

**Implementation:** `cmd_cat` in `CLI__Vault.py` already calls `sync.sparse_cat()`.
Add an early branch: if `--id` or `--json`, call `sync.sparse_ls(directory,
path=args.path)` instead and print from the first matching entry. Same zero-network
path as proposed for `cmd_read`.

**Agent script update:** Replace `sgit read` with `sgit cat` throughout. Reads
better — `cat` is the established Unix verb for "print file content."

### Updated blast radius

Remove `sgit_ai/cli/CLI__Main.py` `read_parser` and `CLI__Vault.py` `cmd_read`.
Add `--id` and `--json` to the existing `cat_parser` and `cmd_cat`. Net: same
functionality, one fewer command.

### Updated acceptance criteria

| # | Original | Replacement |
|---|----------|-------------|
| AC-5 | `sgit read … --id` prints blob ID | `sgit cat … --id` prints blob ID |
| AC-6 | `sgit read …` prints decrypted content | Already satisfied by existing `sgit cat` |
| AC-7 | `sgit read … --json` outputs valid JSON | `sgit cat … --json` outputs valid JSON |

---

## Change 3 — Path correction: `.sgit/` → `.sg_vault/local/`

### The problem

The brief specifies the read-only clone flag file as:

```
.sgit/clone-mode.json
```

`.sgit/` does not exist in this project. All local clone state lives under:

```
.sg_vault/local/
```

### The fix

Store the file at:

```
.sg_vault/local/clone_mode.json
```

Add `clone_mode_path(directory) -> str` to `Vault__Storage`, following the
existing pattern of `local_config_path`, `remotes_path`, `tracking_path`,
`push_state_path`:

```python
def clone_mode_path(self, directory: str) -> str:
    return os.path.join(self.local_dir(directory), 'clone_mode.json')
```

Update AC-16 accordingly.

---

## Change 4 — OQ-4: Multi-file atomic write — include in scope

### The recommendation

The brief recommends deferring "write several files in one commit atomically."
This should be in scope for the initial release.

### Why

The agent workflow almost always updates content and instructions together:

```bash
# Write new hero content
NEW_ID=$(cat hero.md | sgit write content/hero.md ./vault)

# Update instructions to reference the new blob — SEPARATE COMMIT
echo "$INSTRUCTIONS" | sgit write instructions/home.json ./vault
```

Between these two commits there is a window where the vault is inconsistent:
instructions still reference the old hero blob. If push succeeds after commit 1
but the agent is interrupted before commit 2, the server has new content that
nothing points to — and instructions still reference the old content.

Atomic multi-file write closes this window and is the natural primitive for
content-plus-instructions updates.

### Proposed interface

```bash
# Write multiple files in one commit (stdin per --also)
cat hero.md | sgit write content/hero.md ./vault \
    --also instructions/home.json:/tmp/updated-instructions.json \
    --message "hero v2 + instructions"

# Or: two --file flags with explicit paths
sgit write content/hero.md ./vault --file /tmp/hero.md \
    --also instructions/home.json:/tmp/instructions.json
```

### Implementation cost

`write_file()` already operates on the flat map before calling `build_from_flat()`.
Supporting multiple files means accumulating all entries into the flat map before
building the tree — approximately 5 extra lines. The commit and push path are
unchanged.

Simplest API: accept `--also vault_path:local_file` zero or more times. Read each
local file, encrypt and store each blob, update flat map for each, then build tree
and create one commit.

---

## Change 5 — OQ-1: `--push` flag — include in scope

### The recommendation

The brief marks `sgit write --push` as an open question. It should be in scope.

### Why

The agent workflow is almost always write-then-push. `--push` makes the common
case one command and eliminates the status-check friction:

```bash
# Current (two commands)
NEW_ID=$(cat hero.md | sgit write content/hero.md ./vault)
sgit push ./vault

# With --push (one command)
NEW_ID=$(cat hero.md | sgit write content/hero.md ./vault --push)
```

### Implementation

Add `--push` flag to `write_parser`. In `cmd_write`, after `sync.write_file()`,
call `sync.push(args.directory, on_progress=progress.callback)` if `args.push`.
Print `Pushed.` (or push summary) to stderr so stdout remains just the blob ID
for `$()` capture.

---

## Minor Notes

### `write_file()` content-hash optimisation

The existing `Vault__Sub_Tree.build()` skips re-encryption when content is
unchanged (checks `content_hash` against the existing flat map entry). `write_file()`
should do the same: if the incoming content's hash matches the existing entry's
`content_hash`, return the existing `blob_id` without creating a new commit. Avoids
spurious commits when an agent writes the same content twice.

### Mixed workflow warning

Document clearly: `sgit write` and `sgit commit` should not be mixed on the same
vault clone. `sgit write` is the programmatic workflow (write directly to vault
HEAD without scanning the directory). `sgit commit` is the human-edit workflow
(scan working directory, snapshot all changes). Using both on the same directory
will produce unexpected results because each has a different view of what "the
current state" is.

---

## Updated Blast Radius

| File | Change |
|------|--------|
| `sgit_ai/sync/Vault__Sync.py` | Add `write_file()` — writes blob + tree + commit + disk |
| `sgit_ai/cli/CLI__Main.py` | Add `write_parser` (with `--also`, `--push`); add `--id`/`--json` to `cat_parser`; add `--ids`/`--json` to `ls_parser`; add `--read-key` to `clone_parser` |
| `sgit_ai/cli/CLI__Vault.py` | Add `cmd_write`; extend `cmd_cat` (--id, --json); extend `cmd_ls` (--ids, --json); extend `cmd_clone` (--read-key path, read_key output); extend `cmd_info` (read_key + write availability); extend `cmd_derive_keys` (read-only awareness); add early read-only guard to `cmd_write`, `cmd_commit`, `cmd_push` |
| `sgit_ai/sync/Vault__Storage.py` | Add `clone_mode_path(directory)` |
| `sgit_ai/crypto/Vault__Crypto.py` | Add `import_read_key(read_key_b64url) -> bytes` |
| `sgit_ai/cli/CLI__Token_Store.py` | Add `load_clone_mode(directory) -> dict` |
| ~~`sgit read` command~~ | Removed — functionality absorbed into `sgit cat --id` / `--json` |

---

## Updated Acceptance Criteria (changes only)

| # | Updated criterion |
|---|-------------------|
| AC-3 | `sgit write` does not **scan** the working directory — only the named file is added or replaced on disk |
| AC-5 | `sgit cat path --id` prints blob ID with zero network calls |
| AC-6 | `sgit cat path` (existing behaviour, unchanged) prints decrypted content |
| AC-7 | `sgit cat path --json` outputs valid JSON with path, blob_id, size, content_type, fetched |
| AC-16 | A read-only clone has `.sg_vault/local/clone_mode.json` with `"mode": "read-only"` |
| AC-21 (new) | `sgit write path --also path2:file2 --also path3:file3` creates one commit containing all named files |
| AC-22 (new) | `sgit write path --push` pushes immediately; stdout contains only the blob ID |
