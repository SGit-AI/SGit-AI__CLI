# Design 03: partial commits (`commit <paths>`, `commit -p`) and hooks

> Read with [`design__00__index-and-reconciliation.md`](design__00__index-and-reconciliation.md): where the two disagree (shared foundations F1–F9, the in-progress rules), the index wins.

**Roadmap items:** 2.3 (commit some files, not all) and 2.9 (hooks), from `roadmap__git-parity.md` (same folder).
**Status:** design, not implemented. Written against `3a1d72a` on `claude/charming-babbage-5hzcxq` (code identical to `dev`).
**Git reference:** git 2.43.0. Every Git behaviour quoted below was run against that binary in a scratch repository
on 28 Oct, unless marked "(docs)".
**Extension rule:** nothing changes for a user who does not use these features. `sgit commit` with no paths still
commits the whole working copy. A clone with no hooks folder runs nothing. No vault format change; no `min_client` gate.

---

## 1. Summary and the exact Git behaviour matched

### 1.1 `sgit commit <pathspec>…` (whole-file partial commits)

Git's `git commit <pathspec>` is `git commit --only <pathspec>`. It takes HEAD's tree, replaces the matched
**tracked** paths with their working-tree content (or removes them if deleted), and commits only that. Everything
else stays uncommitted, untouched on disk. Measured on git 2.43:

| Case | Git 2.43 result | sgit (this design) |
|---|---|---|
| Modified tracked file named | committed; the other edits stay dirty | same |
| Tracked file deleted on disk, named | the deletion is committed | same |
| Folder named (`d`) | every changed tracked path under `d/` | same, **plus new files under `d/`** (1.4) |
| Glob (`'*.txt'`, quoted so the shell leaves it) | `*` also crosses `/` (fnmatch without `FNM_PATHNAME`) | same rule |
| Untracked file named | `error: pathspec 'new.txt' did not match any file(s) known to git`, exit 1 | **committed** (1.4) |
| Name that matches nothing | same error, exit 1 | `pathspec 'zzz' did not match any file known to sgit`, exit 1 |
| Named path unchanged | "nothing added to commit…", exit 1 | "Nothing to commit…", exit 0 (sgit's existing exit code, kept) |
| A merge is in progress | `fatal: cannot do a partial commit during a merge.`, exit 128 | refused with the same words, exit 1 |
| `--include` / `-i` | stages the paths, commits index + paths | not offered: no index (decision D1) |

### 1.2 `sgit commit -p` (hunk selection)

Git has no `commit -p` of its own name for this; `git commit -p` runs `git add -p` on a temporary index and commits
the result. The interactive keys of git 2.43 `add -p`:
`y n q a d j J g / e s p ?` (also `k K`): yes / no / quit / all remaining in file / none remaining in file /
leave undecided and go next / previous / go to / search / **edit hunk** / **split hunk** / print.
sgit matches `y n q a d s ?` plus `j k` navigation. `e` (edit the hunk in an editor) is a non-goal for the first
cut (decision D4). The working-tree file is never modified; only the committed blob is the partial content.

### 1.3 Hooks

Git runs executables named after the event from `$GIT_DIR/hooks/` (or `core.hooksPath`). Measured and from
`githooks(5)`:

| Hook | When | Arguments | stdin | Exit status | `--no-verify` skips it |
|---|---|---|---|---|---|
| `pre-commit` | before the commit message is prepared | none | none | non-zero aborts the commit | yes |
| `prepare-commit-msg` | after the default message is written to the message file, before the editor | `$1` message file, `$2` source (`message` with `-m`, `merge`, `squash`, `commit` with `-c/-C/--amend` without `-m`, `template`, or absent), `$3` commit id (only for source `commit`) | none | non-zero aborts | **no** (measured: it ran with `--no-verify`) |
| `commit-msg` | after the message is final | `$1` message file (hook may rewrite it) | none | non-zero aborts | yes |
| `post-commit` | after the commit is made | none | none | ignored | no |
| `pre-push` | after the remote refs are known, before anything is sent | `$1` remote name, `$2` URL | one line per ref: `<local ref> SP <local id> SP <remote ref> SP <remote id> LF`, a missing remote ref is forty `0` (measured: `refs/heads/master 41b8… refs/heads/master 0000…`) | non-zero aborts the push, nothing sent | yes |
| `post-merge` | after a successful merge (also a fast-forward pull); not after a merge that stopped on conflicts | `$1` `1` if squash else `0` | none | ignored | no |
| `post-checkout` | after a checkout / switch (and clone, worktree add) | `$1` previous HEAD, `$2` new HEAD, `$3` `1` branch checkout or `0` file checkout | none | **becomes the command's exit status** (measured: a hook exiting 3 made `git checkout` exit 1) but cannot undo it | no |

Further Git facts the design copies:

- The hook runs with its cwd at the **root of the working tree**, even when the command ran in a sub-folder
  (measured: cwd was the repo root for a commit made from `d/`).
- Git exports what child Git commands need (`GIT_INDEX_FILE` for `pre-commit`: measured; `GIT_DIR` is only set when it
  had to be found by other means; measured empty in a plain repo).
- A hook file that exists but is not executable is ignored with a hint (`advice.ignoredHook`) (docs).
- `core.hooksPath` replaces the hooks folder; it may be relative to the working-tree root (docs). Git never takes
  hooks from the repository content; a team that wants shared hooks points `core.hooksPath` at a tracked folder by
  hand (Husky and similar do this).
- `git commit -n` is `--no-verify`.

---

## 2. Scope and non-goals

**In scope**

1. `sgit commit [-m MSG] [--] <pathspec>…`, with folders, globs, deletions, new files, `--amend`, `--json`.
2. `sgit commit -p [<pathspec>…]` interactive, and a non-interactive hunk selection for agents
   (`--list-hunks`, `--hunk ID`).
3. Hooks: `pre-commit`, `prepare-commit-msg`, `commit-msg`, `post-commit`, `pre-push`, `post-merge`,
   `post-checkout`; `--no-verify` / `-n`; a per-clone hooks path (`core.hooksPath` equivalent).
4. **Prerequisite:** `sgit push` stops refusing a dirty working copy (5.4). Without it, a partial commit cannot be
   pushed, which defeats the feature.
5. `sgit vault hooks` to show the hooks path and what is installed (decision D6 on the name).

**Non-goals (first cut)**

- A persistent staging area (`sgit add`, `restore --staged`). Analysed in 5.6; decision D1.
- `e` (edit hunk) in `-p`; `git add -p`'s regex search `/` and `g` goto.
- Pathspec magic (`:(exclude)`, `:!`, `:(icase)`, `:(top)`, `:(literal)`, `:(glob)`). Only literal paths, folders and
  the three wildcards `* ? [...]`. `:!pattern` is a cheap follow-up (decision D3).
- Hooks Git has beyond the seven above (`pre-merge-commit`, `pre-rebase`, `post-rewrite`, `reference-transaction`,
  `pre-auto-gc`, `push-to-checkout`, server hooks). `post-rewrite` (for `--amend`) is a one-line follow-up.
- Hooks for `sgit write` (plumbing; Git's plumbing runs no hooks either), except `pre-push` when `write --push`
  pushes (5.8).
- Hooks taken from vault content, synced, or set by the vault. Never.
- Template hooks copied into a fresh clone (Git's `init.templateDir`). A fresh sgit clone has no hooks.

---

## 3. CLI surface

### 3.1 `sgit commit`

```
sgit commit [MESSAGE] [-m MSG] [-d DIR] [--allow-deletions] [--allow-secret-file PATH]…
            [--amend] [-p | --patch] [--hunk ID]… [--list-hunks] [-n | --no-verify] [--json]
            [-- PATHSPEC…]
```

**Disambiguating the positional message.** Today `sgit commit "msg"` takes the first positional as the message
(`sgit_ai/cli/CLI__Main.py:375`). Git takes positionals as pathspecs. The rule, chosen so that every existing
invocation keeps its meaning:

| Invocation | Meaning |
|---|---|
| `sgit commit` | whole working copy (today) |
| `sgit commit "fix typo"` | whole working copy, message "fix typo" (today) |
| `sgit commit -m "fix" a.txt b/` | **paths** `a.txt`, `b/` (Git's form: with `-m`, every positional is a pathspec) |
| `sgit commit "fix" -- a.txt` | message "fix", path `a.txt` |
| `sgit commit -- a.txt` | path `a.txt`, auto message |
| `sgit commit -m "x" "y"` | **changes meaning**: today `-m` silently overrides the positional `y`; in this design `y` is a pathspec. Searched our docs, skills and tests: no use of both. The parser prints `note: with -m, "y" is a path` when that path matches nothing, so the old habit fails loudly, never silently (decision D2). |

argparse implementation: `commit_parser.add_argument('args', nargs='*')` replaces the `message` positional;
`CLI__Vault.cmd_commit` splits it: with `-m`, all of `args` are pathspecs; without `-m`, the part before a literal
`--` must be at most one item (the message) and everything after `--` is a pathspec. argparse drops a bare `--`
from the list, so the split point comes from the raw argv (implementation note at the end of section 10).

**Flags added**

| Flag | Meaning |
|---|---|
| `-- PATHSPEC…` / positionals with `-m` | commit only the matched paths (5.1) |
| `-p`, `--patch` | interactive hunk selection over the matched paths (all changed text files when none given); needs a TTY on stdin and stdout, else exit 2 with "use --list-hunks / --hunk for non-interactive selection" |
| `--list-hunks` | print the hunks of the matched paths and exit 0; nothing committed. With `--json`, a machine list (3.3) |
| `--hunk ID` (repeatable) | non-interactive selection: commit exactly these hunks (ids from `--list-hunks`); implies `-p` semantics, no TTY needed |
| `-n`, `--no-verify` | skip `pre-commit` and `commit-msg` (Git's scope; `prepare-commit-msg` and `post-commit` still run) |
| `--json` | one JSON object on stdout (3.3) |

**Output (text)**, unchanged for the whole-copy commit. For a path commit:

```
Committed 2 file(s) to clone-abc… (2 of 7 changed; 5 left uncommitted).
  Commit: obj-cas-imm-…
  Left uncommitted: notes.md, src/x.py, … (sgit status)
```

**Exit codes**

| Code | When |
|---|---|
| 0 | committed; or "Nothing to commit" (existing behaviour, kept) |
| 1 | refused: a pathspec matched nothing, partial commit during a merge, a path outside a scoped clone, secret guard, a hook rejected (`pre-commit hook failed (exit 3): nothing was committed`), `commit-msg` emptied the message |
| 2 | usage: `-p` without a TTY and without `--hunk`; `--hunk` and `--list-hunks` together; an unknown hunk id |

### 3.2 `sgit push`, `pull`, `branch switch`, `branch checkout`, `checkout`, `branch merge`

One flag is added where Git has one: `sgit push -n / --no-verify` (skips `pre-push`). Pull, switch, checkout and
merge only gain the post-hooks, which `--no-verify` does not affect in Git either. `sgit write --push` gains
`--no-verify` for its push.

### 3.3 JSON shapes

`sgit commit --json` (success):

```json
{"status": "committed", "commit_id": "obj-cas-imm-…", "branch_id": "clone-…", "message": "…",
 "files_changed": 2, "paths": ["a.txt", "b/c.md"], "left_uncommitted": ["notes.md"],
 "hunks": {"src/app.py": ["h-3f9a2c41d07b", "h-91aa…"]},
 "hooks": {"pre-commit": 0, "prepare-commit-msg": null, "commit-msg": 0, "post-commit": 0}}
```

`hooks` values: exit code, or `null` when not installed / not run. `status` is `nothing_to_commit` with no
`commit_id` when that applies. Refusals print `{"status": "refused", "reason": "…", "paths": […]}` and exit 1.

`sgit commit --list-hunks --json`:

```json
{"base_commit": "obj-cas-imm-…",
 "files": [
   {"path": "src/app.py", "binary": false, "status": "modified",
    "base_hash": "…", "work_hash": "…",
    "hunks": [
      {"id": "h-3f9a2c41d07b", "index": 1, "header": "@@ -10,6 +10,8 @@ def main():",
       "old_start": 10, "old_lines": 6, "new_start": 10, "new_lines": 8,
       "added": 2, "removed": 0, "text": " ctx\n+new line\n…",
       "splittable": true}
    ]},
   {"path": "logo.png", "binary": true, "status": "modified", "hunks": [{"id": "h-whole-…", "index": 1, "whole_file": true}]}
 ]}
```

**Hunk ids** are content-derived, never positional, so an agent's selection cannot land on the wrong hunk if the file
changed between listing and committing: `id = "h-" + sha256(path NUL base_hash NUL old_start NUL old_lines NUL
removed lines NUL added lines)[:12]`. Split sub-hunks get their own ids, listed with `--list-hunks --split`
(each `splittable` hunk is replaced by its parts). `--hunk` refuses (exit 2) any id that is not in the freshly
computed list, naming it, so a stale id fails loudly. New files list as one whole-file hunk; deletions as one
whole-file "delete" hunk.

### 3.4 `sgit vault hooks`

```
sgit vault hooks                 # where hooks are read from, and each known hook: installed / executable / missing
sgit vault hooks --path DIR      # set the hooks path for this clone (core.hooksPath); relative = to the vault root
sgit vault hooks --unset         # back to .sg_vault/local/hooks
sgit vault hooks --json
```

Rule 9: hooks are per-clone configuration, not a daily verb, so they live under `vault`, not at the top level;
`TOP_LEVEL_COMMANDS` does not change. (Git: `git config core.hooksPath`. sgit has no `config` command; decision D6.)

---

## 4. How the code works today

### 4.1 Commit

| What | Where |
|---|---|
| CLI parser: positional `message`, `-m`, `-d`, `--allow-deletions`, `--allow-secret-file`, `--amend` | `sgit_ai/cli/CLI__Main.py:374-389` |
| CLI handler; "Nothing to commit" exits 0 | `sgit_ai/cli/CLI__Vault.py:794-822` |
| Facade | `sgit_ai/core/Vault__Sync.py:148-154` |
| Commit flow | `sgit_ai/core/actions/commit/Vault__Sync__Commit.py:32-203` |
| Load HEAD's flat map (scoped: `Vault__Scoped_Tree.flatten` → `(flat, opaque)`; full: `flatten` + `flatten_dirs`) | `Vault__Sync__Commit.py:69-78` |
| Full working-copy scan (with scan cache), collecting `.conflict` files on the way | `Vault__Sync__Commit.py:80-81` |
| Secret guard on the changed paths only | `Vault__Sync__Commit.py:82-86` |
| Scoped clone: any working-copy path outside the scope refuses by name | `Vault__Sync__Commit.py:88-95` |
| Sparse / selective branch: overlay on-disk files on HEAD's flat map; a checked-out path missing on disk is a deletion; then `build_from_flat` | `Vault__Sync__Commit.py:97-135` |
| Full branch: `Vault__Sub_Tree.build` with `old_flat_entries` + `old_tree_ids` (the "one-file fast path") | `Vault__Sync__Commit.py:136-145` |
| Merge state read; `has_conflicts` uses the scan's list | `Vault__Sync__Commit.py:147-151` |
| `--amend` plan; "nothing to commit" when the root tree equals HEAD's | `Vault__Sync__Commit.py:154-160`, `_amend_plan` `:205-229` |
| Create the signed commit, write the clone ref | `Vault__Sync__Commit.py:180-188` |
| `write_file` (`sgit write`): HEAD's flat map + named files → `build_from_flat` → commit; writes the files, then the ref | `Vault__Sync__Commit.py:231-350` (build `:325`, files then ref `:339-344`) |
| `write`'s path guard | `Vault__Sync__Commit.py:352-372` |

### 4.2 Trees

| What | Where |
|---|---|
| `build(directory, file_map, …, old_flat_entries, opaque, old_tree_ids)`: an entry whose scanned size and hash equal HEAD's is reused without reading the file (`unchanged`, `:58-63`); reading is `O_NOFOLLOW` and never through a link (`:65-81`) | `sgit_ai/storage/Vault__Sub_Tree.py:32-92` |
| `build_from_flat(flat_map, read_key, opaque)`: **no folder reuse**, every folder is rebuilt and re-encrypted (deterministic, so the ids are right, but the cost is the whole vault) | `Vault__Sub_Tree.py:105-131` |
| Folder reuse: a folder whose file names, sub-folders and files are all unchanged keeps its old tree id | `Vault__Sub_Tree.py:556-642`, reuse test `:593-604` |
| Blob reuse by content hash; otherwise encrypt (deflated on `blob-deflate` vaults) and store | `Vault__Sub_Tree.py:517-529` |

### 4.3 Scan and scan cache (sgit's half of Git's index)

| What | Where |
|---|---|
| `scan-cache.json` under `.sg_vault/local/`: `{path: [mtime_ns, ctime_ns, size, ino, dev, hash]}`, version 2 | `sgit_ai/core/Vault__Sync__Base.py:32-35`, load `:487-504`, save `:506-517` |
| Git's racy rule (2 s) | `Vault__Sync__Base.py:35`, `:541-545`, `:592-599` |
| The scan: ignores, links never followed, unreadable never "deleted", FIFOs kept | `Vault__Sync__Base.py:519-636` |
| Every sgit write seeds the cache with the real hash | `_checkout_flat_map` `:674-714`, `_scan_cache_seed` `:716-736` |
| Checkout writes a file **in place** (`open(path, 'wb')`), so an existing file keeps its mode bits | `Vault__Sync__Base.py:701-703` |

### 4.4 Push, pull, switch, checkout (where hooks would fire)

| What | Where |
|---|---|
| Push refuses a dirty working copy: `status()` then "Working directory has uncommitted changes. Commit your changes before pushing." | `sgit_ai/core/actions/push/Vault__Sync__Push.py:92-96` |
| Push's implicit pull, then the final heads | `Vault__Sync__Push.py:177-186` |
| Pull refuses during a merge; runs `Workflow__Pull` | `sgit_ai/core/actions/pull/Vault__Sync__Pull.py:80-121` |
| Merge outcome (`up_to_date`, `fast_forward`, `merge`, `conflict`, `rewound`) | `sgit_ai/workflow/pull/Step__Pull__Merge.py:54-156` |
| Pull's dirty-tree guard (carries dirty files the merge does not touch, refuses the ones it would) | `sgit_ai/core/actions/pull/Vault__Pull__Guard.py:28-127` |
| Branch switch (refuses dirty unless `--force`) | `sgit_ai/core/actions/branch/Vault__Branch_Switch.py:30`, `_assert_clean` `:339` |
| Selective checkout of files | `sgit_ai/core/actions/checkout/Vault__Sync__Checkout.py:34` |
| `branch merge` is a pull with `merge_from` | `sgit_ai/core/Vault__Sync.py:230-234` |

### 4.5 Paths, the CLI root, secrets in the environment

| What | Where |
|---|---|
| The CLI walks `directory` up to the vault root | `sgit_ai/cli/CLI__Main.py:1170-1183`, `Vault__Storage.find_vault_root` `sgit_ai/storage/Vault__Storage.py:87-96` |
| Vault content can never name `.sg_vault*` or `.git` (any spelling) | `sgit_ai/storage/Vault__Path_Guard.py:27-28`, `safe_join` `:134-148` |
| Environment variables sgit reads: `SGIT_DEFAULT_BASE_URL`, `SGIT_HTTP_NO_KEEPALIVE`, `SGIT_TRACE`, `SGIT_PACK_INDEXES(_READ)` and **`SG_SEND_PASSPHRASE`** (the credential store passphrase: a secret) | grep of `sgit_ai/` |
| TM-F06: `sgit update` ran `python -m pip` with the cwd on `sys.path`; fixed with `python -I` | threat model row TM-F06 |
| Local config schema (per clone, never synced; unknown keys are accepted by `from_json`) | `sgit_ai/schemas/Schema__Local_Config.py:9-22` |
| Rule 9 list | `tests/unit/cli/test_CLI__B07__Namespace_Moves.py:104-109` |

---

## 5. Design

### 5.1 Pathspec semantics

New class `Vault__Pathspec` in `sgit_ai/core/actions/commit/Vault__Pathspec.py`:

```python
class Vault__Pathspec(Type_Safe):
    patterns : list[Safe_Str__Pathspec]        # as typed, normalised to '/' separators
    prefix   : Safe_Str__Pathspec = None        # cwd relative to the vault root ('' at the root)

    def from_args(self, args: list, cwd: str, root: str) -> 'Vault__Pathspec'
    def is_glob(self, pattern: str) -> bool             # contains * ? or [
    def matches(self, path: str) -> bool                # any pattern
    def match(self, head_paths, disk_paths) -> tuple    # (matched: set, unmatched_patterns: list)
```

New safe type `Safe_Str__Pathspec` (`sgit_ai/safe_types/Safe_Str__Pathspec.py`): `max_length 4096`, regex rejects only
control characters `[\x00-\x1f\x7f]` (paths may be any Unicode; `Safe_Str__File_Path` would rewrite `* ? [` to `_`,
see `sgit_ai/safe_types/Safe_Str__File_Path.py:4`). `trim_whitespace = False` (a file name may end in a space).

Rules (each one a test):

| Input | Rule |
|---|---|
| Relative path | relative to the **cwd**, as in Git (`cd src && sgit commit -m x app.py` means `src/app.py`). `prefix` = `relpath(cwd, root)` when the cwd is inside the vault, else `''` (then relative to the root, which is how `-d DIR` users think). |
| `..` | allowed while it stays inside the vault (`cd src && sgit commit -m x ../README.md`); a pattern that resolves outside the root is refused: `pathspec '../../x' is outside the vault` (exit 1). |
| Absolute path | accepted if under the root; converted; else refused as above. |
| Literal file path | matches that path (tracked in HEAD, or a new file on disk). |
| Literal folder (`docs`, `docs/`, `.`) | matches every path under it, in HEAD or on disk. `.` is everything under the cwd. |
| Glob (`* ? [abc] [!abc]`) | `fnmatch.fnmatchcase(path, prefix + pattern)` over full vault paths; `*` crosses `/` (Git's default, measured). Case-sensitive on every OS (Git's default; decision D3 keeps it). |
| A path matched only on disk and ignored by `.gitignore` | not matched (Git: an ignored untracked file is not "known"); if a **literal** pattern names it, refuse with `pathspec 'x' is ignored by .gitignore` (exit 1). A tracked ignored file matches (sgit's "tracked wins", `tests/unit/sync/test_Vault__Ignore__Tracked_Wins.py`). |
| `.conflict` files, `.sg_vault*`, `.git` | never matched (the scan never lists them; the guard refuses them). |
| A pattern that matches nothing in HEAD ∪ disk | error naming every such pattern, exit 1, nothing written (Git). |
| A matched path that is unchanged | simply not in the commit; if nothing matched changed: "Nothing to commit" (exit 0, existing). |
| Renames | there is no rename in sgit's tree model: a moved file is a delete plus an add. `sgit commit -m mv old.txt new.txt` names both; naming only `new.txt` commits the add and leaves `old.txt` in HEAD (Git does the same: it commits what you name). |

`match(head_paths, disk_paths)` takes the **union** of HEAD's flat paths and the scan's paths, so a deleted tracked
file (in HEAD, not on disk) matches and becomes a deletion.

### 5.2 Building the commit tree from HEAD plus the selected paths

New method `Vault__Sync__Commit._commit_selected(directory, c, old_flat, old_tree_ids, opaque, selected: dict)`,
where `selected` is `{path: bytes | None}` (`None` = delete). It is the same shape as `write_file`'s core, so the
two share it:

1. `flat = dict(old_flat)`. For each `path, data` in `selected`: `None` → `flat.pop(path)`; bytes →
   `encrypt_or_reuse_blob(data, old_flat.get(path), read_key)` (`Vault__Sub_Tree.py:517`), entry
   `{blob_id, size, content_hash, content_type, large}` as `write_file` does (`Vault__Sync__Commit.py:310-314`).
2. Root tree: `sub_tree.build_from_flat(flat, read_key, opaque=opaque, old_tree_ids=old_tree_ids,
   file_unchanged=lambda p: p not in selected)`.
3. **Change to `Vault__Sub_Tree.build_from_flat`** (`Vault__Sub_Tree.py:105`): add the parameters `old_tree_ids: dict
   = None` and `file_unchanged: callable = None` and pass them, with `old_flat_entries=flat`, to
   `_build_tree_from_dir_contents` (`:556`), which already implements the reuse. Today `build_from_flat` rebuilds every
   folder; with the reuse a pathspec commit (and `sgit write`, and every merge) builds only the folders on the
   selected paths' spines. Callers that pass nothing behave exactly as today (both default to `None`).
   Correctness: a folder is reused only if its names and every file in it are unchanged and its old tree is in the
   store (`:593-604`), and tree ids are content addresses, so a reused id is byte-identical to a rebuilt one. The test
   `test_build_from_flat__reuse_gives_the_full_build_ids` builds both ways and compares every id.
4. Same signing, same `create_commit` call, same ref write as `commit()` (`Vault__Sync__Commit.py:162-188`).

`commit()` gains the parameters `paths: list = None`, `hunks: list = None`, `patch: bool = False`,
`no_verify: bool = False`, `hooks: Vault__Hooks = None` (5.5). When `paths` and `hunks` are both empty and `patch`
is false, the existing code path runs unchanged (the only edit to it is the hook calls).

**Selected-path flow** (new private method `_commit_paths`):

1. Refusals first, before any read: merge in progress → `Vault__Partial_Commit_Error('cannot do a partial commit
   during a merge')` (new error class in `sgit_ai/core/Vault__Errors.py`).
2. HEAD's flat map as today (`:69-78`).
3. Scan **only what the pathspec can reach**:
   - literal file paths: one `lstat` + the scan-cache rule per path (new `Vault__Sync__Base._scan_paths(directory,
     rel_paths)`, extracted from the per-file body of `_scan_local_directory` `:569-609` so both share one
     implementation: links skipped and kept, unreadable refused, FIFOs kept);
   - literal folders: `_scan_local_directory` restricted to that sub-tree (new parameter `under: list = None`, which
     starts `os.walk` at each folder instead of the root; the ignore rules still load from the root);
   - any glob: the full scan (it is what `commit` does today; the scan cache makes it cheap).
4. `Vault__Pathspec.match(head_paths, disk_paths)` → matched paths; unmatched patterns → refuse.
5. Changed = matched paths whose disk hash differs from HEAD's, plus matched HEAD paths missing on disk (deletions).
   Sparse / selective clones: a HEAD path not on disk is a deletion only if it is in the checkout set
   (`Vault__Checkout_Set`, as `Vault__Sync__Commit.py:102-111`), unless `--allow-deletions`.
6. Scoped clone: any changed path outside the scope → the existing refusal (`:88-95`), naming only the matched ones.
7. Secret guard on the changed paths (`Vault__Secret_Guard.refuse_files`, as `:85-86`).
8. Read the content of each changed path with `Vault__Path_Guard.read_regular` (O_NOFOLLOW).
9. `_commit_selected(...)`, then the commit as above. Nothing on disk is written; the scan cache needs no update
   (it describes the working copy, which did not change).
10. Result dict adds `paths` (sorted committed paths) and `left_uncommitted` (changed paths not selected, from the
    scan when one was done, else omitted).

`--amend` with paths: base flat map = HEAD's tree (the commit being replaced), parents = HEAD's parents, exactly
`_amend_plan` (`:205-229`), with the selected paths overlaid. Git does the same (`git commit --amend <paths>`).

### 5.3 Hunk selection (`-p`, `--hunk`, `--list-hunks`)

New class `Vault__Hunks` in `sgit_ai/core/actions/commit/Vault__Hunks.py` (pure: bytes in, bytes and schemas out):

```python
class Vault__Hunks(Type_Safe):
    context : Safe_UInt__Hunk_Context = 3      # lines of context, Git's default (-U3)
    max_bytes : Safe_UInt__File_Size = 10 * 1024 * 1024   # above this a file is whole-file only

    def hunks_of(self, path: str, base: bytes, work: bytes) -> Schema__File_Hunks
    def split(self, hunk: Schema__Hunk) -> list           # [Schema__Hunk], 1 element when not splittable
    def apply(self, base: bytes, work: bytes, chosen: list) -> bytes   # chosen: [Schema__Hunk]
    def hunk_id(self, path: str, base_hash: str, hunk) -> str
```

New schemas (`sgit_ai/schemas/commit/`):

| Schema | Fields |
|---|---|
| `Schema__Hunk` | `hunk_id : Safe_Str__Hunk_Id`, `index : Safe_UInt`, `old_start / old_lines / new_start / new_lines : Safe_UInt`, `removed : list[Safe_Str__Diff_Line]`, `added : list[Safe_Str__Diff_Line]`, `context_before / context_after : list[Safe_Str__Diff_Line]`, `header : Safe_Str__Diff_Header`, `splittable : bool`, `whole_file : bool`, and internal opcode bounds `a_lo / a_hi / b_lo / b_hi : Safe_UInt` (line indexes into base and work) |
| `Schema__File_Hunks` | `path : Safe_Str__Pathspec`, `status : Enum__Hunk_File_Status` (`modified`, `added`, `deleted`), `binary : bool`, `base_hash / work_hash : Safe_Str__Content_Hash`, `hunks : list[Schema__Hunk]` |
| `Schema__Hunk_List` | `base_commit : Safe_Str__Commit_Id`, `files : list[Schema__File_Hunks]` |

New safe types: `Safe_Str__Hunk_Id` (`^h-[0-9a-f]{12}$`), `Safe_Str__Diff_Line` (any text, no length cap below
the file cap; `\r` kept), `Safe_Str__Diff_Header`, `Safe_UInt__Hunk_Context`, `Enum__Hunk_File_Status`.
Every schema passes the round-trip invariant.

**Algorithm**

1. Lines: `base.splitlines(keepends=True)` and `work.splitlines(keepends=True)` on **bytes**, so CRLF and a missing
   final newline survive exactly. Text decoding only for display (`errors='replace'`).
2. Binary (a NUL in the first 8 KB, the rule of `Vault__Diff._is_binary`, `sgit_ai/core/actions/diff/Vault__Diff.py:534`)
   or larger than `max_bytes`: one `whole_file` hunk.
3. `difflib.SequenceMatcher(None, a, b, autojunk=False).get_grouped_opcodes(context)` gives Git-shaped hunks
   (`autojunk=False`, else long files with repeated lines get worse diffs than Git's). Each group is one hunk;
   `old_start` / `new_start` are 1-based as in a unified header. Header text: `@@ -s,l +s,l @@` plus, for text files,
   the nearest preceding line matching `^[A-Za-z_$]` (a cheap stand-in for Git's funcname; display only).
4. **Split** (Git's `s`): a hunk whose group has more than one non-`equal` opcode separated by `equal` runs splits at
   each such run; each part keeps up to `context` lines on each side. A hunk with a single change block is not
   splittable (`splittable = false`), as in Git.
5. **Apply:** walk base lines; for each opcode of the full diff, emit the work side if its hunk (or sub-hunk) was
   chosen, else the base side. Unchosen `insert` emits nothing, unchosen `delete` keeps the base lines. Since every
   chosen block is an opcode of the same `SequenceMatcher` run, blocks never overlap and the result is well defined.
   Property tests: choose all → `work`; choose none → `base`; any subset → `git apply --cached` of the same hunks
   gives the same bytes (Git as oracle, 9.2).
6. New file: one hunk (all added). Choosing it adds the file; not choosing leaves it out. Deleted file: one hunk;
   choosing it deletes. Git's `add -p` behaves the same for intent-to-add / deleted files.
7. The partial content becomes a blob through `_commit_selected` (5.2) as `{path: bytes}`. **The working copy is
   never written.** The scan cache is not touched. After the commit `sgit status` shows the file as modified (the
   rest of the hunks), which is exactly Git's state after `add -p` + `commit`.

**Base content.** HEAD's blob for the path: `obj_store.load(blob_id)` + `crypto.decrypt`. On a sparse, scoped or
pack-store clone the blob of a file that is on disk is local (it was written from it); if not, fetch it with the
existing blob fetcher (`Vault__Sync__Base._make_blob_fetcher`, `Vault__Sync__Base.py:81`) and verify by content
address as every fetch does. Read-only clones refuse commit already.

**Interactive prompt** — new class `CLI__Hunk_Prompt` (`sgit_ai/cli/CLI__Hunk_Prompt.py`), using `input()`:

```
diff --sgit a/src/app.py b/src/app.py
@@ -10,6 +10,8 @@ def main():
 …
(1/3) Commit this hunk [y,n,q,a,d,s,j,k,?]?
```

| Key | Action |
|---|---|
| `y` / `n` | take / skip this hunk |
| `a` / `d` | take / skip this and every later hunk in the file |
| `s` | split (only offered when `splittable`) |
| `j` / `k` | leave undecided, next / previous |
| `q` | stop; hunks decided so far count, the rest are skipped |
| `?` | help |

Colour only when stdout is a TTY and `NO_COLOR` is unset. Ctrl-C aborts with nothing committed (exit 130, as
`CLI__Main.py:1062` does today).

**Non-interactive:** `--list-hunks [--split] [--json]` prints; `--hunk ID…` selects. Both compute the hunks the same
way from the same inputs, so the ids agree as long as the file and HEAD did not change; if either changed the id is
gone and `--hunk` exits 2 naming it.

### 5.4 Prerequisite: push with a dirty working copy

`Vault__Sync__Push.push` refuses any uncommitted change (`Vault__Sync__Push.py:92-96`). After a partial commit
there are uncommitted changes by definition, so push would always refuse. Git pushes with a dirty tree.

Change: drop the `clean` refusal. Keep:

- the conflict-file refusal (`_check_no_conflict_files`, `:48`, `:1059`) and the merge-in-progress refusal (`:49`);
- push's implicit pull (`:177-183`), which already runs the dirty-tree guard (`Vault__Pull__Guard`): a dirty file
  the incoming merge does not touch is carried over, one it would touch refuses the pull **and therefore the push**
  before anything is written, naming the file ("commit them or sgit vault stash, then pull again").

The status call (`:93`) stays only to print a one-line note: `note: 5 uncommitted change(s) stay local (not pushed)`.
`push --force` skips the pull (`:178`) and so never touches the working copy: unchanged.

Test: `test_push__dirty_tree_not_touched_by_incoming_is_pushed` and `test_push__dirty_file_the_pull_would_change_refuses`
(two clones on the in-memory API).

### 5.5 Hooks runner

New package `sgit_ai/core/hooks/` with:

```python
class Enum__Hook_Name(Enum):                     # sgit_ai/safe_types/Enum__Hook_Name.py
    PRE_COMMIT = 'pre-commit'; PREPARE_COMMIT_MSG = 'prepare-commit-msg'; COMMIT_MSG = 'commit-msg'
    POST_COMMIT = 'post-commit'; PRE_PUSH = 'pre-push'; POST_MERGE = 'post-merge'; POST_CHECKOUT = 'post-checkout'

class Schema__Hook_Result(Type_Safe):            # sgit_ai/schemas/hooks/Schema__Hook_Result.py
    hook        : Enum__Hook_Name = None
    ran         : bool            = False
    exit_code   : Safe_Int        = 0
    duration_ms : Safe_UInt
    path        : Safe_Str__File_Path = None     # the file run (display only)

class Vault__Hooks(Type_Safe):                   # sgit_ai/core/hooks/Vault__Hooks.py
    disabled : bool = False                      # --no-verify sets the verify hooks off (see VERIFY_HOOKS)
    timeout  : Safe_UInt__Hook_Timeout = 0        # seconds; 0 = none (Git has none)

    def hooks_dir(self, directory: str) -> str
    def find(self, directory: str, hook: Enum__Hook_Name) -> str            # path or ''
    def run(self, directory: str, hook: Enum__Hook_Name, args: list = None,
            stdin: bytes = b'', no_verify: bool = False) -> Schema__Hook_Result
    def environment(self, directory: str, hook: Enum__Hook_Name) -> dict
    def message_file(self, directory: str) -> str                           # .sg_vault/local/COMMIT_EDITMSG

class Vault__Hook_Error(Exception)                # sgit_ai/core/Vault__Errors.py: "<hook> hook failed (exit N): <what was not done>"
```

`VERIFY_HOOKS = {PRE_COMMIT, COMMIT_MSG, PRE_PUSH}`: the ones `--no-verify` skips (Git's scope, measured for
`prepare-commit-msg`).

**Discovery** (`hooks_dir`, `find`):

1. `hooks_path` from the local config (new field, below); else `<root>/.sg_vault/local/hooks/`.
   A relative `hooks_path` is relative to the vault root (Git's rule for `core.hooksPath`).
2. **Refused hooks paths** (5.6, decision D5): a `hooks_path` that resolves inside the working tree is refused at
   run time unless `hooks_path_tracked` is also set (`sgit vault hooks --path DIR --allow-tracked`), because then
   the hooks are vault content that any teammate's push rewrites.
3. The hook file is `<dir>/<name>` exactly (POSIX). It must be a regular file (`lstat`; a symlink inside the hooks
   folder is allowed and resolved, since the folder is the user's own, not vault content) and executable
   (`os.access(path, os.X_OK)`). Present but not executable: skipped, with one stderr line per command:
   `hint: the pre-commit hook was ignored because it is not executable (chmod +x .sg_vault/local/hooks/pre-commit)`.
4. **Windows** (no exec bit, no shebang exec): look for `<name>.exe`, `<name>.cmd`, `<name>.bat`, `<name>.ps1`, then
   `<name>` with a `#!` line. `.ps1` runs as `powershell -NoProfile -ExecutionPolicy Bypass -File <hook> args…`;
   a `#!` script runs through `sh` if `sh.exe` is on `PATH` (Git for Windows puts it there), else it is skipped with
   a hint. Decision D7.

**Execution** (`run`):

- `subprocess.run([hook_path, *args], cwd=<vault root>, env=self.environment(...), input=stdin, timeout=timeout
  or None, check=False)`. **No shell.** argv is a list; nothing is interpolated.
- stdout and stderr are inherited (the user sees the hook's output, as in Git), except under `--json`, where the
  hook's stdout is redirected to sgit's stderr so stdout stays one JSON object.
- cwd is the vault root even when sgit was run from a sub-folder (measured Git behaviour).
- `ENOEXEC` (no `#!` line) → exit code 126 recorded and reported as a failure with
  `hook <name> could not be executed (no #! line?)`; `FileNotFoundError` on the interpreter → 127. Same codes as a
  shell.
- Timeout (only if configured): kill, exit code 124, reported as failure.
- Time is recorded in `duration_ms` (`--json` shows it).

**Environment** (`environment`): start from `os.environ`, then:

| Variable | Value / action |
|---|---|
| `SGIT_DIR` | absolute path of `<root>/.sg_vault` |
| `SGIT_WORK_TREE` | absolute vault root |
| `SGIT_HOOK` | the hook name |
| `SGIT_BRANCH` | the named branch this clone tracks (plaintext name; it is already plaintext locally) |
| `SGIT_CLONE_BRANCH` | the clone branch id |
| `SGIT_VERSION` | `sgit_ai.__version__` |
| `SGIT_VAULT_ID` | the vault id (not a secret; it is in every URL) |
| `SG_SEND_PASSPHRASE` | **removed** (the credential-store passphrase) |
| any variable whose name matches `(?i)(^SGIT_.*(TOKEN|KEY|SECRET|PASS))|(^SG_SEND_.*)` | **removed** (future-proof rule, tested with a planted variable) |
| `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE` | **removed** if inherited, so a hook that runs `git` is not pointed at some outer repository by sgit's caller |

Never added: the vault key, read key, write key, access token, the server URL with a token. The hook runs as the
same user and can read `.sg_vault/local/vault_key` itself; stripping is about not **leaking** secrets into
processes and logs that did not ask for them (CI logs printing `env`, child tools that upload their environment),
not a security boundary. The design says so in the threat-model row (6).

**Messages:** `message_file` is `.sg_vault/local/COMMIT_EDITMSG`, written with `Vault__Storage.write_private` (0600)
before `prepare-commit-msg`, read back after `commit-msg`, left in place afterwards (Git leaves `COMMIT_EDITMSG`).
It holds a plaintext commit message on local disk, the same class of data as the flat and scan caches (TM-R41).

**Configuration** (local only, never synced): two new fields in `Schema__Local_Config`
(`sgit_ai/schemas/Schema__Local_Config.py:22`):

```python
    hooks_path         : Safe_Str__File_Path       = None          # core.hooksPath: '' or None = .sg_vault/local/hooks
    hooks_path_tracked : bool                      = False         # the user accepted a hooks path inside the working tree
```

Older clients read a config with these keys fine (unknown keys are accepted by `from_json`, verified for
`Schema__Object_Commit`; the same test is added for `Schema__Local_Config`); an older client that rewrites the config
drops them, which only means hooks fall back to the default folder: fail-safe.

`hooks_timeout` is not a config field in the first cut; `SGIT_HOOK_TIMEOUT` (seconds) is read by `Vault__Hooks` for
agents that need a bound (decision D8).

### 5.6 Where each hook fires

| Hook | Call site (new code) | Arguments / stdin | On failure |
|---|---|---|---|
| `pre-commit` | `Vault__Sync__Commit.commit` and `_commit_paths`, **before the scan** (`Vault__Sync__Commit.py:80`), after the merge/read-only refusals | none | `Vault__Hook_Error`, nothing written |
| `prepare-commit-msg` | after the tree is built and "nothing to commit" is ruled out (`:158-160`), before signing | `$1` message file; `$2` `message` when `-m`/positional given, `merge` when concluding a merge (`merge_state` present), `commit` + `$3` HEAD id for `--amend` without a message, else absent (sgit writes its auto message into the file) | abort, nothing written |
| `commit-msg` | right after | `$1` message file | abort; an empty file after the hooks aborts with `Aborting commit due to empty commit message.` (Git's words) |
| `post-commit` | after `write_ref` (`:188`) and the merge-state cleanup (`:194-197`) | none | ignored (printed as a warning) |
| `pre-push` | `Vault__Sync__Push.push`, after the final heads are read (`Vault__Sync__Push.py:185-186`) and only when something will be sent (clone head ≠ named head, or first push), before any upload | `$1` remote name (`origin` or the `--remote` name), `$2` the server base URL (no token, no key); stdin: `refs/heads/<named> <clone head> refs/heads/<named> <named head or 40×0>`; with `--branch-only`, `refs/clones/<clone id>` on both sides | abort, nothing sent |
| `post-merge` | `Vault__Sync__Pull.pull` after the workflow returns with status `merge` or `fast_forward` (not `conflict`, `up_to_date`, `rewound` without changes); covers `branch merge` and push's implicit pull | `0` | ignored |
| `post-checkout` | `Vault__Branch_Switch.switch` (`1`), `sgit branch checkout <commit>` (`1`), `Vault__Sync__Checkout.checkout` (`0`), after the files are written | `$1` previous head id, `$2` new head id, `$3` flag | the command's exit status becomes non-zero (exit 1) with `post-checkout hook exited N`; the checkout stays done (Git) |

**Why `pre-commit` runs before the scan.** In Git the index is the commit; a formatter run by `pre-commit` changes
the working tree, not the index, and a common complaint is that the fix is not in the commit. In sgit the working
copy *is* the commit (no index), so running `pre-commit` first means a formatter's edits are committed, and a check
sees exactly what will be committed. For `commit <paths>` and `-p`, the hunks are computed after `pre-commit` too.

`sgit write` runs no commit hooks (plumbing). `sgit write --push` runs `pre-push` (it is a push), skippable with
`write --no-verify`. History edits (`history undo`, `reset`, `revert --as-commit`): in the first cut only `commit`
(including `--amend`) runs the commit hooks. Git's `git revert` does run `prepare-commit-msg` and `commit-msg`;
adding them to `revert --as-commit` is decision D9.

### 5.7 Staging area: analysis for decision D1

Git's index (`.git/index`) does three jobs:

| Job | Git | sgit today |
|---|---|---|
| Change detection cache (stat data → blob id) | the index's stat fields | **`scan-cache.json`**: `[mtime_ns, ctime_ns, size, ino, dev, hash]` per path, Git's racy rule (`Vault__Sync__Base.py:32-35`). Same role, same key. |
| The content of the next commit | `git add` writes blobs and index entries | **the working copy itself**; `sgit write` for agents |
| Merge stages 1/2/3 | index stages | `merge_state.json` + `<path>.conflict` files |

So the only missing job is the second. Options:

| Option | What | Cost | Risk |
|---|---|---|---|
| **A (recommended)** | No staging area. `commit <paths>`, `commit -p`, `write` cover selection. | in this design | none: no new state |
| B | Opt-in stage: `sgit add <paths>` / `add -p` encrypt the content into the object store and record `{path: entry or delete}` in `.sg_vault/local/stage.json`; when the stage is non-empty, `sgit commit` commits HEAD + stage only; `sgit commit -a` (or an empty stage) keeps today's whole-copy commit; `sgit restore --staged`; `status` gets a "staged" section | +4–5 days | `sgit commit` changes meaning the moment anything is staged, which breaks agents that call `add` by Git habit and then expect `commit` to take everything; three-way status; `add` becomes a top-level verb (Rule 9 edit) |
| C | Git-exact: always staged, `commit` commits only the stage | weeks | breaks every existing script and skill |

Recommendation A now; B later as an extension if users ask, built on `_commit_selected` (5.2) so it adds no new tree
code.

---

## 6. Security and threat model

| Risk | Analysis | Design answer | New TM row (number assigned at merge) |
|---|---|---|---|
| Hooks from vault content | A teammate (A4/A5) or a host serving content (A1, cannot: content is authenticated by id) puts a `hooks/pre-commit` in the vault. | Hooks are read only from `.sg_vault/local/hooks/` or a user-set path. Vault content can never write under `.sg_vault*` (`Vault__Path_Guard.py:27-28`, `safe_join` `:134-148`), so the default folder is out of its reach. Nothing in the vault can set `hooks_path` (local config only). | TM-Rxx-hooks-1: "hooks run as the user from a local folder; vault content cannot install or select one" — accepted, with a `Known_Gaps`-style test that a vault containing `.sg_vault/local/hooks/pre-commit` at any depth is refused on pull and never run |
| User points `hooks_path` at a tracked folder (the Husky pattern) | Every teammate with write access then runs code on this user's machine at the next commit. sgit writes checked-out files **in place** (`Vault__Sync__Base.py:701-703`), so a file the user made executable stays executable when a pull rewrites its content. | Refused unless `--allow-tracked` was given when setting the path; then `sgit vault hooks` and the first run after a pull that changed a hook print `hook pre-commit changed in the last pull (by <author key id>)` with its content hash. | TM-Rxx-hooks-2: accepted only with explicit opt-in; names the writer |
| Secrets in the hook's environment | A hook (or a tool it calls) logs or uploads its environment. | Strip `SG_SEND_PASSPHRASE`, any `SGIT_*TOKEN/KEY/SECRET/PASS`, any `SG_SEND_*`; never add a key or token; base URL passed to `pre-push` without credentials. Not a boundary (same user), stated as such. | TM-Rxx-hooks-3: hooks run as the user and can read `.sg_vault/local` like any process of that user; sgit adds nothing secret to their environment |
| Shell injection through file names or messages | Messages and paths are attacker-influenced (vault content). | No shell: argv list; the message is passed through a file, never argv; paths are not passed at all. | covered by test only |
| `cwd`-relative executable lookup (TM-F06 class) | Running `python` or `sh` by name with the vault root as cwd could pick a planted binary on Windows (the cwd is searched first there). | The hook is run by absolute path. On Windows `sh`/`powershell` are resolved with `shutil.which` over `PATH` **with the vault root removed from the search**, and a vault-root hit is refused. | TM-Fxx (preventive, with test) |
| Partial commit commits something unexpected | `-p` apply bug would commit content the user did not see. | `apply` property tests + Git oracle; `--list-hunks` shows exactly the text that a `--hunk` commits; the commit result lists the committed paths. | none |
| Secret guard bypass via paths | `commit <paths>` must not skip the guard. | Guard runs on the changed selected paths, as today on all changed paths. | none (test) |
| Hunk content that is a secret | A partial blob is never on disk, so the secret guard (which reads files) must also run on bytes: `Vault__Secret_Guard.refuse_bytes` (already used by `write`, `Vault__Sync__Commit.py:297-298`). | `refuse_bytes(path, partial_content)` for each partial blob. | none (test) |

`--no-verify` is a convenience, not a control: anyone who can run `sgit commit` can delete the hook. The design
says so in the docs; teams that need enforcement need it server-side (SGitHub, roadmap section 4).

---

## 7. Interactions

| With | Behaviour |
|---|---|
| Scoped clone (`clone --path`) | Pathspec outside the held folders → the existing scoped refusal naming the matched paths; patterns matching only outside → "did not match any file known to sgit" plus `(this clone holds only <folders>)`. Opaque entries are carried by `build_from_flat(…, opaque=)` exactly as `write_file` does. |
| Shallow clone | No effect (HEAD's tree is always present). |
| Sparse / selective working copy | A HEAD path never checked out is not "deleted" (checkout-set rule, 5.2 step 5); naming it in a pathspec gives `'x' is not checked out (sgit checkout x first)` for `-p`; for a whole-file pathspec it is unchanged, so not committed. After the commit the committed paths are added to the checkout set (as `Vault__Sync__Commit.py:189-192`). |
| Pack vault / `--pack-store` | No difference: blobs are stored loose locally and pushed in the commit pack as today. |
| Read-only clone | Refused before anything (existing `_check_read_only`, `CLI__Vault.py:795`). |
| Merge in progress | `commit <paths>` and `-p` refused (Git's message). Plain `sgit commit` concludes the merge as today. Hooks: `prepare-commit-msg` gets source `merge`. |
| `.conflict` files present, no merge state | Plain commit: today's behaviour. Path commit: allowed if no selected path has a `.conflict` sibling; otherwise refused naming it. |
| `--amend` | 5.2. Works with paths and `-p`. Refusals of `_amend_plan` apply (pushed head, merge commit). Hooks run (Git runs them on amend). |
| Secret guard | Runs on the selected changed paths (files) and on every partial blob (bytes). `--allow-secret-file` works as today. |
| `sgit write` | Shares `_commit_selected`; gains the folder reuse through `build_from_flat`. Behaviour unchanged otherwise. |
| `vault stash` | Stashes the whole working copy as today. A partial commit followed by stash is the Git workflow too. |
| Push | 5.4: dirty copies push; the implicit pull's guard protects uncommitted edits. |
| Status | Unchanged. After `-p` the file shows modified (remaining hunks). |
| Web UI and older clients | A partial commit is an ordinary commit; nothing new is stored. No gate. |

---

## 8. Performance

Measured costs of today's commit on the 76,000-file synthetic vault (release-readiness note, 26 Oct): a 5-file commit
plus push 4.5–5.2 s, of which the scan with a warm cache is most of the commit.

| Operation | Expected cost | Why |
|---|---|---|
| `commit -m x a/b/c.txt` (one literal path) | flat map from the flat cache (~0.6 s cold on 76k, ms warm) + 1 `lstat` + 1 read + ~depth trees encrypted | no working-copy scan; folder reuse in `build_from_flat` |
| `commit -m x docs/` | walk of `docs/` only | scoped scan (`under=`) |
| `commit -m x '*.md'` | full scan (as today) | a glob can match anywhere |
| `sgit write` (any vault) | **faster than today**: was a rebuild of every folder via `build_from_flat` | reuse added (5.2 step 3) |
| `-p` on a 10 MB text file | `SequenceMatcher` with `autojunk=False` is roughly O(n·m) worst case on pathological input; typical edits are fast | files over `max_bytes` (10 MB) are whole-file only; a benchmark test on a 5 MB / 100k-line file with 50 scattered edits must stay under 2 s |
| Hooks | one `fork/exec` per hook present, ~2–5 ms + the hook's own time; zero when the folder is empty | `find` is an `lstat` per hook name |

Perf tests (in `tests/unit/perf/` if the folder exists, else alongside, marked slow-safe): a 20,000-file vault, one
literal path commit must not call `_scan_local_directory` (asserted by a counter attribute on a subclass of
`Vault__Sync__Commit` used only in the test, no mocks) and must build at most `depth + 1` new trees (count objects
in the store before/after).

---

## 9. Test plan

All real objects, no mocks; vaults from `Vault__Test_Env` (`tests/_helpers/vault_test_env.py`) or two clones on
`Vault__API__In_Memory`; no `__init__.py` in test folders. Git is available in CI (`/usr/bin/git`); oracle tests skip
with a reason if `git` is missing.

### 9.1 Pathspec and partial commits — `tests/unit/core/actions/commit/test_Vault__Pathspec.py`, `test_Commit__Paths.py`

| Class | Cases |
|---|---|
| `Test_Vault__Pathspec` | literal file; literal folder with and without `/`; `.` at root and in a sub-folder; `*` crossing `/`; `?`; `[ab]`; `[!ab]`; cwd prefix; `..` inside; `..` escaping refused; absolute inside / outside; Unicode names; trailing-space names; control character refused by `Safe_Str__Pathspec`; round trip of the class's json |
| `Test_Commit__Paths__Basics` | two of five modified files committed, three still dirty (status lists them); deletion by name; folder pathspec commits new files under it; new file by name; unmatched pattern → exit 1, store and ref unchanged (object count equal); unchanged named path → "Nothing to commit"; `-m` + positionals = paths; `"msg" -- a` = message + path; legacy `sgit commit "msg"` unchanged; `-m x y` with `y` matching nothing prints the note |
| `Test_Commit__Paths__Tree` | resulting tree id equals the tree a whole-copy commit would give when the selection is all changed files (both orders); untouched folders keep their ids (compare `flatten_dirs` before/after); `build_from_flat` with reuse gives the same ids as without (random 500-file maps, 50 seeds) |
| `Test_Commit__Paths__Refusals` | merge in progress; scoped clone outside scope; ignored file by literal name; `.conflict` sibling; secret zip by path (guard); read-only clone |
| `Test_Commit__Paths__Amend` | `--amend a.txt` keeps parents, overlays `a.txt`, leaves `b.txt` dirty; refused on a pushed head |
| `Test_Commit__Paths__Sparse` | never-checked-out path not deleted; checked-out path removed → deleted only when named; checkout set updated |
| `Test_Commit__Paths__Git_Oracle` | same scripted edits in a Git repo and an sgit vault, `commit <paths>` in both, the set of committed paths and resulting file contents per path are equal (except the documented deviations: new untracked files) |

### 9.2 Hunks — `tests/unit/core/actions/commit/test_Vault__Hunks.py`, `test_Commit__Patch.py`, `tests/unit/cli/test_CLI__Hunk_Prompt.py`

| Class | Cases |
|---|---|
| `Test_Vault__Hunks__Shape` | single edit → 1 hunk; two edits far apart → 2 hunks; two edits 4 lines apart → 1 splittable hunk; split gives 2; headers 1-based; CRLF preserved; no final newline preserved on both sides; binary → whole-file; file > `max_bytes` → whole-file; empty base (new file); empty work (deleted) |
| `Test_Vault__Hunks__Apply` | all → work; none → base; every subset of a 6-hunk file (64 cases) equals Git: `git apply --cached` of the same hunks (generated as a patch per subset) on a repo with `base` committed, then `git show :path` |
| `Test_Vault__Hunks__Ids` | id stable across runs; id changes when base or hunk text changes; split ids distinct from the parent's |
| `Test_Commit__Patch` | `--hunk` commits exactly those hunks; the working file is byte-identical before/after; status shows the file modified; stale id → exit 2 naming it; `--hunk` + `--list-hunks` → exit 2; `-p` with no TTY → exit 2 with the hint; partial blob containing a vault key is refused by `refuse_bytes` |
| `Test_CLI__Hunk_Prompt` | scripted stdin (`y`, `n`, `s` then `y n`, `a`, `d`, `q`, `j k`, `?`) through a pipe with a pseudo-TTY from `pty.openpty()` on POSIX (skipped on Windows); Ctrl-C (SIGINT to the child) → exit 130, nothing committed |

### 9.3 Push with a dirty tree — `tests/unit/workflow/push/test_Push__Dirty_Tree.py`

`test_push__dirty_tree_not_touched_by_incoming_is_pushed`, `test_push__dirty_file_the_pull_would_change_refuses`
(store, refs and working copy unchanged), `test_push__force_never_touches_working_copy`,
`test_push__conflict_files_still_refuse`, `test_push__prints_uncommitted_note`.

### 9.4 Hooks — `tests/unit/core/hooks/test_Vault__Hooks.py`, `test_Hooks__Commit.py`, `test_Hooks__Push_Pull_Checkout.py`

Hooks are real executable files (`#!/bin/sh` on POSIX; `.cmd` on Windows) written by the test into the hooks folder;
each writes its argv, cwd, selected env vars and stdin to a file the test reads.

| Class | Cases |
|---|---|
| `Test_Vault__Hooks__Discovery` | default folder; `hooks_path` relative / absolute; non-executable ignored with hint; missing folder = nothing run; tracked `hooks_path` refused without `hooks_path_tracked`, allowed with it; Windows extension order (skipped on POSIX) |
| `Test_Vault__Hooks__Environment` | `SGIT_DIR`, `SGIT_WORK_TREE`, `SGIT_HOOK`, `SGIT_BRANCH`, `SGIT_VAULT_ID` set; `SG_SEND_PASSPHRASE`, a planted `SGIT_FOO_TOKEN`, `GIT_DIR` removed; no environment value contains the vault key, read key hex or write key (scan every value) |
| `Test_Vault__Hooks__Execution` | cwd is the vault root when run from a sub-folder; no shell (a file name `$(touch pwned)` is harmless); `ENOEXEC` → 126; timeout via `SGIT_HOOK_TIMEOUT=1` → 124; stdout redirected to stderr under `--json` |
| `Test_Hooks__Commit` | order pre-commit → prepare-commit-msg → commit-msg → post-commit (each appends to a log); pre-commit exit 1 → nothing committed (object count unchanged, ref unchanged); pre-commit edits a file → the edit is in the commit; prepare-commit-msg sources: `message`, `merge`, `commit` + HEAD id on `--amend` without `-m`, absent otherwise; commit-msg rewrites the message → commit has the new one; commit-msg empties it → aborted with Git's words; `--no-verify` skips pre-commit and commit-msg only; post-commit failure → commit stands, warning; `sgit write` runs none |
| `Test_Hooks__Push_Pull_Checkout` | pre-push argv (`origin`, URL with no token) and stdin line (named ref, clone head, remote head / 40 zeros on first push); pre-push exit 1 → nothing uploaded (server object count unchanged); `push --no-verify` skips; `write --push` runs pre-push; post-merge after fast-forward and after merge, not after conflict or up-to-date; post-checkout on branch switch (`1`), on `sgit checkout <path>` (`0`), its failure makes the command exit 1 with the checkout done |
| `Test_Hooks__Security` (in `tests/security/test_Security__Fixed__Hooks.py`) | a vault whose content contains `.sg_vault/local/hooks/pre-commit` (crafted tree) is refused by the path guard on pull and nothing runs; a tracked hooks path changed by a teammate's pull prints the "changed in the last pull" notice naming the author key; Windows `sh` lookup ignores a `sh.exe` in the vault root (skipped on POSIX) |

### 9.5 Schemas and CLI — existing patterns

Round-trip tests for `Schema__Hunk`, `Schema__File_Hunks`, `Schema__Hunk_List`, `Schema__Hook_Result`, the extended
`Schema__Local_Config` (including reading a config with the new keys through an instance of the old schema: unknown
keys accepted). `TOP_LEVEL_COMMANDS` unchanged (the test stays green without an edit). `sgit help all` lists nothing
new at the top level.

### 9.6 Acceptance checklist (implementation and deployment)

- [ ] `pytest tests/unit -n auto` and `pytest tests/security` green; no `__init__.py` added under `tests/`.
- [ ] `sgit commit`, `sgit commit "msg"`, `sgit commit -m msg` behave exactly as before (existing tests unchanged).
- [ ] `sgit commit -m x a b/` commits only `a` and changes under `b/`; `sgit status` lists the rest.
- [ ] Unmatched pathspec exits 1 and writes nothing (object count and ref unchanged).
- [ ] Partial commit during a merge is refused with Git's message.
- [ ] `sgit push` succeeds with uncommitted edits the incoming merge does not touch, and refuses (nothing written) when it would.
- [ ] `sgit commit --list-hunks --json` then `--hunk <id>` commits exactly the listed text; the working file is unchanged.
- [ ] 64-subset Git oracle for hunk apply passes.
- [ ] `sgit write` produces the same tree ids as before, faster on a 20k-file vault (timing printed by the perf test).
- [ ] Each of the seven hooks fires at its call site with Git's arguments and stdin; `--no-verify` scope matches Git.
- [ ] No hook environment contains a key, token or `SG_SEND_PASSPHRASE`.
- [ ] A hooks path inside the working tree is refused without explicit opt-in.
- [ ] Threat-model rows added (6), `Fixed__Hooks` security test present.
- [ ] CHANGELOG `[Unreleased]` entries for both features, with the push behaviour change called out.
- [ ] README / `sgit help commit` show the new forms; `sgit vault hooks` documented.
- [ ] Dev pre-release published; on it, the newsroom-style flow (agent edits 5 files, commits 2 by path, pushes, a
      teammate pulls) run once on the live dev server.

---

## 10. Implementation steps (ordered commits)

| # | Commit | Contents | Estimate |
|---|---|---|---|
| 1 | `perf(tree): build_from_flat reuses unchanged folders` | `old_tree_ids` / `file_unchanged` on `build_from_flat`; `write_file` passes them; id-equality tests | 0.5 day |
| 2 | `feat(push): push with a dirty working copy` | 5.4 + 9.3; CHANGELOG | 0.5 day |
| 3 | `feat(commit): commit <paths>` | `Safe_Str__Pathspec`, `Vault__Pathspec`, `_scan_paths` / `under=`, `_commit_selected`, `_commit_paths`, `Vault__Partial_Commit_Error`, CLI parsing (positional rule), `--json`; tests 9.1 | 1.5 days |
| 4 | `feat(commit): -p, --list-hunks, --hunk` | `Vault__Hunks`, schemas, safe types, `CLI__Hunk_Prompt`; tests 9.2 incl. Git oracle | 2 days |
| 5 | `feat(hooks): runner and commit hooks` | `sgit_ai/core/hooks/`, `Enum__Hook_Name`, `Schema__Hook_Result`, config fields, `COMMIT_EDITMSG`, `-n/--no-verify`, `sgit vault hooks`; tests 9.4 commit part | 1.5 days |
| 6 | `feat(hooks): pre-push, post-merge, post-checkout` | call sites in push, pull, switch, checkout; `push --no-verify`, `write --no-verify`; tests | 1 day |
| 7 | `docs+security: threat model rows, Fixed__Hooks, CHANGELOG, README` | 6, 9.4 security, 9.6 | 0.5 day |

Total about 7.5 days (2.3 ≈ 4.5 days with the push prerequisite and the tree reuse; 2.9 ≈ 3 days). The roadmap's
"1 day / 2 days" for 2.3 did not include the push change, the shared `build_from_flat` reuse, the agent hunk
interface or the Git oracle.

Parser note for step 3: declare `commit_parser.add_argument('args', nargs='*')`; argparse drops a bare `--` from
`nargs='*'` lists, so `cmd_commit` finds the split point by locating `'--'` in `sys.argv` after the `commit` token
(the CLI receives argv through `CLI__Main.run`; pass the raw list down as `args.raw_argv` set in `run` for the
`commit` command only), which keeps the rule testable without patching `sys.argv`.

---

## 11. Open decisions for Dinis

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | Staging area | A none / B opt-in `sgit add` / C Git-exact | **A** now; B later as an extension if asked (5.7) |
| D2 | `sgit commit -m x y`: `y` becomes a path (Git) instead of being ignored | Git rule / keep ignoring | **Git rule**, with the loud note when `y` matches nothing |
| D3 | Pathspec scope | literal + folders + `* ? []` / add `:!exclude` now / full Git magic | **literal + folders + wildcards**, `:!` as a small follow-up; case-sensitive everywhere |
| D4 | `e` (edit hunk) in `-p` | include / defer | **defer**: agents use `--hunk`; humans rarely use `e` |
| D5 | Hooks path inside the working tree (Husky pattern) | refuse / allow with opt-in / allow | **allow only with `--allow-tracked`**, plus the "changed in last pull" notice |
| D6 | Where hooks are configured | `sgit vault hooks` / a new top-level `sgit config` (Git's `core.hooksPath`) | **`sgit vault hooks`** now (no Rule 9 edit); revisit if `sgit config` arrives for the merge style (design 01) |
| D7 | Windows hooks | `.exe/.cmd/.bat/.ps1` + `#!` via `sh` on PATH / POSIX only | **support Windows as described**, tested in the Windows CI job |
| D8 | Hook timeout | none (Git) / config / env only | **none by default, `SGIT_HOOK_TIMEOUT` for agents** |
| D9 | Commit hooks for other commit-making commands (`revert --as-commit`, merge commits from pull, `history undo`) | `commit` only / also `revert --as-commit` | **`commit` only** in the first cut; pull's merge commit runs none (Git runs `pre-merge-commit`, a non-goal here) |
| D10 | Untracked files under a folder pathspec / by name | commit them (sgit's "working copy is the index") / refuse like Git | **commit them**: sgit has no `add`, so refusing would make new files uncommittable by path |
