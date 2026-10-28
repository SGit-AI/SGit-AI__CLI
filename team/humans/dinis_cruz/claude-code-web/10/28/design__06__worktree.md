# Design 06: `sgit worktree` (roadmap 2.13, priority 2)

**Status:** design, not built. **Date:** 28 Oct 2026. **Roadmap:** `roadmap__git-parity.md` item 2.13, approach A
(agreed with Dinis: shared objects only, Git's *alternates*; no shared refs). **Code read at:** `3a1d72a` on
`claude/charming-babbage-5hzcxq`. Every `file:line` below is at that commit.

**In one paragraph.** `sgit worktree add <path>` makes a second working copy of the vault in seconds, with no network.
The new folder is a real sgit clone: its own `.sg_vault/local/` (clone branch, signing key, config, caches, merge
state, reflog) and its own small `.sg_vault/bare/` (branch index, refs, public keys). Its object store has no objects
of its own at first. It reads objects from the main vault's store, then from the network, in that order. New objects
are written to the worktree's own store and never to the main one. Merging works as today: push, then
`branch merge`. Phase 2 adds `branch merge` from another local worktree without a push.

---

## 1. Summary and the exact Git behaviour matched

### 1.1 What Git does (checked on git 2.43.0, installed in this container)

| Git piece | Where it lives | What it holds |
|---|---|---|
| Linked worktree folder | `<wt>/.git` is a **file**, one line | `gitdir: /main/.git/worktrees/<name>` |
| Per-worktree admin folder | `/main/.git/worktrees/<name>/` | `HEAD`, `ORIG_HEAD`, `index`, `logs/`, `commondir` (`../..`, back to the main `.git`), `gitdir` (path of `<wt>/.git`), `locked` when locked |
| Shared state | the main `.git` | objects, packs, `refs/heads`, `refs/tags`, config, hooks |
| One-branch rule | `git worktree add ../wt2 feat` when `feat` is checked out elsewhere | `fatal: 'feat' is already used by worktree at '…/wt'` |
| Lock | `git worktree lock <wt> --reason R` | writes `.git/worktrees/<name>/locked` containing R; `prune` and `remove` skip it |
| Prune | `git worktree prune` (also run by `gc`, `gc.worktreePruneExpire`, default 3 months) | deletes admin folders whose `gitdir` points to a path that no longer exists, unless locked |
| List | `git worktree list [--porcelain]` | path, HEAD, branch, `locked <reason>` |

| Git alternates piece | Where | Behaviour |
|---|---|---|
| Pointer | `<repo>/.git/objects/info/alternates` | one absolute path per line, e.g. `/main/.git/objects` (verified: `git clone --reference main` writes exactly that) |
| Read path | object lookup | own objects first, then each alternate in order |
| Write path | new objects | always into the repo's own `objects/`; an alternate is never written |
| `clone --reference R` | clone | borrows R's objects; only what R lacks comes over the network |
| `clone --reference R --dissociate` | clone | borrows during the clone, then copies what it uses and deletes the alternates file (verified: `objects/info/` holds only `packs` afterwards) |
| The documented danger | `git-clone(1)`, `--shared` | if the source repository prunes or repacks away an object the borrower needs, the borrower is corrupt |

### 1.2 What sgit matches, and how

| Git behaviour | sgit worktree (this design) | Same or different |
|---|---|---|
| Second working copy from one store, created in seconds | `sgit worktree add <path>`: a clone whose objects are borrowed from the main store | Same effect |
| Objects shared | read-only borrowing through `.sg_vault/local/alternates.json` (Git's alternates) | Same mechanism |
| Refs shared (a commit in one worktree is visible in the other at once) | **Not shared.** Each worktree is its own clone with its own refs, as every sgit clone is. A commit reaches the main folder by push + `branch merge` (phase 1) or by `branch merge --worktree <name>` (phase 2) | Different, on purpose (section 5.9) |
| One branch per worktree | Not needed. Each worktree has its own clone branch (every sgit clone does), so no two working copies ever move the same local ref. Two worktrees on the same *named* branch behave like two clones of it: both push, both merge | Safer than Git's rule, no refusal needed |
| `worktree list / remove / prune / lock / unlock` | the same five subcommands, same meaning | Same |
| `clone --dissociate` | `sgit worktree dissociate <name>`: copy every borrowed object the worktree can reach into its own store, then drop the pointer | Same |
| Danger: the source prunes objects | sgit has no prune today (roadmap 2.10). Any future prune or a destructive command in the main vault (rekey, move, uninit) must refuse while worktrees are registered (section 6) | Same danger, closed by guards |

---

## 2. Scope and non-goals

**In scope, phase 1 (2–3 days):**

1. `sgit worktree add <path> [--name N] [--branch <named> | -b <new named>] [--path F ...] [--no-checkout] [--vault-key K]`.
2. `sgit worktree list [--json]`, `remove <name|path> [--force]`, `prune [--dry-run]`, `lock <name|path> [--reason R]`,
   `unlock <name|path>`, `dissociate <name|path>`.
3. The read path: `Vault__Object_Store` reads through one alternate store, verifying each borrowed object by its
   content address.
4. Guards in the main vault: `vault uninit`, `vault rekey`, `vault move`, `migrate apply` refuse while worktrees are
   registered (names listed, `--force` or `worktree remove` first). Guards in a worktree: `vault uninit` points to
   `worktree remove`; `vault backup` materialises borrowed objects into the zip; a first push of a never-pushed vault
   is refused.
5. The working-copy scan never descends into a nested vault (a sub-folder that holds its own `.sg_vault`). This
   matters when a worktree is created inside the main working copy, and it fixes a latent bug for any nested clone.

**Phase 2 (1–1.5 days):** `sgit branch merge --worktree <name|path>`: merge another local worktree's clone head
without pushing. It imports the commits and objects it needs, verified by content address, plus the other worktree's
public key, then runs the existing pull merge step.

**Non-goals:**

| Not doing | Why |
|---|---|
| Git-style shared refs (`commondir`) | Section 5.9: 81 hand-built paths to reroute and ref locking to add, for a gain phase 2 delivers more cheaply |
| Writing into the main store from a worktree | Section 5.4 |
| Worktrees of a read-only clone | A read-only clone (`clone_mode.json`, no write key) has no clone branch to fork. Refused in v1 with a message; open decision D6 |
| Worktrees across machines or network paths | The pointer is an absolute local path; a network share works if the OS presents it as a path, untested |
| Sharing the scan cache | It records paths, mtimes and inodes of one working copy: meaningless in another |
| Submodules | roadmap 2.15 |

---

## 3. CLI surface

### 3.1 Placement (Rule 9) — decision D1

Git has `git worktree` at the top level, and agents type it from habit. A worktree is about working copies, which
are daily-use, not about "the vault as a whole". **Recommendation: top-level `sgit worktree`**, with
`TOP_LEVEL_COMMANDS` in `tests/unit/cli/test_CLI__B07__Namespace_Moves.py:104` gaining `'worktree'` in the same commit
(a deliberate edit, as Rule 9 asks). The alternative is `sgit vault worktree …`. The rest of this section assumes top
level. `sgit help all` (`sgit_ai/cli/CLI__Main.py:1491`) must list it (it already omits several commands; that list
is fixed separately).

### 3.2 Commands

| Command | Arguments and flags | Effect |
|---|---|---|
| `sgit worktree add <path>` | `--name N` (default: basename of `<path>`, made safe by `Safe_Str__Worktree_Name`) · `--branch <named>` (track this existing named branch; default: the named branch the main clone tracks) · `-b <new named>` (create a new named branch from the starting commit, as `branch new` does) · `--from <rev>` (start commit; default `HEAD` of the main clone; any revision `history` accepts) · `--path F` (repeatable: a scoped worktree, as `clone --path`) · `--no-checkout` (selective working copy, as `clone --no-checkout`) · `--vault-key K` or `-` for stdin (only when the main clone is bare, i.e. holds no key) · `--json` | Creates the worktree (section 5.6). Prints its name, path, clone branch, named branch, start commit, files written, time |
| `sgit worktree list` | `--json` · `--porcelain` | One line per worktree: name, path, named branch, head (short id), state (`ok`, `missing`, `locked: <reason>`), plus the main vault as the first line, as Git does |
| `sgit worktree remove <name|path>` | `--force` | Refuses when the worktree has uncommitted changes, unpushed commits, a merge in progress, or is locked; `--force` overrides all but `locked` (Git needs `--force --force` for a locked one; sgit asks for `unlock` first, which is clearer). Deletes the worktree folder (working copy and `.sg_vault/`) and its registry entry |
| `sgit worktree prune` | `--dry-run` | Drops registry entries whose path no longer holds a worktree of this vault (folder gone, or its `alternates.json` no longer points here), unless locked |
| `sgit worktree lock <name|path>` | `--reason R` | Marks the entry locked (a removable disk, a long-running agent): `prune` and `remove` skip it |
| `sgit worktree unlock <name|path>` | | Clears the lock |
| `sgit worktree dissociate <name|path>` | run from anywhere | Copies every borrowed object reachable from the worktree's refs into its own store (each verified), then deletes its `alternates.json` and the registry entry: it becomes an ordinary clone |
| `sgit branch merge --worktree <name|path>` (phase 2) | `--merge lines|files` once design 01 lands | Merges that worktree's clone head into this clone (section 5.8) |

`<name|path>` resolves first as a registry name, then as a path (absolute or relative to the current directory).
Every subcommand except `add` and phase 2 can run from the main folder or from any of its worktrees. Inside a
worktree, the registry used is the main vault's, found through `alternates.json`.

### 3.3 Output

```
$ sgit worktree add ../agent-7 -b agent-7
Worktree agent-7 at /work/agent-7
  vault       y8pwtjlw
  branch      agent-7 (new, from current at 3f9a1c2)
  clone       branch-clone-5e1b… (registered on first push)
  objects     borrowed from /work/vault (0 downloaded)
  files       9,404 written in 2.1 s
```

```
$ sgit worktree list
/work/vault       3f9a1c2  current   (main)
/work/agent-7     3f9a1c2  agent-7
/work/agent-8     b07e2d4  current   locked: long run
/mnt/usb/agent-9  -        -         missing (sgit worktree prune)
```

`--porcelain` prints Git's shape: blocks of `worktree <path>`, `HEAD <commit id>`, `branch <named>`, `locked <reason>`,
`prunable <reason>`, separated by a blank line.

### 3.4 `--json` shapes

`worktree add --json`:

```json
{ "name": "agent-7", "path": "/work/agent-7", "main": "/work/vault", "vault_id": "y8pwtjlw",
  "named_branch": "agent-7", "named_branch_new": true, "clone_branch_id": "branch-clone-5e1b…",
  "start_commit": "obj-cas-imm-3f9a1c2…", "files_written": 9404, "objects_downloaded": 0,
  "scope_paths": [], "selective": false, "seconds": 2.1 }
```

`worktree list --json`: `{"main": {...}, "worktrees": [{"name", "path", "head", "named_branch", "clone_branch_id",
"created_at", "locked", "lock_reason", "state"}]}`, where `state` is `ok | missing | foreign`. `foreign` means the
folder exists but its `alternates.json` points to another main vault.

### 3.5 Exit codes

As the rest of the CLI (`sys.exit(1)` is used 116 times in `sgit_ai/cli/*.py`, `sys.exit(2)` for argparse misuse,
`130` for Ctrl-C): `0` success, `1` refused or failed (the message says why and names the remedy), `2` bad arguments.
`remove` and `prune --dry-run` exit `0` when there is nothing to do.

---

## 4. How the code works today

| Area | Code | What matters here |
|---|---|---|
| Layout constants | `sgit_ai/storage/Vault__Storage.py:6-17` | `.sg_vault/`, `bare/{data,refs,keys,indexes,pending,branches,cache}`, `local/`, `vault_key` |
| Path helpers | `Vault__Storage.py:24-31` (`sg_vault_dir`, `bare_dir`, `local_dir`), `:83` `is_vault`, `:87` `find_vault_root` | Every helper is `os.path.join(directory, '.sg_vault', …)`; no indirection exists |
| Vault root detection | `Vault__Storage.find_vault_root` `:87` and `Vault__Context.detect` `sgit_ai/core/Vault__Context.py:29-56` | Walk up until a folder holds a `.sg_vault/` **directory**. A worktree with a real `.sg_vault/` directory needs no change here |
| Object store | `sgit_ai/storage/Vault__Object_Store.py:47-190` | `load` `:106`: loose file → kept packs (`packs()` `:55`) → `Vault__Object_Missing_Error`. `exists` `:118`, `size_of` `:124`, `all_object_ids` `:157` (loose ∪ packed), `loose_object_ids` `:165`, `resolve_id` `:135` (prefix search over `all_object_ids`), `verify_integrity` `:180` |
| Writes | `store` `:68`, `store_raw` `:82`, `store_at` `:96`; `Vault__Verified_Write.save` `sgit_ai/storage/Vault__Verified_Write.py:72` (every download path) | Plain `open(path, 'wb')`: **not atomic**. A reader in another process can see a half-written file. Loose reads (`load` `:106`) do not re-verify; only kept-pack reads do (`Vault__Pack_Store`, "verified on every read") |
| CAS guard | `store` `:68-80` | An existing id with different bytes raises `Vault__Object_Collision_Error`; identical bytes are a no-op |
| Kept packs | `sgit_ai/storage/Vault__Pack_Store.py` (`db_path` `:52` = `<sg>/local/pack-store.sqlite`, `packs_dir` `:55` = `<sg>/bare/packs`, `remove_pack` `:276`) | The pack table is per `vault_path`. A `Vault__Object_Store` built on the main `sg_dir` brings the main pack store with it |
| Construction | `Vault__Object_Store(` appears 48 times in 30 files (6 in `Vault__Packs.py`, 4 each in `Vault__Pack_Index__Reader.py` and `Vault__Pack_Index.py`, 3 in `Vault__Bare.py`, …) | The alternate must be found **inside** the object store, lazily, as `packs()` is. Threading it through 48 constructors is not an option |
| Clone workflow | `sgit_ai/workflow/clone/Workflow__Clone.py` steps: `Derive_Keys`, `Check_Directory`, `Download_Index`, `Download_Branch_Meta`, `Bulk_Fetch`, `Walk_Commits`, `Walk_Trees`, `Download_Blobs`, `Verify_Signatures`, `Create_Clone_Branch`, `Extract_Working_Copy`, `Setup_Local_Config` | The worktree flow reuses the last four as they are and replaces the network steps with local copies |
| Clone branch creation | `Step__Clone__Create_Clone_Branch` → `Vault__Branch_Manager.create_clone_branch` `sgit_ai/storage/Vault__Branch_Manager.py:49-74` | New `branch-clone-<16 hex>`, ref `ref-pid-snw-<12 hex>`, key pair: public key to `bare/keys/key-rnd-imm-…` (encrypted under the read key), private `.pem` to `local/` (0600). The index entry is written locally; `pending_registration.json` registers it on first push |
| Local config | `Step__Clone__Setup_Local_Config`; `Schema__Local_Config` (`sgit_ai/schemas/Schema__Local_Config.py:9-22`) | `my_branch_id`, `sparse`, `pack_store`, `scope_paths`, `shallow_boundaries`, `last_remote_head`, … The vault key goes through `Vault__Storage.write_private` (0600, `Vault__Secret_File`) |
| Files under `local/` | `config.json`, `vault_key`, `<key id>.pem`, `remotes.json`, `token`, `base_url`, `remote_heads.json` (`Vault__Sync__Base.py:170`), `reflog.jsonl`, `merge_state.json`, `scan-cache.json`, `flat-cache/<tree>.json` (`Vault__Sub_Tree.py:13`), `pack-store.sqlite`, `index/generations.json`, `checkout.json`, `last-pull.json`, `pending_registration.json`, `push_state.json`, `tracking.json`, `stash-meta.json`, `move-history.json`, `migrations.json`, `trace.jsonl`, `lazy-fetch.log`, `debug/` | Section 5.6 lists which are copied, rebuilt or left out |
| Local transport | `sgit_ai/network/api/Vault__Backend__Local.py` (`--transport local`, read-only folder) | `clone --transport local <main>/.sg_vault` would work but copies every object and makes the folder the remote. Not used |
| Attach | `sgit_ai/core/actions/lifecycle/Vault__Attach.py` | Binds a key to an existing `bare/` (validate first, write nothing on a wrong key). Its key-validation rule is reused |
| First push | `Vault__Sync__Push._is_first_push` `:773` and `_upload_bare_to_server` `:840` | A first push walks the **own** `bare/` dir and uploads every file. A worktree of a never-pushed vault would upload an incomplete store: refused (section 7) |
| Push object reads | `Vault__Batch` and `Vault__Sync__Push` read bytes through `obj_store.load` | Borrowed objects are read and uploaded like own ones |
| Uninit | `Vault__Sync__Lifecycle.uninit` `:95-129` | Backup, then `shutil.rmtree(sg_dir)`. On a worktree that removes only the worktree's own `.sg_vault` |
| Rekey wipe | `Vault__Sync__Lifecycle.rekey_wipe` `:52` | `secure_rmtree(sg_dir)`: destroys the main store that worktrees borrow from |
| Merge entry | `Vault__Sync.merge_branch` `sgit_ai/core/Vault__Sync.py:230` → `Vault__Sync__Pull.pull(merge_from=…)` `:80`; `Step__Pull__Load_Branch_Info` `:77-85` resolves `merge_from` to a named branch from the server's index | Phase 2 adds a local source |
| Scan | `Vault__Sync__Base._scan_local_directory` `:519`, walk at `:555-562` | Skips ignored dirs and links. A sub-folder that is itself a vault root (holds `.sg_vault/`) is **descended into**: its `.sg_vault/` is skipped (`ALWAYS_IGNORED_DIRS`, `Vault__Ignore.py:6`) but its files are scanned and would be committed |
| Path guard | `Vault__Path_Guard.is_protected` `sgit_ai/storage/Vault__Path_Guard.py:95` | Any segment named `.sg_vault`, `.sg_vault_new`, `.sg_vault_old_*`, `.git` (and spellings) is refused from vault data, file or folder. Vault content therefore cannot plant `sub/.sg_vault/local/alternates.json` |

### 4.1 Why not Git-style shared refs: the counts (verified)

`grep -rn "'\.sg_vault'" sgit_ai --include=*.py`, excluding `Vault__Storage.py`: **52 occurrences in 22 files**.

| File | Count |
|---|---|
| `sgit_ai/cli/CLI__Token_Store.py` | 9 |
| `sgit_ai/cli/CLI__Vault.py` | 7 |
| `sgit_ai/plugins/dev/workflow/CLI__Dev__Workflow.py` | 4 |
| `sgit_ai/core/actions/status/Vault__Sync__Status.py` | 4 |
| `sgit_ai/core/Vault__Ignore.py` | 3 |
| `sgit_ai/cli/CLI__Serve.py` | 3 |
| `sgit_ai/workflow/Workflow__Runner.py`, `sgit_ai/core/serve/Vault__Serve.py`, `sgit_ai/core/actions/publish/Vault__Publish.py`, `sgit_ai/core/actions/merge/Vault__Merge.py`, `sgit_ai/core/Vault__Sync__Base.py`, `sgit_ai/cli/CLI__Main.py` | 2 each |
| `Step__Move__Delete_Source.py`, `Vault__Path_Guard.py`, `Dev__Tree__Graph.py`, `Migration__Runner.py`, `Vault__Sync__Push.py`, `Vault__Sync__Move.py`, `Vault__Restore.py`, `Vault__Secret_Guard.py`, `Vault__Context.py`, `CLI__Create.py` | 1 each |

`grep -rn "os.path.join([^)]*'bare'"`, same exclusion: **29 occurrences in 18 files**.

| File | Count |
|---|---|
| `sgit_ai/workflow/move/steps/Step__Move__Build_Temp_Vault.py` | 9 |
| `Vault__Publish.py`, `Vault__Sync__Base.py`, `CLI__Serve.py` | 2 each |
| `Step__Move__Write_Sentinel_Commits.py`, `Step__Move__Push_To_Target.py`, `Vault__Ref_Manager.py`, `Vault__Pack_Store.py`, `Vault__Object_Store.py`, `Vault__Key_Manager.py`, `Vault__Serve__Mirror.py`, `Vault__Pack_Maintain.py`, `Vault__Attach.py`, `Vault__Sync__Upload_Objects.py`, `Vault__Backup.py`, `Vault__Sync.py`, `Vault__Context.py`, `Vault__Bare.py` | 1 each |

On top of these, string paths such as `'bare/data/'` appear in about 60 more places. Most are wire file ids (the
server's path), but `Step__Move__Build_Temp_Vault.py:103` and `Step__Move__Validate_Local.py:61` use them on disk.

Shared refs would mean: every one of those 81 paths goes through one resolver, `bare/refs`, `bare/indexes` and
`bare/keys` become shared between processes, and the ref, index and baseline writes need cross-process locks. Those
writes are compare-and-swap on the server today and unlocked on disk (`save_branch_index`
`Vault__Branch_Manager.py:76-86` writes in place). That is a 1–2 week change touching most commands, with a
concurrency bug class sgit does not have today. Approach A changes the object read path in one class, plus about 10
small guards.

---

## 5. Design

### 5.1 On-disk layout

```
/work/vault/                        main clone (unchanged layout)
  .sg_vault/bare/{data,refs,keys,indexes,packs,…}
  .sg_vault/local/
      worktrees.json                NEW: registry of this vault's worktrees (Schema__Worktree__Registry)
      …everything as today

/work/agent-7/                      worktree: a real clone
  .sg_vault/bare/
      data/                         own objects only (new commits, trees, blobs; fetched objects the main lacks)
      refs/                         copied at add time, then its own
      keys/                         copied at add time (public keys, encrypted), then its own
      indexes/<branch index id>     copied at add time, then its own
  .sg_vault/local/
      alternates.json               NEW: the pointer to the main store (Schema__Worktree__Alternates)
      config.json  vault_key  <key>.pem  remotes.json  token  base_url  remote_heads.json  …
  <working copy files>
```

There are no symlinks. The worktree's `.sg_vault/` is a real directory, so `find_vault_root` and
`Vault__Context.detect` work unchanged. A worktree is an ordinary clone plus one file.

### 5.2 Schemas and safe types (new)

| Name | File | Definition |
|---|---|---|
| `Safe_Str__Worktree_Name` | `sgit_ai/safe_types/Safe_Str__Worktree_Name.py` | `regex = re.compile(r'[^a-zA-Z0-9._\-]')`, `max_length = 64`, `allow_empty = False`, `trim_whitespace = True`. Leading `.` is refused by `Vault__Worktree` (no `.sg_vault`-like names) |
| `Safe_Str__Worktree_Lock_Reason` | `sgit_ai/safe_types/Safe_Str__Worktree_Lock_Reason.py` | `max_length = 200`, `allow_empty = True`, `trim_whitespace = True`, control characters replaced |
| `Enum__Worktree_State` | `sgit_ai/safe_types/Enum__Worktree_State.py` | `OK = 'ok'`, `MISSING = 'missing'`, `FOREIGN = 'foreign'` |
| `Schema__Worktree__Alternates` | `sgit_ai/schemas/worktree/Schema__Worktree__Alternates.py` | `schema : Safe_Str__Schema_Version = None` (`'worktree_alternates_v1'`); `main_sg_dir : Safe_Str__File_Path = None` (absolute path of the main `.sg_vault`); `worktree_name : Safe_Str__Worktree_Name = None`; `branch_index_id : Safe_Str__Index_Id = None` (the vault's branch index file id: the identity check, 5.3); `created_at : Safe_UInt__Timestamp` |
| `Schema__Worktree__Entry` | `sgit_ai/schemas/worktree/Schema__Worktree__Entry.py` | `name : Safe_Str__Worktree_Name = None`; `path : Safe_Str__File_Path = None` (absolute); `clone_branch_id : Safe_Str__Branch_Id = None`; `named_branch : Safe_Str__Branch_Name = None`; `created_at : Safe_UInt__Timestamp`; `locked : bool = False`; `lock_reason : Safe_Str__Worktree_Lock_Reason = None` (new: one line, 200 chars, printable characters only) |
| `Schema__Worktree__Registry` | `sgit_ai/schemas/worktree/Schema__Worktree__Registry.py` | `schema : Safe_Str__Schema_Version = None` (`'worktree_registry_v1'`); `worktrees : list[Schema__Worktree__Entry]` |
| `Schema__Worktree__Add__State` | `sgit_ai/schemas/workflow/worktree/Schema__Worktree__Add__State.py` | The workflow state: the clone-state fields the reused clone steps read (`directory`, `sg_dir`, `vault_id`, `vault_key`, `read_key_hex`, `branch_index_file_id`, `index_id`, `named_branch_id`, `named_ref_id`, `named_commit_id`, `clone_branch_id`, `clone_ref_id`, `clone_public_key_id`, `scope_paths`, `shallow_boundaries`, `sparse`, `pack_store`) plus `main_directory`, `main_sg_dir`, `worktree_name`, `start_commit_id`, `new_named_branch`. **Alternative, preferred if the steps type-check their input:** subclass `Schema__Clone__State` and add the five fields, so `Step__Clone__Create_Clone_Branch`, `Step__Clone__Verify_Signatures`, `Step__Clone__Extract_Working_Copy` and `Step__Clone__Setup_Local_Config` run unchanged |

Every schema gets the round-trip test (`cls.from_json(obj.json()).json() == obj.json()`). Both JSON files are written
through `Vault__Storage.write_private` (0600, temp file, fsync, rename): `alternates.json` names a path to a folder
holding a key, and `worktrees.json` names paths.

### 5.3 The read path (one class changes)

`Vault__Object_Store` (`sgit_ai/storage/Vault__Object_Store.py`) gains:

| Member | Kind | Behaviour |
|---|---|---|
| `alternate : object = None` | field | the main vault's `Vault__Object_Store` (its own `packs()` included), or None |
| `alternates_probed : bool = False` | field | probed once per instance, as `packs_probed` is (`:51-53`) |
| `alternate_store(self)` | method | First call: read `<vault_path>/local/alternates.json` through `Vault__Alternates.load`. When it exists and validates, build `Vault__Object_Store(vault_path=main_sg_dir, crypto=self.crypto, id_hex_len=self.id_hex_len)`. An alternate of an alternate is never followed: the main store's own probe is disabled (`alternates_probed=True` when constructed as an alternate), so a chain or a loop cannot form |
| `load(self, object_id)` | changed | own loose file → own kept packs → `alternate.load(object_id)` **then verified**: `self.crypto.object_id_matches(object_id, data)`. A mismatch (a half-written file, a changed disk) counts as missing → `Vault__Object_Missing_Error` as today, so every fail-soft caller fetches from the network as it already does |
| `exists(self, object_id)` | changed | own loose → own packs → `alternate.exists` |
| `size_of(self, object_id)` | changed | same order |
| `all_object_ids(self)` | changed | own ∪ alternate. Callers that list for presence (`resolve_id` `:135`, `Vault__Revision.py:136`, `Vault__Incoming_Check.py:88`, `Step__Clone__Verify_Signatures.py:81`, `Vault__Inspector.py:330`, `Vault__Pack_Maintain.py:76`) then see borrowed objects as present, which is the Git semantics |
| `own_object_ids(self)` | new | own loose ∪ own packs: for `dissociate`, backup counting, `worktree list` stats |
| `is_borrowed(self, object_id)` | new | `not own exists and alternate exists`: for fsck reporting and dissociate |
| `verify_integrity` `:180` | unchanged | goes through `load`, so it covers borrowed objects |

`Vault__Alternates` (new, `sgit_ai/storage/Vault__Alternates.py`, Type_Safe) does all pointer handling:

| Method | Behaviour |
|---|---|
| `path(sg_dir) -> str` | `<sg_dir>/local/alternates.json` |
| `load(sg_dir) -> Schema__Worktree__Alternates or None` | Read with `Vault__Path_Guard().read_regular` (O_NOFOLLOW, regular file only, the TM-F27 rule). Parse. Return None on any error: a broken pointer means "no alternate", never a crash, and the network fallback still works |
| `validate(sg_dir, alt) -> str` | `''` when usable, else the reason. Checks, in order: `main_sg_dir` is absolute; it is a directory and not a link (`Vault__Path_Guard.is_link`); `main_sg_dir != sg_dir` (no self-loop); `<main_sg_dir>/bare/indexes/<branch_index_id>` exists (**identity check**: the branch index file id is derived from the read key and vault id, so only the same vault has it); `<main_sg_dir>/local/alternates.json` does not exist (the main is not itself a worktree: no chains) |
| `write(sg_dir, alt)` | through `Vault__Storage.write_private` |
| `remove(sg_dir)` | delete the file (used by `dissociate`) |
| `main_directory(alt) -> str` | `dirname(main_sg_dir)` |

**Why verify borrowed reads when own loose reads are not verified:**
- the main store is written by another process, non-atomically (`store` `:68`, `Verified_Write.save` `:72`), so a
  half-written file is a real possibility;
- the main folder may be on another disk that changes under the worktree;
- the cost is one SHA-256 per borrowed object, about 1 GB/s, the same rule kept packs already follow.

A mismatch is reported once per run as a warning (`object <id> in the main store does not match its id; fetched
from the server instead`).

### 5.4 The write path: new objects go to the worktree's own store

**Decision: own store only.** Git never writes into an alternate, and the same reasons hold:

1. **Ownership.** The main folder's store belongs to the main clone. Two processes writing into one `bare/data/`
   meet the non-atomic writes above and the CAS guard's read-compare (`store` `:70-75`), which would raise a false
   collision on a half-written file.
2. **Removal is clean.** `worktree remove` deletes the worktree folder and everything it created. Nothing the
   worktree wrote stays behind in the main store.
3. **Kept packs.** A `--pack-store` main has a SQLite table per clone (`local/pack-store.sqlite`). A worktree
   writing loose objects into the main `bare/data/` would bypass that table's intake rules.
4. **Cost.** The duplicate is only what the worktree itself creates or fetches: its own commits, plus what it pulls
   that the main has not pulled yet.

A pull in the worktree downloads only objects missing from **both** stores, because `exists` covers the alternate.
When the main clone has already pulled, the worktree's pull downloads only refs.

### 5.5 The registry in the main vault

`Vault__Worktree_Registry` (new, `sgit_ai/storage/Vault__Worktree_Registry.py`):

| Method | Behaviour |
|---|---|
| `path(main_sg_dir)` | `<main_sg_dir>/local/worktrees.json` |
| `load(main_sg_dir) -> Schema__Worktree__Registry` | an empty registry when absent; an unreadable file raises (fail closed: a guard must never read "no worktrees" from a corrupt file, the TM-F23 rule) |
| `save(main_sg_dir, registry)` | `write_private` (atomic) |
| `add(main_sg_dir, entry)` | refuses a duplicate name or path |
| `remove(main_sg_dir, name)` | |
| `find(main_sg_dir, name_or_path) -> entry or None` | name first, then normalised absolute path |
| `state_of(main_sg_dir, entry) -> Enum__Worktree_State` | `MISSING` when `<path>/.sg_vault` is absent; `FOREIGN` when the worktree's `alternates.json` does not point back to `main_sg_dir`; else `OK` |
| `live(main_sg_dir) -> list` | entries in state `OK`, plus locked ones in any state: what the guards check |

Concurrency: `worktree add` and `remove` read-modify-write the registry. Two concurrent `add` calls could lose an
entry. The registry write uses a lock file `worktrees.json.lock` (`os.open(O_CREAT|O_EXCL)`, removed in `finally`,
stale after 60 s). This is the only cross-process lock in the design.

### 5.6 `worktree add`, step by step

New class `Vault__Worktree` (`sgit_ai/core/actions/worktree/Vault__Worktree.py`, a `Vault__Sync__Base` subclass like
the other actions), method `add(main_directory, path, name=None, branch=None, new_branch=None, from_rev=None,
scope_paths=None, no_checkout=False, vault_key=None, on_progress=None) -> dict`. It runs
`Workflow__Worktree__Add` (`sgit_ai/workflow/worktree/Workflow__Worktree__Add.py`, registered with
`@register_workflow` as the clone workflows are):

| # | Step | New or reused | What it does |
|---|---|---|---|
| 1 | `Step__Worktree__Check_Main` | new | Resolve the main vault root from the current directory (`Vault__Storage.find_vault_root`). Refuse when: it is a worktree itself (has `alternates.json`; the remedy names the main folder; Git also creates worktrees of the main only); it is a read-only clone (`clone_mode.json`, decision D6); a merge is in progress (`Vault__Merge__State.check_not_in_progress`); a `vault move`/rekey is half done (`.sg_vault_new` or `.sg_vault_old_*` present). Read the vault key from `local/vault_key`, or from `--vault-key` when the main is bare (`Vault__Bare.is_bare`), validated as `Vault__Attach` does: the derived branch-index file must exist in `bare/indexes`, else write nothing. Derive the keys (`Vault__Crypto.derive_keys_from_vault_key`) |
| 2 | `Step__Worktree__Check_Target` | new | `<path>` must not exist, or be an empty directory. It must not be inside the main's `.sg_vault`. It may be inside the main working copy only when the main's ignore rules ignore it, or when it is a nested vault the scan skips (5.10): the step warns, and refuses with `--no-nested` (decision D4). The name must be unique in the registry; the default name is `basename(path)`, with `-2`, `-3` appended on a clash |
| 3 | `Step__Worktree__Resolve_Start` | new | The start commit: `--from <rev>` through `Vault__Revision.resolve` against the main clone, default the main clone's HEAD (its clone branch head, **including unpushed commits**, as Git's `worktree add` starts from HEAD). The named branch: `--branch` (must exist in the main's local branch index), `-b <new>` (must not exist), default the main's tracked named branch |
| 4 | `Step__Worktree__Copy_Structure` | new | `create_bare_structure(<path>)`. Copy from the main's `bare/`: the branch index file, **all** of `bare/refs/` (dozens of files of 69 bytes), **all** of `bare/keys/` (public keys, encrypted). Each copy is a regular-file read through `read_regular` and a write into the new store; refs and keys are not content-addressed, so they are copied byte for byte. **Not** copied: `bare/data/` (borrowed), `bare/packs/` (borrowed through the main store's `packs()`), `bare/cache/` (derived; rebuilt on the worktree's first push if declared), `bare/pending/` (change packs are drained by the main clone). Then write `local/alternates.json` (5.2) |
| 5 | `Step__Worktree__Copy_Local` | new | Copy the clone-independent local files: `remotes.json`, `base_url`, `token` (through `write_private`: the server pin, TM-F15/F22, must hold in the worktree too), `remote_heads.json` (the baselines of what the main accepted: correct, because every object they name is reachable through the alternate; without them, the first pull in the worktree could not detect a rewind), the format/policy pin if present, `flat-cache/<head tree>.json` (content-addressed by tree id, so always valid; saves the first flatten). **Not** copied: `scan-cache.json` (per working copy), `reflog.jsonl` (the worktree's history starts here; one entry `worktree add from <main> at <commit>`), `merge_state.json`, `checkout.json`, `last-pull.json`, `push_state.json`, `pending_registration.json`, `stash*`, `pack-store.sqlite`, `index/generations.json` (derived), `trace.jsonl`, `lazy-fetch.log`, `debug/`, `move-history.json`, `migrations.json`, the main's `.pem` (a worktree never signs as the main clone) |
| 6 | `Step__Clone__Create_Clone_Branch` | **reused** (`sgit_ai/workflow/clone/Step__Clone__Create_Clone_Branch.py`) | New clone branch, new key pair, `.pem` 0600 in the worktree's `local/`, `pending_registration.json`; its ref is set to the start commit (the step writes `named_commit_id`; the worktree state sets that field to the start commit) |
| 7 | `Step__Worktree__New_Named_Branch` | new, only with `-b` | `Vault__Branch_Switch.branch_new(<path>, name)` (`sgit_ai/core/actions/branch/Vault__Branch_Switch.py:167`) inside the new worktree, exactly as a user would run `sgit branch new` there |
| 8 | `Step__Clone__Verify_Signatures` | **reused** | Same rule as every clone (TM-R04/TM-F14): under `signatures-required`, every commit since the recorded policy start must verify. All objects are local through the alternate, so this costs no network. The main's unpushed commits are signed by the main's clone key, whose public key was copied in step 4, so they verify |
| 9 | `Step__Clone__Extract_Working_Copy` | **reused** | Full checkout, or the scoped tree for `--path`, or nothing beyond the record for `--no-checkout`. Blobs are read through `obj_store.load`, therefore borrowed and verified. The scan cache is seeded as every checkout seeds it (`_checkout_flat_map`, `Vault__Sync__Base.py:674`) |
| 10 | `Step__Clone__Setup_Local_Config` | **reused** | `config.json` (new `my_branch_id`; `scope_paths` from `--path`; `shallow_boundaries` **copied from the main**, because history the main never fetched is not borrowable either; `sparse` as the main's when the main is sparse, or `--no-checkout`; `pack_store=False`, since the worktree keeps no packs of its own and borrows the main's; `last_remote_head` from the main) and `vault_key` (0600) |
| 11 | `Step__Worktree__Register` | new | Add the `Schema__Worktree__Entry` to the main's `worktrees.json` (locked write) |

**Failure handling.** Any failure after step 4 removes `<path>/.sg_vault` and the files written (the step runner's
`keep_work=False` cleanup plus an explicit `rollback` in `Vault__Worktree.add`). Nothing in the main vault is written
before step 11.

**The vault key: copied, not referenced (decision D2).** The worktree is a full clone and must keep working if the
main folder moves or is removed. A reference would also make every worktree command open the main's key file. Git
shares config the same way, in effect. The copy is written through the single secret writer, as every clone's is.

### 5.7 `remove`, `prune`, `lock`, `unlock`, `dissociate`, `list`

| Method on `Vault__Worktree` | Rules |
|---|---|
| `remove(main_directory, name_or_path, force=False)` | Resolve the entry. Refuse when locked. Unless `force`: refuse when `Vault__Sync__Status.status(<path>)` is not clean (uncommitted, untracked, conflict files), when the clone branch head is not reachable from any named-branch head this clone knows (unpushed commits: the message names how many and says `sgit push` there first), or when a merge is in progress. Then `secure_rmtree(<path>/.sg_vault/local)` (key, `.pem`, token are secrets: zero-filled as `rekey_wipe` does), `shutil.rmtree(<path>)`, and remove the entry. The worktree's clone branch stays in the vault's branch index if it was ever pushed (sgit has no branch delete; it costs one index entry and one public key; decision D5) |
| `prune(main_directory, dry_run=False)` | Remove entries in state `MISSING` or `FOREIGN`, never locked ones. Prints each. No files are touched (the folder is already gone or belongs elsewhere) |
| `lock(…, reason)` / `unlock(…)` | Set or clear `locked` and `lock_reason` in the entry |
| `dissociate(main_directory, name_or_path)` | In the worktree: walk every ref the worktree holds (clone branch, named branches in its index, tags, stash), collect every reachable commit, tree and blob within its scope and shallow boundaries, and for each `is_borrowed` object `load` (verified) then `store` it into the own store. Then `Vault__Alternates.remove`, and remove the registry entry. Prints counts and bytes. After this, the main vault can be removed without affecting the former worktree |
| `list(main_directory)` | The main first, then each entry with `state_of`, head and named branch read from the worktree's own config and refs (read-only; a missing worktree shows `-`) |

### 5.8 Phase 2: `sgit branch merge --worktree <name|path>`

Goal: merge another worktree's work into this clone without a push. This is what makes the main folder
(or a coordinating agent) able to integrate agents' worktrees the way `git merge feature` does.

**Flow** (`Workflow__Merge_Local`, `sgit_ai/workflow/pull/Workflow__Merge_Local.py`; reuses the pull workspace):

| # | Step | New or reused | What it does |
|---|---|---|---|
| 1 | `Step__Pull__Derive_Keys` | reused | as pull |
| 2 | `Step__Merge_Local__Resolve_Source` | new | Resolve `<name|path>` through the registry (from the main or any worktree). The source must be a worktree of the **same vault**: its `alternates.json` validates against the same `branch_index_id`, or it is the main itself when run from a worktree. Read its clone branch head: its `local/config.json` `my_branch_id` → its branch index entry → `head_ref_id` → its `bare/refs/<ref>`, decrypted with the read key (`Vault__Ref_Manager.read_ref` on the source's `sg_dir`). Refuse when the source has a merge in progress |
| 3 | `Step__Merge_Local__Import` | new | Walk commits from the source head until reaching commits this clone has (`obj_store.exists`). For each missing commit, the trees and blobs it introduces: read from the source's object store (which itself borrows from the main), verify by content address, `store` into this clone's own store. Import the source's public key file `bare/keys/<author_key_id>` when this clone lacks it, accepted only if it decrypts to a public key, exactly as `Vault__Key_Fetch._is_public_key` (`sgit_ai/core/actions/verify/Vault__Key_Fetch.py`) does |
| 4 | `Step__Merge_Local__Check_Signatures` | new, thin | Under `signatures-required`: `Vault__Signatures.verify_chain(head=source_head, stop_at=<commits this clone already has>)`, the same check pull applies to incoming commits (`Vault__Incoming_Check`). A failure refuses before any write |
| 5 | `Step__Pull__Merge` | **reused** | With `named_commit_id` set to the source head. Fast-forward, three-way merge, `.conflict` files, merge state, the dirty-tree guard (`_guard_working_tree`): all unchanged. With design 01 landed, `--merge lines` applies here too |

**What it does not touch:** this clone's named-branch ref and baselines (`remote_heads.json`). A local merge is not a
fetch of the named branch: the rewind guard and the baselines only ever follow the server. The merge commit's
message is `Merge worktree <name> (<clone branch>) into <this clone branch>`.

**Where the switch goes:** `CLI__Branch` merge parser gains `--worktree NAME` (mutually exclusive with fetching from
the server). `Vault__Sync.merge_branch` gains `worktree: str = None` and calls `Vault__Sync__Pull.merge_local(…)`.
`Pull__Workspace.merge_from` stays for named branches.

### 5.9 Compatibility

| Who | Effect |
|---|---|
| Vaults and clones without worktrees | Nothing changes. `alternates_probed` finds no file and the object store behaves exactly as today. The scan change (5.10) affects only folders containing a nested `.sg_vault` |
| The server and the web UI | Nothing changes. A worktree is a clone: one more clone branch and public key in the index after its first push, as for any new clone |
| Older sgit opening a worktree | It does not know `alternates.json`, so it sees a clone with an almost empty `bare/data/`. Reads miss and fall back to the network (existing fail-soft paths), which is slow but correct. `check fsck` reports objects missing. The worktree `README` line printed by `add` says the worktree needs this sgit version or later. No gate is needed: nothing on the server changes and a worktree is a local arrangement |
| Older sgit opening the main vault | `worktrees.json` is ignored; the guards of 6.3 are absent in that build, which is the residual risk named in TM row W3 |

### 5.10 Nested vaults in the scan (fix included in phase 1)

`_scan_local_directory` (`Vault__Sync__Base.py:555-562`) and the other working-copy walks (`:659`, `:752`,
`Vault__Merge.remove_conflict_files` / `has_conflicts`, `Vault__Sync__Lifecycle.uninit`'s count) must not descend
into a sub-folder that holds its own `.sg_vault/`. The check costs nothing extra: `os.walk` already lists each
folder's sub-directories, so when `root != directory and '.sg_vault' in dirs`, clear `dirs` and skip `files`. Same
rule as Git for a nested repository. One shared helper, `Vault__Ignore.is_nested_vault_root(root_listing_dirs,
root, directory) -> bool`, so all walks use the same rule. `status` reports `Nested vault skipped: wt/` once, so the
user knows why those files are not tracked.

### 5.11 File-by-file changes

| File | Change |
|---|---|
| `sgit_ai/safe_types/Safe_Str__Worktree_Name.py` | new (5.2) |
| `sgit_ai/safe_types/Enum__Worktree_State.py` | new |
| `sgit_ai/schemas/worktree/Schema__Worktree__Alternates.py`, `Schema__Worktree__Entry.py`, `Schema__Worktree__Registry.py` (+ `__init__.py` in `sgit_ai/schemas/worktree/`) | new |
| `sgit_ai/schemas/workflow/worktree/Schema__Worktree__Add__State.py` | new (or a `Schema__Clone__State` subclass) |
| `sgit_ai/storage/Vault__Alternates.py` | new (5.3) |
| `sgit_ai/storage/Vault__Worktree_Registry.py` | new (5.5) |
| `sgit_ai/storage/Vault__Object_Store.py` | fields `alternate`, `alternates_probed`; `alternate_store`, `own_object_ids`, `is_borrowed`; `load`, `exists`, `size_of`, `all_object_ids` changed (5.3). Commit 0: atomic writes in `store`/`store_raw`/`store_at` (temp file in the same folder + `os.replace`) |
| `sgit_ai/storage/Vault__Verified_Write.py` | `save` `:72` writes atomically (temp + `os.replace`) |
| `sgit_ai/core/Vault__Ignore.py` | `is_nested_vault_root` (5.10) |
| `sgit_ai/core/Vault__Sync__Base.py` | scan walks skip nested vault roots (`:555`, `:659`, `:752`) |
| `sgit_ai/core/actions/merge/Vault__Merge.py` | `remove_conflict_files` / `has_conflicts` walks: same skip |
| `sgit_ai/core/actions/worktree/Vault__Worktree.py` (+ `__init__.py`) | new: `add`, `list`, `remove`, `prune`, `lock`, `unlock`, `dissociate`, `rollback` |
| `sgit_ai/workflow/worktree/Workflow__Worktree__Add.py`, `Step__Worktree__Check_Main.py`, `Step__Worktree__Check_Target.py`, `Step__Worktree__Resolve_Start.py`, `Step__Worktree__Copy_Structure.py`, `Step__Worktree__Copy_Local.py`, `Step__Worktree__New_Named_Branch.py`, `Step__Worktree__Register.py` (+ `__init__.py`) | new |
| `sgit_ai/core/Vault__Sync.py` | thin delegates `worktree_add`, `worktree_list`, …; `merge_branch(…, worktree=None)` (phase 2) |
| `sgit_ai/cli/CLI__Worktree.py` | new `CLI__Worktree` class: parsers and `cmd_*` methods, output and `--json` (3.3, 3.4) |
| `sgit_ai/cli/CLI__Main.py` | register the `worktree` parser (build_parser), add to `help all` |
| `sgit_ai/core/actions/lifecycle/Vault__Sync__Lifecycle.py` | `uninit` `:95`: in a worktree, refuse ("this is worktree N of /main: `sgit worktree remove N`"); in a main with live worktrees, refuse unless `force`. `rekey_wipe` `:52` / `rekey`: refuse with live worktrees |
| `sgit_ai/core/actions/move/Vault__Sync__Move.py` | `move` `:22`: refuse with live worktrees (a move rewrites every id: worktrees would borrow nothing and point at the old vault); in a worktree: refuse ("move the main vault, or dissociate first") |
| `sgit_ai/migrations/Migration__Runner.py` | `apply`: refuse with live worktrees (migrations rewrite trees) |
| `sgit_ai/core/actions/backup/Vault__Backup.py` | in a worktree, the zip's `bare/data/` includes every borrowed object reachable from the worktree's refs (read through `load`), so a backup restores without the main |
| `sgit_ai/core/actions/push/Vault__Sync__Push.py` | `_upload_bare_to_server` `:840`: when `alternates.json` is present, refuse ("this vault was never pushed; push it from the main folder /main first"). A worktree of a pushed vault never takes this path |
| `sgit_ai/core/actions/fsck/Vault__Sync__Fsck.py` | report `borrowed: N objects from /main` and, with `--verbose`, which; a borrowed object that fails verification is reported as corrupt in the main, with the main's path |
| `sgit_ai/workflow/pull/Workflow__Merge_Local.py`, `Step__Merge_Local__Resolve_Source.py`, `Step__Merge_Local__Import.py`, `Step__Merge_Local__Check_Signatures.py` | new (phase 2) |
| `sgit_ai/core/actions/pull/Vault__Sync__Pull.py` | `merge_local(directory, source, on_progress)` (phase 2) |
| `sgit_ai/cli/CLI__Branch.py` | `--worktree NAME` (phase 2) |
| `tests/unit/cli/test_CLI__B07__Namespace_Moves.py:104` | `'worktree'` added to `TOP_LEVEL_COMMANDS` (if D1 is top level) |

---

## 6. Security and threat model

### 6.1 What the worktree trusts

| Thing | Trust | Why it is safe |
|---|---|---|
| Borrowed objects | none | Verified by content address on every borrowed read (5.3). A changed or half-written file is a miss, never accepted |
| `alternates.json` | The worktree's own `.sg_vault/local/`, same trust as `vault_key` | It can only be written by a local process with the user's rights. Vault content cannot plant it: `Vault__Path_Guard.is_protected` (`:95`) refuses any `.sg_vault` segment from vault data, file or folder, on every write path (TM-F03) |
| The main store's identity | The `branch_index_id` check (5.3) | Only the same vault holds that file id. A pointer to another vault fails validation. Even if it passed, foreign objects would fail to decrypt or would not hash to the ids the trees name |
| Refs and keys copied at `add` | Same as the main clone's | They are the main clone's own verified state. Everything later is pulled and verified by the worktree itself |
| The registry | Main's `local/` | Only paths and names. An unreadable registry fails closed in every guard |

### 6.2 Cases

| Case | Behaviour |
|---|---|
| The main folder is deleted or moved | `validate` fails (no directory, or no index file). The worktree runs as a clone with a sparse store: reads fall back to the network (fail-soft paths). Objects that were **only** in the main (its unpushed commits that the worktree started from) are lost to the worktree. `status` and `fsck` say so. Remedy: `dissociate` before removing a main folder, and `vault uninit` in the main refuses while worktrees are live |
| The pointer is a symlink, or `main_sg_dir` is a link | Refused by `read_regular` / `is_link` |
| The pointer points to the worktree itself, or to another worktree | Refused (self-loop check; the target holds an `alternates.json`) |
| A second user on the machine edits the main store | The same exposure as editing a clone's own store; verification turns any change into a miss |
| Key material | The worktree gets its **own** clone key pair (a commit from a worktree is attributable to that worktree, `author_key_id`). The vault key and token are copied through `write_private` (0600). `remove` zero-fills them (`secure_rmtree` of `local/`) |
| Secrets in the working copy | Unchanged: the secret guard runs in the worktree as in any clone |
| A worktree inside the main working copy | The nested-vault rule (5.10) keeps the main from committing the worktree's files. Without it, the main's next `commit` would put the worktree's whole working copy into the vault a second time |
| Metadata seen by the host | One more clone branch and public key per worktree, after its first push (TM-R08 already lists "team size (clone branches, keys)"). Nothing else: the host never learns that two clones share a disk |

### 6.3 Threat-model rows to add

These use the next free TM numbers at implementation time (TM-R44 and TM-F38 at the time of writing; other designs
may take numbers first).

| Proposed row | Text | Test |
|---|---|---|
| W1 (accepted risk, TM-R) | Worktrees borrow objects from the main clone's store (`local/alternates.json`). Every borrowed object is verified by its content address on read, so a changed or half-written main store yields a miss (and a network fetch), never wrong content. A worktree whose main is removed loses the objects only the main held (its unpushed commits): `dissociate` first; main `uninit`/`rekey`/`move`/`migrate apply` refuse while worktrees are registered | `test_Security__Known_Gaps.py` (removing the main by hand loses unpushed borrowed objects; the worktree still reads everything pushed) |
| W2 (fixed, TM-F) | A folder inside the working copy that holds its own `.sg_vault/` (a worktree or a nested clone) was scanned and its files committed into the outer vault. The scan never descends into a nested vault root | `test_Security__Fixed__Hostile_Paths.py::test_nested_vault_is_never_committed` |
| W3 (accepted risk, TM-R) | Guards that protect worktrees (`uninit`, `rekey`, `move`, `migrate`) exist only in builds that know `worktrees.json`; an older sgit in the main folder can destroy the store worktrees borrow from. Mitigation: update the main folder's sgit with the worktrees | analysis |
| W4 (fixed, as part of commit 0, TM-F) | Object files were written in place, so a reader in another process could see a half-written object; the CAS guard could then report a false collision. Writes are now a temp file plus `os.replace` | `test_Vault__Object_Store` atomic-write case |

### 6.4 Path-guard test to add

`tests/security/test_Security__Fixed__Hostile_Paths.py`:

- `test_worktree_pointer_cannot_be_planted_by_vault_content`. A hostile commit carries `sub/.sg_vault/local/alternates.json`
  and a file `sub/.sg_vault`. Clone, pull, branch switch, checkout, `write`, stash pop and revert must write neither.
  `is_protected` already refuses both; the test pins it for the new file name.
- Extend the existing parametrised `test_spellings_of_structural_folders_are_protected` with
  `.sg_vault/local/alternates.json` and `.SG_VAULT/local/worktrees.json`.

---

## 7. Interactions

### 7.1 Commands run in a worktree

| Command | Behaviour |
|---|---|
| `status`, `commit`, `commit --amend`, `write`, `history *`, `diff`, `checkout`, `resolve`, `merge-abort`, `vault stash` | Unchanged. All object reads go through the object store, so borrowed objects are present |
| `push` | Normal push. Objects the worktree's commits reference are read through the alternate and uploaded when the server lacks them (the push path decides by its own rules, as now). Starting from the main's unpushed HEAD means the first worktree push also pushes the main's unpushed commits, exactly as pushing a Git branch pushes its base. The worktree's clone branch is registered on its first push (`pending_registration.json`) |
| `pull`, `fetch`, `fetch --unshallow`, `fetch <folder>` | Downloads only objects missing from both stores, into the worktree's own store. Baselines and the rewind guard work as in any clone (seeded from the main's at `add`) |
| `branch switch`, `branch new`, `branch merge` | Unchanged; a switch in the worktree does not affect the main |
| `check fsck` | Borrowed objects count as present and are verified; the report names how many were borrowed. `--repair` writes into the worktree's own store |
| `check verify` | Unchanged (keys copied at `add`, missing ones fetched as today) |
| `pack *` on a pack vault | `pack compact` from a worktree works as from any clone (it reads through `load`). The worktree keeps no packs of its own; `--pack-store` is not offered on `worktree add` |
| `vault backup` | Includes borrowed reachable objects (5.11) |
| `vault uninit` | Refused: use `sgit worktree remove` |
| `vault move`, `vault rekey`, `migrate apply` | Refused in a worktree: run them in the main folder after removing or dissociating worktrees |
| `serve`, `publish` | Work (they read through the object store); `publish`'s own walk of `bare/` is the main-vault command and is refused in a worktree, as for a partial clone |
| `dev dump` | Already refused on partial clones; also refused in a worktree with an alternate ("dissociate first") |

### 7.2 Commands run in the main folder while worktrees exist

| Command | Behaviour |
|---|---|
| Everything that only adds objects (commit, pull, fetch, push, clone steps) | Unaffected. Worktrees see new main objects immediately, because they read the store live |
| `pack compact` / `pack store` swap on a `--pack-store` main | Packs can be removed from the main's pack store while a worktree process reads through it. The read finds no pack, counts as a miss, and falls back to the network. A worktree started after the swap sees the new table |
| `pack store extract` | Moves objects from packs to loose files in the main: still borrowable |
| `vault uninit`, `vault rekey`, `vault move`, `migrate apply` | Refused while `live()` is non-empty, naming each worktree and the two remedies (`sgit worktree remove N`, `sgit worktree dissociate N`); `--force` exists only on `uninit`, where the backup is taken first |
| `vault clean` | Removes the main's working copy only; the store stays; unaffected |
| `worktree list` | Shows every worktree's state |

### 7.3 Clone shapes

| Main clone is | Worktree |
|---|---|
| Full | Any shape: full, `--path`, `--no-checkout` |
| Scoped (`--path` in the main) | Default scope = the main's scope; `--path` must be within it, otherwise the extra folders are fetched from the network on `add` (allowed, and said so) |
| Shallow | Inherits the boundaries; `fetch --unshallow` in the worktree fetches into its own store |
| Sparse / selective | Inherits; blobs the main never fetched are fetched on demand into the worktree's store |
| Bare (`clone --bare`, no key) | Supported with `--vault-key` (or stdin). This is the common agent layout in Git (`git clone --bare` plus one worktree per branch) |
| Read-only | Refused in v1 (D6) |
| Pack vault, loose store | Borrows loose objects |
| Pack vault, `--pack-store` | Borrows through the main's pack store (the alternate's own `packs()`) |

### 7.4 Other designs

| Design | Interaction |
|---|---|
| Design 01 (line-level merge) | Phase 2's merge goes through the same `Step__Pull__Merge`, so `--merge lines` and the per-clone `merge_style` apply. Each worktree has its own `local/config.json`, so each can choose |
| Design 05 (bisect) | Bisect state lives in `local/` and is per worktree, as Git's `refs/bisect` is per worktree. An agent can bisect in a worktree while the main keeps working: the main use case |
| Design 02 (signing with own keys) | A user signature comes from the user's key, which is shared across worktrees through Git's or sgit's config; the clone signature is per worktree |
| Hooks (2.9) | `local/hooks/` is per clone; `worktree add` copies the main's hooks (Git shares hooks across worktrees). Copy, so a hook edited in one place does not silently change another: decision D3 |

---

## 8. Performance

Reference numbers, 76,000 files in 58,553 folders, in-memory host, 4 cores
(`10/26/release-readiness__pack-indexes-branch.md` §3): full clone 61 s; `clone --no-checkout` 28 s, so the network
and store part is about 28 s and the checkout about 33 s; `clone --path raw/c09` (1,520 files) 2.8 s.

| `worktree add` variant | Work done | Expected time (to measure, acceptance item A9) |
|---|---|---|
| `--no-checkout` | Copy index, refs, keys (well under 1 MB), local files, flat cache file for the head; create clone branch; verify signatures from the policy start | under 2 s |
| `--path raw/c09` | as above plus 1,520 files written | about 1 s plus the write |
| full checkout | as above plus 76,000 files written, 76,000 borrowed reads with SHA-256 each (~1 KB files: tens of ms of hashing in total) | about the checkout share of a clone, ~30 s here, dominated by file creation; versus 61 s for a full clone, **with zero network**. On a real host the gain is larger (a clone's network share was 165 s before the bulk fetch on the DC vault, 80 s after) |

Disk:

| Part | Size |
|---|---|
| Working copy | the same as any checkout (unavoidable) |
| `.sg_vault/bare/` | the branch index, refs and keys: kilobytes (the DC vault: ~40 refs and ~40 keys) |
| `.sg_vault/local/` | config, keys, one flat-cache file (on the 76,000-file vault one flat cache is a few MB), scan cache (as any clone) |
| Objects | 0 at `add`; afterwards only the worktree's own commits and what it pulls before the main does |

A full clone of the 76,000-file vault holds about 174 MB in `.sg_vault`; a worktree holds a few MB.

Read-path cost for clones without worktrees: one `os.path.isfile` on `local/alternates.json` per object-store
instance (probed once), so nothing measurable.

---

## 9. Test plan

All tests are real: in-memory API (`Vault__API__In_Memory`) or `Vault__Test_Env` vaults, no mocks, no `__init__.py`
under `tests/`. File names follow `test_<Class>.py`.

### 9.1 Unit tests

| File | Class | Cases |
|---|---|---|
| `tests/unit/safe_types/test_Safe_Str__Worktree_Name.py` | `Test_Safe_Str__Worktree_Name` | sanitises `a/b` → `a_b`; max 64; empty refused; round trip |
| `tests/unit/schemas/worktree/test_Schema__Worktree__Alternates.py`, `…Entry.py`, `…Registry.py` | one class each | defaults; round-trip invariant; unknown-field tolerance |
| `tests/unit/storage/test_Vault__Alternates.py` | `Test_Vault__Alternates` | load absent → None; load broken JSON → None; link file refused; relative `main_sg_dir` refused; missing dir; self-loop; main that is itself a worktree (chain) refused; identity: an index id of another vault refused; valid → usable |
| `tests/unit/storage/test_Vault__Object_Store__Alternates.py` | `Test_Vault__Object_Store__Alternates` | own first: an object in both stores is read from own; borrowed read returns bytes; borrowed bytes changed on disk → `Vault__Object_Missing_Error`; half-written file (truncate) → miss; `exists`, `size_of`, `all_object_ids`, `own_object_ids`, `is_borrowed`; `resolve_id` resolves a borrowed short id; writes never touch the main (main's `bare/data` listing unchanged after `store`); alternate of the alternate not followed; main with `--pack-store`: a packed object is borrowed; no alternates file: behaviour identical to today (same calls, same results) |
| `tests/unit/storage/test_Vault__Object_Store.py` (extend) | | commit 0: `store`/`store_raw`/`store_at` leave no temp file, never a partial target (simulate by writing then reading from another handle) |
| `tests/unit/storage/test_Vault__Worktree_Registry.py` | `Test_Vault__Worktree_Registry` | add/find/remove; duplicate name/path refused; corrupt file raises; `state_of` OK/MISSING/FOREIGN; `live` includes locked missing; lock file stale after 60 s |
| `tests/unit/core/test_Vault__Ignore__Nested_Vault.py` | `Test_Vault__Ignore__Nested_Vault` | nested root detected; root itself never "nested" |
| `tests/unit/sync/test_Vault__Sync__Nested_Vault_Scan.py` | `Test_Vault__Sync__Nested_Vault_Scan` | a nested clone inside the working copy: `status` does not list its files and says it was skipped; `commit` does not commit them; conflict-file walks skip it |
| `tests/unit/worktree/test_Vault__Worktree__Add.py` | `Test_Vault__Worktree__Add` | add from a full clone: files equal the main's HEAD, own `bare/data` empty, `alternates.json` 0600, `vault_key` 0600, new clone branch id and `.pem` differ from the main's; `-b new` creates the named branch; `--branch existing`; `--from HEAD~1`; `--path` scope; `--no-checkout`; bare main with `--vault-key`, wrong key writes nothing; refusals: target non-empty, target inside `.sg_vault`, main is a worktree, read-only main, merge in progress, duplicate name; failure mid-way leaves no `.sg_vault` at the target and no registry entry; zero API calls during add (count `Vault__API__In_Memory` calls) |
| `tests/unit/worktree/test_Vault__Worktree__Lifecycle.py` | `Test_Vault__Worktree__Lifecycle` | `list` shapes (text, porcelain, json); `remove` refuses dirty, unpushed, locked, merge in progress; `--force`; removes files and entry; secrets zero-filled; `prune` drops missing and foreign, keeps locked; `lock`/`unlock`; `dissociate` copies exactly the reachable borrowed set, removes the pointer, and the worktree then works with the main deleted |
| `tests/unit/worktree/test_Worktree__Two_Way.py` | `Test_Worktree__Two_Way` | worktree commit + push, main `branch merge` sees it; main commit + push, worktree pull downloads 0 objects when the main already pulled; worktree push of a start commit that was unpushed in the main uploads those objects; first push of a never-pushed vault from a worktree refused; signatures-required vault: worktree add verifies, worktree push verifies on the main's pull |
| `tests/unit/worktree/test_Worktree__Guards.py` | `Test_Worktree__Guards` | main `uninit` refused with live worktree, allowed with `--force` (backup taken); `rekey` refused; `move` refused; `migrate apply` refused; in a worktree: `uninit`, `move`, `rekey`, `dev dump`, `publish` refused with the remedy; `vault backup` in a worktree restores into a fresh folder with no main present |
| `tests/unit/worktree/test_Worktree__Fsck.py` | `Test_Worktree__Fsck` | borrowed count reported; corrupt borrowed object reported as corrupt in the main; `--repair` writes to own store |
| `tests/unit/worktree/test_Worktree__Pack_Vault.py` | `Test_Worktree__Pack_Vault` | pack vault, loose main; pack vault, `--pack-store` main; main compaction swap while a worktree reads → miss then network |
| `tests/unit/worktree/test_Merge_Local.py` (phase 2) | `Test_Merge_Local` | fast-forward from a worktree; three-way with conflict files; source's public key imported only when it decrypts; under `signatures-required` a source commit with a bad signature refuses before any write; baselines and named ref untouched; a source of another vault refused; source with merge in progress refused; dirty-tree guard applies |
| `tests/unit/cli/test_CLI__Worktree.py` | `Test_CLI__Worktree` | parsing, exit codes 0/1/2, output lines, `--json` keys exactly as 3.4 |
| `tests/unit/cli/test_CLI__B07__Namespace_Moves.py` | existing | `TOP_LEVEL_COMMANDS` includes `worktree` (D1) |

### 9.2 Security tests

| File | Test |
|---|---|
| `tests/security/test_Security__Fixed__Hostile_Paths.py` | `test_worktree_pointer_cannot_be_planted_by_vault_content`; spellings extended (6.4); `test_nested_vault_is_never_committed` (W2) |
| `tests/security/test_Security__Known_Gaps.py` | W1: main removed by hand → worktree reads pushed objects from the network, unpushed borrowed ones are reported missing; W3 analysis row has no test |

### 9.3 Integration

`tests/integration/test_Worktree__Live.py` (Python 3.12 venv, the in-memory sgraph server): add, commit, push,
main merge, pull, remove: the full loop against the real server code. One run with a pack vault.

### 9.4 Acceptance checklist (implementation and deployment)

| # | Check | How |
|---|---|---|
| A1 | `sgit worktree add ../wt` on a pushed vault makes **zero** network requests | API call counter in the unit test; on the live dev server, run with the network blocked (`SGIT_DEFAULT_BASE_URL` to a closed port is not enough, since the server is pinned; run with no route) and the command still succeeds |
| A2 | The worktree's files are byte-identical to the main's HEAD | `diff -r` excluding `.sg_vault` |
| A3 | The worktree's `bare/data` holds no objects after `add`; the main's `bare/data` is unchanged after any worktree command | listing before/after |
| A4 | A commit in the worktree, pushed, then `sgit branch merge <named>` in the main, gives the main the change | scripted |
| A5 | Phase 2: `sgit branch merge --worktree wt` in the main gives the same tree as A4 with no push | scripted |
| A6 | Removing the main folder by hand: the worktree still `status`es, `pull`s and `push`es (network fallback); `fsck` names what was lost | scripted |
| A7 | `uninit`, `rekey`, `move`, `migrate apply` in the main refuse while a worktree exists, and name it | scripted |
| A8 | A nested worktree inside the main working copy is never committed by the main | scripted |
| A9 | Timings on the 76,000-file vault: `add --no-checkout` < 2 s; full `add` < 50 % of a full clone on the same machine | measured, recorded in the CHANGELOG |
| A10 | `pytest tests/unit -n auto` and `pytest tests/security` green; `tests/integration` worktree test green on 3.12 | CI |
| A11 | Older sgit (0.26.x) opening a worktree: commands work (slowly, by network), nothing is corrupted | manual, one run |
| A12 | `sgit help all` lists `worktree`; `TOP_LEVEL_COMMANDS` updated | test |
| A13 | Threat-model rows W1–W4 added with their tests; CHANGELOG entry; README section "Worktrees" | review |

---

## 10. Implementation steps (ordered commits)

| # | Commit | Contents | Estimate |
|---|---|---|---|
| 0 | `fix(storage): object files written atomically` | temp + `os.replace` in `Vault__Object_Store.store/store_raw/store_at` and `Vault__Verified_Write.save`; tests; TM row W4 | 0.25 day |
| 1 | `feat(storage): object store reads through a verified alternate` | `Vault__Alternates`, schemas, object store changes, `test_Vault__Alternates`, `test_Vault__Object_Store__Alternates` | 0.5 day |
| 2 | `fix(scan): never descend into a nested vault` | `is_nested_vault_root`, walks, status line, tests, TM row W2 | 0.25 day |
| 3 | `feat(worktree): sgit worktree add` | registry, workflow and steps, `Vault__Worktree.add`, `CLI__Worktree`, CLI registration, `TOP_LEVEL_COMMANDS`, `help all`, tests | 1 day |
| 4 | `feat(worktree): list, remove, prune, lock, unlock, dissociate` | methods, CLI, tests | 0.5 day |
| 5 | `feat(worktree): guards and interactions` | uninit/rekey/move/migrate guards, backup materialisation, first-push refusal, fsck reporting, dump/publish refusals, security tests, TM rows W1/W3 | 0.5 day |
| 6 | `docs: worktrees` | README section, CHANGELOG, threat model, response note with measured timings (A9) | 0.25 day |
| 7 | `feat(branch): merge from a local worktree` (phase 2) | `Workflow__Merge_Local` and steps, `merge_local`, `--worktree` flag, tests, integration test | 1–1.5 days |

Phase 1: about 3.25 days (commits 0–6). Phase 2: 1–1.5 days. Commits 0 and 2 are useful on their own and can land
first.

---

## 11. Open decisions for Dinis

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | Command placement (Rule 9) | top-level `sgit worktree` · `sgit vault worktree` | **Top level**, as Git; agents already type `worktree`. Edit `TOP_LEVEL_COMMANDS` in the same commit |
| D2 | The vault key in a worktree | copy (0600) · reference the main's file | **Copy**: a worktree must survive the main moving, and every clone already holds its key this way |
| D3 | Hooks (when 2.9 lands) | shared with the main · copied at `add` · none | **Copied at `add`**: predictable, no hidden coupling |
| D4 | A worktree inside the main working copy | allow with a warning · refuse | **Allow with a warning** (Git allows it); the nested-vault scan rule makes it safe |
| D5 | Clone branches left in the vault by removed worktrees | leave (as today for any deleted clone) · add `branch delete` for unused clone branches later | **Leave for now**; note it under roadmap item 2.10 (prune) |
| D6 | Worktrees of a read-only clone | refuse · support as read-only worktrees (copy `clone_mode.json`, no clone branch) | **Refuse in v1**; easy to add if asked |
| D7 | Start point | the main's HEAD including unpushed commits (Git) · the last known named-branch head | **The main's HEAD**, as Git; `--from` covers the other case |
| D8 | Phase 2 now or later | with phase 1 · after agents have used phase 1 | **With phase 1** if the integrating agent pattern (one coordinator merging many worktrees) is the main use; otherwise after. It is a self-contained commit either way |
