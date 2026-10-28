# Design 01: line-level three-way merge (opt-in) and `sgit history cherry-pick`

> Read with [`design__00__index-and-reconciliation.md`](design__00__index-and-reconciliation.md): where the two disagree (shared foundations F1–F9, the in-progress rules), the index wins.

**Roadmap items:** 2.1 (line-level merge) and 2.8 (cherry-pick), from `roadmap__git-parity.md` (same folder).
**Status:** design. No code has been written.
**Code read at:** `3a1d72a` (branch `claude/charming-babbage-5hzcxq`).
**Git behaviour checked:** git 2.43.0 in this sandbox, using `git merge-file` (outputs quoted below).

**In one paragraph.** Today every sgit merge compares files by blob id. When both sides changed a file, sgit keeps
ours and writes theirs next to it as `<path>.conflict`. That stays the default. A new opt-in style, `lines`, runs
a Git-compatible three-way line merge on exactly those files. A clean result becomes a new blob in the merge
commit. A rough edge becomes Git's `<<<<<<< ======= >>>>>>>` markers in the file itself.

- **Where the style is chosen:** per command (`--merge lines|files` on `pull` and `branch merge`), or per clone
  (`merge_style` in `.sg_vault/local/config.json`).
- **What it touches:** the vault format does not change. A merge result is an ordinary commit, so there is no
  version gate, and old clients and the web UI are unaffected.
- **Cherry-pick:** `sgit history cherry-pick <commit>` is the same three-way merge with base = the picked
  commit's parent, ours = HEAD and theirs = the picked commit. It obeys the same style.

---

## 1. Summary and the Git behaviour matched

### 1.1 What Git does

| Git | Behaviour | sgit target |
|---|---|---|
| `git merge`, `git pull` (ort strategy) | Content merge per file through `ll_merge` → `xdl_merge` (xdiff). Conflicts are written into the file with markers, and the index holds stages 1–3. `merge.conflictStyle` = `merge` (default), `diff3` or `zdiff3`. | `--merge lines`, conflict style `merge` (default) or `diff3` |
| `git merge-file -p [--diff3] -L ours -L base -L theirs O B T` | The same xdiff engine on three files. Exit code = number of conflicts (capped at 127), 0 = clean, 255 = error (binary). Level `XDL_MERGE_ZEALOUS_ALNUM`, Myers diff. | **Our oracle** (byte-exact on unique-line inputs, §9.3) |
| `git cherry-pick <c>` | Three-way merge with base = `c^`, ours = HEAD, theirs = `c`. A new commit with the original message; `-x` appends `(cherry picked from commit <id>)`. `--continue`, `--abort`, `--skip`. A merge commit needs `-m <n>`. An empty result stops ("The previous cherry-pick is now empty"). Conflicts → exit 1 with CHERRY_PICK_HEAD set. | `sgit history cherry-pick` (§3.3) |
| Binary files | `git merge-file`: `error: Cannot merge binary files`, exit 255. `git merge`: whole-file conflict, ours kept. Binary = a NUL in the first 8,000 bytes (`buffer_is_binary`). | Binary → today's whole-file `.conflict` behaviour |
| modify/delete, delete/modify | `CONFLICT (modify/delete)`; the modified version stays in the working tree. Not a content merge. | Unchanged: today's whole-file rule |

### 1.2 Git behaviours confirmed here with `git merge-file` (2.43.0)

These become the fixed vectors of §9.2.

| # | Case | Git output (abridged) | Exit |
|---|---|---|---|
| G1 | ours `b→B1`, theirs `b→B2`, theirs `e→E` | `<<<<<<< ours / B1 / ======= / B2 / >>>>>>> theirs`, then `E` merged cleanly | 1 |
| G2 | the same with `--diff3` | adds `||||||| base / b` between the ours and theirs sections | 1 |
| G3 | both sides make the identical change (`b→X`) | clean, `X` | 0 |
| G4 | **adjacent** changes (ours line 2, theirs line 3) | **one conflict** spanning both lines (touching ranges conflict) | 1 |
| G5 | changes one unchanged line apart (ours line 2, theirs line 4) | clean | 0 |
| G6 | both insert different lines at the same point | conflict | 1 |
| G7 | both insert the identical line at the same point | clean | 0 |
| G8 | partial overlap: ours `b,c→X,Y`, theirs `b,c→X,Z` (merge style) | `X` outside, conflict only `Y` / `Z` (zealous refinement) | 1 |
| G9 | G8 with `--diff3` | no refinement: ours `X,Y`, base `b,c`, theirs `X,Z` | 1 |
| G10 | two conflicts separated by 1, 2 or 3 unchanged lines | coalesced into **one** conflict including the lines between | 1 |
| G11 | the same separated by 4 lines | two conflicts | 2 |
| G12 | separated by 4 lines with no alphanumeric character (`}` ×4) | coalesced into one (`ZEALOUS_ALNUM`) | 1 |
| G13 | all three sides CRLF | marker lines end in `\r\n` | 1 |
| G14 | both sides' last line without a newline, conflicting | a `\n` is added before each marker; the result ends with `>>>>>>> theirs\n` | 1 |
| G15 | theirs only drops the final newline | clean, result has no final newline | 0 |
| G16 | add/add (empty base) | one conflict over the differing region | 1 |
| G17 | a NUL byte in a side | `error: Cannot merge binary files` | 255 |
| G18 | `--marker-size 3` | `<<< ours` (sgit fixes the size at 7) | 1 |

`git merge` itself uses `XDL_MERGE_ZEALOUS` through `ll_merge`, and merge-ort uses the histogram diff. We match
`git merge-file` (Myers, `ZEALOUS_ALNUM`) because it is the oracle every developer has installed. Where Myers and
histogram place a hunk differently, sgit can differ from `git merge` but never from `git merge-file`. Section 11,
D9, decides whether to stop there.

---

## 2. Scope and non-goals

**In scope**

1. A line-level three-way merge engine (`Vault__Line_Diff`, `Vault__Line_Merge`) on bytes, with conflict styles
   `merge` and `diff3`.
2. **Opt-in** style selection:
   - flag `--merge lines|files` on `pull` and `branch merge`;
   - per-clone default `merge_style` in `Schema__Local_Config`;
   - optionally the environment variable `SGIT_MERGE_STYLE` (decision D1).
   - The default stays `files` (today's behaviour, byte for byte).
3. The same engine is used, when `lines` is selected, by the other three callers of `three_way_merge`: the rewind
   re-apply (`Step__Pull__Merge._take_rewind`), `history revert --as-commit` and the new cherry-pick.
4. Conflict handling for marker files:
   - merge state records which paths hold markers;
   - `commit` refuses while complete marker blocks remain;
   - `resolve <file>` marks a hand-edited file resolved;
   - `resolve --ours/--theirs` restores a side;
   - `merge-abort` restores ours.
5. `sgit status` shows an in-progress merge. It does not today (§4.6).
6. `sgit history cherry-pick <commit>…` with `-x`, `--continue`, `--abort`, `--json`.
7. The pre-existing defect found while checking (§4.5): `commit` while `.conflict` files exist commits the
   `.conflict` files into the vault. Fixed for both styles (decision D3).

**Non-goals (this round)**

- `zdiff3`, a configurable marker size, `-X ours/theirs/union` per hunk. The engine supports
  ours/theirs/union internally for tests, not on the CLI.
- The histogram or patience diff, and the indent heuristic.
- The recursive merge-base (virtual base) for criss-cross histories. `find_lca` keeps returning one LCA
  (`Vault__Fetch.find_lca`, `sgit_ai/core/actions/fetch/Vault__Fetch.py:78`).
- Rename detection (item 2.4). Merge attributes or `.gitattributes`. Per-file merge drivers.
- `cherry-pick -m <parent>` (merge commits are refused), commit ranges `A..B`, `--skip`, `-n/--no-commit`,
  `--edit`.
- Pull `--json`; the pull exit code (stays 0 on conflicts, decision D6).
- The web UI's merge. It keeps whole-file `.conflict` semantics and is not touched.

---

## 3. CLI surface

Rule 9: `pull` and `branch merge` keep their places. `cherry-pick` is about commits, so it goes under `history`.
`TOP_LEVEL_COMMANDS` is unchanged.

### 3.1 `sgit pull` and `sgit branch merge <name>`

New options on both parsers (`CLI__Main.py:398` pull; `CLI__Branch.py:52` branch merge):

| Option | Values | Default | Meaning |
|---|---|---|---|
| `--merge STYLE` | `files`, `lines` | the clone's `merge_style`, else `SGIT_MERGE_STYLE` (if D1), else `files` | How files changed on both sides are merged |
| `--conflict STYLE` | `merge`, `diff3` | the clone's `conflict_style`, else `merge` | Marker layout in `lines` mode (Git's `--conflict=<style>` / `merge.conflictStyle`); ignored with `files` |

Precedence: flag > environment (if D1) > `.sg_vault/local/config.json` > default. An invalid value is an argparse
`choices` error (exit 2). `branch switch` pulls with the clone's configured style (no flag); `serve pull` is
fast-forward only and unaffected.

**Output, `lines` style, clean.** Today's block, plus one line per line-merged file:
```
Merged: 1 added, 4 modified, 0 deleted
  Line-merged 2 file(s) that both sides changed:
    ≈ notes/plan.md
    ≈ src/app.py
```

**Output, `lines` style, conflicts.** It replaces `CLI__Vault.py:995-1009`. The quick options stay, and the second
reason column is new:
```
CONFLICT: 3 file(s) have merge conflicts.
  ! notes/plan.md      conflict markers in the file (2 hunk(s)): edit it, then sgit commit
  ! img/logo.png       binary: kept yours, theirs is in img/logo.png.conflict
  ! data/big.csv       too large for a line merge (12.4 MB): kept yours, theirs is in data/big.csv.conflict

Quick options:
  sgit resolve --all --ours       Keep all your local versions
  sgit resolve --all --theirs     Accept all remote versions
  sgit resolve <file>             Mark a file you edited by hand as resolved
  sgit resolve <file> --ours      Keep your version of one file
  sgit resolve <file> --theirs    Take remote version of one file

Then:                             sgit commit
Or to abandon the merge:          sgit merge-abort
See unresolved conflicts:         sgit status  (or sgit resolve --show)
```
With `--merge files` (the default), the output is exactly today's.

**Exit code:** 0, as today, including on conflicts (decision D6).

### 3.2 `sgit resolve`

| Form | Today | New |
|---|---|---|
| `resolve <file> --ours` | deletes `<file>.conflict` | the same for `.conflict` paths. For a **marker** path it writes ours' blob back to `<file>`, replacing the markers. |
| `resolve <file> --theirs` | moves `<file>.conflict` onto `<file>` | the same; for a marker path it writes theirs' blob to `<file>` |
| `resolve <file>` (no side) | `error: specify --ours or --theirs` | **marks `<file>` resolved** (Git's `git add` after a hand edit). It refuses while the file still holds a complete marker block, unless `--force`. For a `.conflict` path it also removes `<file>.conflict`. |
| `resolve --all --ours/--theirs` | per path | per path, by kind |
| `resolve --show` | 3-way verdict view | adds a kind column: `markers` / `whole-file` |

New option: `--force` (only with a bare `resolve <file>`).

### 3.3 `sgit history cherry-pick`

```
sgit history cherry-pick [-x] [--merge files|lines] [--conflict merge|diff3] [--json] <commit>... [directory]
sgit history cherry-pick --continue [--json] [directory]
sgit history cherry-pick --abort [directory]
```

| Item | Detail |
|---|---|
| `<commit>` | Anything `Vault__Revision.resolve` accepts: an id or a 4+ hex prefix, `HEAD~n`, `@{n}`, a tag, `tag:<name>`. A full `obj-cas-imm-…` id that is not local is fetched (§5.9). Several commits are applied in the order given (decision D5). |
| `-x` | Append `\n\n(cherry picked from commit <full id>)` to the message (Git's `-x`). Off by default. |
| `--merge` / `--conflict` | As in §3.1, with the same precedence |
| `--continue` | After resolving: commit the pick (single parent, the picked message), then apply the remaining listed commits |
| `--abort` | `merge-abort` for a pick: the head and working copy go back to before the first pick of the sequence |
| `--json` | One object on stdout, below |

Refusals (`Vault__Revision_Error`, exit 1, nothing written):
- a merge commit: `<id> is a merge commit; cherry-pick of merges is not supported`;
- a root commit: allowed, base = the empty tree, as in Git;
- a dirty working copy: `cherry-pick needs a clean working copy: commit your changes or sgit vault stash them
  first. Nothing was changed.`;
- a merge or pick already in progress;
- a read-only clone;
- a scoped clone, when the picked commit changes paths outside the scope (§7);
- under `signatures-required`, a picked commit that does not verify (§6).

**Text output:**
```
Picked 3f9a1c2b4d5e "Fix the import order" as a new commit 7a8b9c0d1e2f:
  ~ src/app.py
  ≈ notes/plan.md   (line-merged)
Push it to share it: sgit push
```
Conflicts:
```
CONFLICT cherry-picking 3f9a1c2b4d5e "Fix the import order": 1 file(s).
  ! src/app.py      conflict markers in the file (1 hunk(s))
Resolve (edit, or sgit resolve <file> --ours/--theirs), then: sgit history cherry-pick --continue
Or: sgit history cherry-pick --abort
```
Empty: `nothing to cherry-pick: the changes of 3f9a1c2b4d5e are already in the head` (exit 1; Git stops too).

**Exit codes:** 0 picked, 1 conflicts or refused (Git parity; decision D6), 2 usage.

**`--json` shape:**
```json
{"status": "picked" | "conflicts" | "empty",
 "picked": ["obj-cas-imm-…"],
 "commit_ids": ["obj-cas-imm-…"],
 "stopped_at": "obj-cas-imm-…" | null,
 "remaining": ["obj-cas-imm-…"],
 "files": {"modified": [], "added": [], "deleted": [], "line_merged": []},
 "conflicts": [{"path": "src/app.py", "kind": "markers", "hunks": 1}]}
```

### 3.4 `sgit status`

A new block printed when `merge_state.json` exists. Today `status` returns the merge fields
(`Vault__Sync__Status.py:215-228`) but `CLI__Vault.cmd_status` never prints them.
```
Merge in progress (pull, lines style): 2 unresolved, 1 resolved
  ! notes/plan.md   markers: edit it, then sgit commit (or sgit resolve notes/plan.md --ours/--theirs)
  ! img/logo.png    whole file: theirs is in img/logo.png.conflict
  ✓ README.md
Finish: sgit commit   ·   Abandon: sgit merge-abort
```
For a pick, the heading is `Cherry-pick in progress (3f9a1c2b4d5e "Fix the import order")` and the finish line is
`sgit history cherry-pick --continue / --abort`.

---

## 4. How the code works today

### 4.1 The classifier

`sgit_ai/core/actions/merge/Vault__Merge.py:14-80`, `three_way_merge(base_map, ours_map, theirs_map)`.

- **Inputs:** flat maps `{path: {blob_id, size, content_hash, content_type, large}}`.
- **Rule:** per path, compare blob ids only:
  - neither side changed → ours;
  - one side changed → that side;
  - both changed to the same blob → ours;
  - both changed differently (`:47-49`) → ours plus a conflict;
  - add/add with different blobs (`:57-60`) → ours plus a conflict;
  - modify/delete and delete/modify (`:63-71`) → the modified side plus a conflict.
- **Returns:** `merged_map, conflicts, added, modified, deleted`.

`write_conflict_files` (`:82-106`) decrypts **theirs'** blob to `<path>.conflict`, through
`Vault__Path_Guard.safe_join`. It skips silently when theirs has no entry (ours modified / theirs deleted) and on
any exception. `CONFLICT_SUFFIX = '.conflict'` (`:8`; duplicated as `Vault__Sync__Base.py:31`, pinned equal by a
test).

### 4.2 The callers

| Caller | File:line | Conflict handling today |
|---|---|---|
| Pull and branch merge, three-way path | `sgit_ai/workflow/pull/Step__Pull__Merge.py:120-185` | The guard runs first (`:138`); the working copy is written with `merged_map` (`:140`); conflicts → `.conflict` files plus `Vault__Merge__State.new_state(...)` written; **the clone ref is not moved**. Clean → `build_from_flat` → a signed two-parent commit → ref written (`:157-182`). |
| Rewind re-apply | `Step__Pull__Merge._take_rewind`, `:245-310` | any conflict → `Vault__Ref_Rewind_Error`, nothing written (`:269-273`) |
| `history revert --as-commit` | `sgit_ai/core/actions/history/Vault__Sync__History_Edit.py:60-113`; merge at `:85` with base = target, ours = head, theirs = target's parent | any conflict → `Vault__Revision_Error` (`:86-91`) |
| (`branch merge` is pull with `merge_from`) | `Vault__Sync.merge_branch` → `Vault__Sync__Pull.pull(merge_from=…)`, `sgit_ai/core/Vault__Sync.py:230-234`, `Vault__Sync__Pull.py:80-123` | as pull |

`Pull__Workspace.merge_helper` is a `Vault__Merge` (`sgit_ai/workflow/pull/Pull__Workspace.py:22,62`).

### 4.3 Merge state

- **Schema:** `sgit_ai/schemas/merge/Schema__Merge_State.py`: `schema_version`, `ours_commit_id`,
  `theirs_commit_id`, `lca_id`, `started_at`, `conflict_paths`, `resolved_paths`.
- **Manager:** `Vault__Merge__State` (`sgit_ai/core/actions/merge/Vault__Merge__State.py`), which writes
  `.sg_vault/local/merge_state.json` (`:9,14-16`).
- **Guard:** `check_not_in_progress` (`:42-49`) is called by `pull` (`Vault__Sync__Pull.py:88`).

### 4.4 Resolve and abort

- `Vault__Merge__Resolve` (`sgit_ai/core/actions/merge/Vault__Merge__Resolve.py`): `--ours` deletes
  `<path>.conflict` (`:79-86`); `--theirs` `os.replace`s it onto `<path>` (`:88-94`). It holds no crypto.
- `Vault__Merge__Abort.abort` (`Vault__Merge__Abort.py:13-39`) removes the `.conflict` files, then
  `Vault__Sync__Pull.reset(directory, ours_commit_id)`, then deletes the state.
- CLI: `CLI__Merge.cmd_resolve` and `cmd_merge_abort` (`sgit_ai/cli/CLI__Merge.py:17-54,126-144`); `branch
  merge-abort` (`CLI__Branch.py:60-62`).

### 4.5 Commit during a merge, and a defect

`Vault__Sync__Commit.commit` (`sgit_ai/core/actions/commit/Vault__Sync__Commit.py:147-197`):
- reads the merge state;
- `has_conflict_files` = any `*.conflict` file seen by the scan (`Vault__Sync__Base.py:569-570`);
- with a state and no `.conflict` files: a merge commit (second parent = `theirs_commit_id`) and the state is
  deleted;
- with `.conflict` files present, **it commits anyway**, as a single-parent commit, and keeps the state.

`*.conflict` is not in any ignore rule (`Vault__Ignore.py:6-27` ignores folders only), so **the `.conflict` files
themselves are committed**.

Reproduced here: pull → conflict on `shared.txt` → `sync.commit(..., 'while conflicted')` returned
`files_changed: 1, merge_commit: False`, and that one file is `shared.txt.conflict`. After
`resolve shared.txt --theirs` the next commit had `files_changed: 2` (the `.conflict` deleted, `shared.txt`
changed) and `merge_commit: True`. Every teammate who pulls between the two commits receives `shared.txt.conflict`.

### 4.6 Status and the CLI

- **Status:** `Vault__Sync__Status.status` returns `merge_in_progress`, `merge_ours/theirs/lca`,
  `merge_conflicts`, `merge_resolved` (`sgit_ai/core/actions/status/Vault__Sync__Status.py:215-228`).
  `CLI__Vault.cmd_status` (`sgit_ai/cli/CLI__Vault.py:826+`) prints none of it, although the pull output says "See
  unresolved conflicts: sgit status".
- **Pull exit code:** pull prints conflicts and returns normally, so it exits 0 (`CLI__Vault.cmd_pull`, `:995-1009`).

### 4.7 Blobs and entries

- **Writing a blob:** `Vault__Sub_Tree.encrypt_or_reuse_blob(content, old_entry, read_key)`
  (`sgit_ai/storage/Vault__Sub_Tree.py:517-529`):
  - `content_hash` = `sha256(plaintext)[:12]` (`Vault__Crypto.content_hash`, `Vault__Crypto.py:335`);
  - a blob whose hash matches the old entry is reused;
  - otherwise `crypto.encrypt(read_key, content, deflate=True)` (deflated on a `blob-deflate` vault) and
    `obj_store.store`;
  - `large` = ciphertext > 4 MiB (`LARGE_BLOB_THRESHOLD`, `:9`).
- **Building trees from a merged map:** `build_from_flat(flat_map, read_key, opaque=…)` (`:105-130`) uses each
  entry's `blob_id`, `size`, `content_hash`, `content_type` and `large`.
- **Reading:** `obj_store.load` + `crypto.decrypt` handle both envelopes and pack-store clones transparently.
- **Push:** it collects the blobs of every commit in the pushed chain, so a new merge blob is uploaded with the
  merge commit.

### 4.8 The dirty-tree guard and selective writes

- **The guard:** `Step__Pull__Merge._guard_working_tree` (`:327-362`) computes `touched` = paths whose blob differs
  between `ours_map` and `merged_map`, scans with `verify=touched`, and refuses (`Vault__Dirty_Working_Tree_Error`)
  before any write if a dirty path would be overwritten. `blocked_targets` also refuses untracked files in the way.
- **Today's blind spot:** `.conflict` targets are not checked, so an untracked `x.conflict` is overwritten.
- **Selective writes:** `_write_selective` (`:218-230`) writes through `Pull__Selective.split` (selective working
  copies) and records the writes (`after_write`).

### 4.9 Blob availability

- `Step__Pull__Fetch_Missing` fetches theirs' commits and trees, and blobs unless the clone is `--sparse`
  (`include_blobs = not is_sparse`, `Step__Pull__Fetch_Missing.py:124`).
- On a scoped clone, only the scope is fetched.
- Base blobs (the LCA's) are local whenever the clone held that commit's files. That is not the case for
  `--sparse`, or across a shallow boundary.
- `Vault__Sync__Sparse.sparse_fetch` + `_save_verified` (`sgit_ai/core/actions/sparse/Vault__Sync__Sparse.py:106-175,
  262-271`) is the existing verified on-demand blob fetch: `api.batch_read` for small blobs, `api.read_large` for
  large ones, and `Vault__Verified_Write`.

### 4.10 Diff code in the tree

`Vault__Diff` uses `difflib` for display and `_is_binary` = a NUL in the first 8,192 bytes
(`sgit_ai/core/actions/diff/Vault__Diff.py:24,534-535`). `three_way_conflict_view` (`:664+`) powers
`resolve --show`. No three-way line-merge code exists.

---

## 5. Design

### 5.1 New modules and classes

| File | Class | Purpose |
|---|---|---|
| `sgit_ai/core/text/__init__.py` | — | New package for the text algorithms; the history tools in items 2.4, 2.5 and 2.7 will reuse it |
| `sgit_ai/core/text/Vault__Line_Splitter.py` | `Vault__Line_Splitter(Type_Safe)` | `split(data: bytes) -> list` keeps each line's `\n` and the last line's absence of one. `is_binary(data: bytes) -> bool` (NUL in the first 8,000 bytes, Git's `FIRST_FEW_BYTES`). `eol_of(line: bytes) -> bytes`. |
| `sgit_ai/core/text/Vault__Line_Diff.py` | `Vault__Line_Diff(Type_Safe)` | Myers diff over interned line ids: `diff(a_ids, b_ids) -> list[Schema__Line_Hunk]`, linear space, with a cost cap |
| `sgit_ai/core/text/Vault__Line_Merge.py` | `Vault__Line_Merge(Type_Safe)` | `merge(base: bytes, ours: bytes, theirs: bytes, conflict_style, labels) -> tuple(bytes, Schema__Line_Merge_Result)` |
| `sgit_ai/core/actions/merge/Vault__Content_Merger.py` | `Vault__Content_Merger(Type_Safe)` | Bridges the classifier to the engine: loads and decrypts three blobs (fetching missing ones), runs the engine, stores a clean result as a blob, returns an outcome per path |
| `sgit_ai/core/actions/history/Vault__Cherry_Pick.py` | `Vault__Cherry_Pick(Vault__Sync__Base)` | `pick(directory, specs, record_origin, style, conflict_style)`, `continue_(directory)`, `abort(directory)` |
| `sgit_ai/cli/CLI__Cherry_Pick.py` | `CLI__Cherry_Pick(Type_Safe)` | `cmd_cherry_pick(args)`; registered in `sgit_ai/plugins/history/CLI__History.py` |

### 5.2 New types and schemas

All in `sgit_ai/safe_types/` and `sgit_ai/schemas/`, following CLAUDE.md (no raw primitives as fields; collections
annotated without values).

| Type | Kind | Values or fields |
|---|---|---|
| `Enum__Merge_Style` | Enum | `FILES='files'`, `LINES='lines'` |
| `Enum__Conflict_Style` | Enum | `MERGE='merge'`, `DIFF3='diff3'` |
| `Enum__Line_Merge_Outcome` | Enum | `CLEAN`, `CONFLICT`, `BINARY`, `TOO_LARGE`, `TOO_DIFFERENT`, `MISSING_BLOB`, `NOT_TEXT_PAIR` (modify/delete) |
| `Enum__Merge_Operation` | Enum | `PULL='pull'`, `BRANCH_MERGE='branch-merge'`, `CHERRY_PICK='cherry-pick'` |
| `Enum__Conflict_Kind` | Enum | `MARKERS='markers'`, `WHOLE_FILE='whole-file'` |
| `Safe_UInt__Line_Number` | Safe_UInt | A line index |
| `Safe_UInt__Hunk_Count` | Safe_UInt | Conflict hunks |
| `Safe_Str__Merge_Reason` | Safe_Str | Printable ASCII, `max_length = 200`: why a path fell back to whole-file ("binary", "too large for a line merge (12.4 MB)") |
| `Safe_Str__Conflict_Label` | Safe_Str | `regex = [^\x20-\x7E]` (replaced), `max_length = 80`, `trim_whitespace`. Labels are built from vault data (branch names, commit messages): a newline or a marker string must never reach the file. |
| `Schema__Line_Hunk` | Type_Safe | `base_start`, `base_end`, `side_start`, `side_end` : `Safe_UInt__Line_Number` (half-open `[start, end)`) |
| `Schema__Conflict_Labels` | Type_Safe | `ours`, `base`, `theirs` : `Safe_Str__Conflict_Label` |
| `Schema__Line_Merge_Result` | Type_Safe | `outcome : Enum__Line_Merge_Outcome`, `hunks : Safe_UInt__Hunk_Count`, `reason : Safe_Str__Merge_Reason = None` |
| `Schema__Content_Merge_Outcome` | Type_Safe | `path : Safe_Str__File_Path`, `outcome : Enum__Line_Merge_Outcome`, `kind : Enum__Conflict_Kind = None`, `hunks : Safe_UInt__Hunk_Count`, `blob_id : Safe_Str__Object_Id = None` (clean), `reason : Safe_Str__Merge_Reason = None` |
| `Schema__Merge_Conflict` | Type_Safe | `path : Safe_Str__File_Path`, `kind : Enum__Conflict_Kind`, `hunks : Safe_UInt__Hunk_Count` (status and `--json`) |

**Additions to `Schema__Merge_State`** (`sgit_ai/schemas/merge/Schema__Merge_State.py`). All are optional or
default-empty, so an older merge state file loads unchanged (Type_Safe accepts the missing fields), and a file
written by this build loads in an older build (Type_Safe accepts unknown keys; checked on
`Schema__Object_Commit.from_json`):
```
merge_style          : Enum__Merge_Style      = None     # what produced this state
conflict_style       : Enum__Conflict_Style   = None
operation            : Enum__Merge_Operation  = None     # None = pull (legacy files)
marker_paths         : list[Safe_Str__File_Path]         # conflict paths whose file holds markers
source_commit_id     : Safe_Str__Commit_Id    = None     # cherry-pick: the commit being picked
remaining_commit_ids : list[Safe_Str__Commit_Id]         # cherry-pick: still to apply (D5)
sequence_start_id    : Safe_Str__Commit_Id    = None     # cherry-pick: head before the first pick (for --abort)
record_origin        : bool                   = False    # cherry-pick -x
```
`Vault__Merge__State.new_state(...)` gains keyword arguments for these. `_migrate_legacy` is unchanged.

**Additions to `Schema__Local_Config`** (`sgit_ai/schemas/Schema__Local_Config.py`):
```
merge_style    : Enum__Merge_Style    = None   # None = files (today)
conflict_style : Enum__Conflict_Style = None   # None = merge
```
An older build that rewrites `config.json` drops these fields, and the clone falls back to `files`. That fails
safe: the default is today's behaviour.

### 5.3 The diff: `Vault__Line_Diff`

**Input preparation (in `Vault__Line_Merge`)**

1. Split each side with `Vault__Line_Splitter.split`. A line is the bytes up to and including `\n`; the last line
   may lack it. `\r` stays part of the line, so `a\r\n` ≠ `a\n`, as in Git without whitespace options.
2. Intern every distinct line (bytes, including the eol) to a small int with one dict shared by the three files.
   The diff then compares ints.

**Algorithm: Myers 1986, "An O(ND) Difference Algorithm", linear-space variant** (§4b, the middle-snake divide and
conquer, as xdiff's `xdl_split`). Steps:

1. **Trim the common prefix and suffix** (xdiff's `xdl_trim_ends`). This is O(n) and removes most work on
   real files.
2. **Discard lines with no match** (xdiff's `xdl_cleanup_records`, simplified): a line id that occurs only in A
   (or only in B) can never be in the LCS. Mark it as changed up front and run Myers on the remaining
   subsequences, keeping an index map back to the originals. This is a large speed-up for "mostly different"
   files.
3. **Middle snake recursion** on the remaining ranges. Each `find_middle_snake(a_lo, a_hi, b_lo, b_hi)` runs the
   forward and backward greedy searches with two V arrays of size `2·max_d + 1` (Python lists of ints), stops at
   the first overlap, and recurses on both halves. Memory is O(N+M).
4. **Cost cap:** a running count of the edit cost `D` per top-level call. If `D` exceeds
   `MAX_EDIT_COST = 5,000` (lines added + removed), the diff stops with `Vault__Line_Diff__Too_Different`.
   `Vault__Line_Merge` turns that into outcome `TOO_DIFFERENT`, and the path falls back to the whole-file
   conflict. (xdiff instead switches to a heuristic split; we prefer a clear fallback: decision D8.)
5. **Produce hunks:** walk the edit script and emit maximal `Schema__Line_Hunk(base_start, base_end, side_start,
   side_end)`. A pure insertion has `base_start == base_end`; a pure deletion has `side_start == side_end`.
6. **Compaction** (deterministic placement in ambiguous runs, xdiff's `xdl_change_compact` without the indent
   heuristic): for each group of changed lines in A (and separately in B), slide it **down** while the line after
   the group equals the group's first line, then back **up** only if that aligns it with a change group on the
   other side. Git applies the same rule. This makes the output deterministic. Exact equality with Git on
   repeated-line inputs is not promised (§9.3).

**Interface:**
```
class Vault__Line_Diff(Type_Safe):
    max_edit_cost : Safe_UInt__Line_Number = 5000
    def diff(self, a_ids: list, b_ids: list) -> list            # list[Schema__Line_Hunk], sorted by base_start
```
Raises `Vault__Line_Diff__Too_Different(Exception)` (in `sgit_ai/core/Vault__Errors.py`).

### 5.4 The merge: `Vault__Line_Merge` (xdiff `xdl_merge` semantics)

**Pre-checks, in order** (each returns `(b'', result)` with the outcome and a `reason`):

| Check | Outcome |
|---|---|
| any side `is_binary` | `BINARY` |
| any side longer than `MAX_MERGE_BYTES = 8 MiB`, or more than `MAX_MERGE_LINES = 200,000` lines | `TOO_LARGE` |

**Step 1: two diffs.** `H_o = diff(B, O)` and `H_t = diff(B, T)`, as base-relative hunks.

**Step 2: walk both hunk lists in base order and group.** Let `i`, `j` index `H_o` and `H_t`.

- If `H_o[i].base_end < H_t[j].base_start`, the ours hunk is strictly before theirs, with at least one unchanged
  base line between. Emit it as a **one-sided change (ours)** and advance `i`. Symmetrically for theirs.
- Otherwise the hunks **overlap or touch** (`end == start` counts, G4; two insertions at the same point overlap,
  G6). Open a **group** with `g_lo = min(starts)` and `g_hi = max(ends)`. Keep absorbing the next hunk from either
  list while its `base_start <= g_hi`, extending `g_hi`.
- For each group, map the base range `[g_lo, g_hi)` onto each side. With `δ_o(k)` = the sum of `(side_len −
  base_len)` over the ours hunks ending at or before base line `k`:
  - `ours_lo = g_lo + δ_o(before group)`;
  - `ours_hi = g_hi + δ_o(through group)`;
  - likewise for theirs;
  - a side with no hunk in the group gets the base lines, i.e. its range is the base range shifted by its δ.
- **EAGER:** if `O[ours_lo:ours_hi] == T[theirs_lo:theirs_hi]` (identical change, G3/G7), emit it as a non-conflict.
- Otherwise emit `Conflict(base=[g_lo,g_hi), ours=[ours_lo,ours_hi), theirs=[theirs_lo,theirs_hi))`.

**Step 3: refine, ZEALOUS (merge style only, not diff3; Git caps diff3 at EAGER, G9).** For each conflict where
both sides are non-empty, diff the ours text against the theirs text. Equal runs become non-conflict lines; each
differing region becomes its own smaller conflict. Its base range is the whole original base range for the first
sub-conflict and empty for the rest, as in xdiff's `xdl_refine_conflicts`; base is only printed in diff3 style,
which skips this step.

**Step 4: simplify, ZEALOUS_ALNUM (merge style only).** Walk adjacent conflicts `c1`, `c2` in ours coordinates.
Let `gap` = the ours lines between `c1.ours_hi` and `c2.ours_lo`. **Merge** them when `len(gap) <= 3` (G10/G11) or
when no gap line contains an ASCII alphanumeric byte `[0-9A-Za-z]` (G12). The merged conflict:
- ours = from `c1.ours_lo` to `c2.ours_hi`;
- theirs = the matching span in theirs coordinates, including the same gap lines (they are common text);
- base = the span covering both.

Repeat until stable.

**Step 5: assemble the output.** Walk the base in order:
- unchanged base lines → copied;
- a one-sided ours or theirs change → that side's lines;
- a resolved identical change → those lines;
- a conflict → the block below.

The marker size is 7 and `eol` = `\r\n` when CR is needed, else `\n`:
```
<<<<<<< {labels.ours}{eol}
{ours lines}
||||||| {labels.base}{eol}        ← diff3 style only
{base lines}                      ← diff3 style only
======={eol}
{theirs lines}
>>>>>>> {labels.theirs}{eol}
```

- **No final newline (G14):** if a side's block is non-empty and its last line has no `\n`, append `eol` before
  the next marker. The output then always ends a conflict with `>>>>>>> …{eol}`.
- **When CR is needed (G13):** as xdiff's `is_cr_needed`. Look at the line before the conflict in ours (or ours'
  first line if the conflict starts at 0): it must end in `\r\n`, and the same must hold in theirs. If either side
  is undetermined (no eol at all), use base's. Otherwise `\n`.

**Step 6: the result.** No conflicts → `outcome = CLEAN`, content = the assembled bytes. Otherwise
`outcome = CONFLICT`, `hunks` = the number of conflict blocks after simplification. This equals `git merge-file`'s
exit code below 128.

**Labels**, built by the caller and sanitised by `Safe_Str__Conflict_Label`:

| Operation | ours | base | theirs |
|---|---|---|---|
| pull | `ours (this clone {12-hex})` | `base ({12-hex of LCA})` | `theirs ({named branch name} {12-hex})` |
| branch merge | `ours (this clone {12-hex})` | `base ({12-hex})` | `theirs ({merged branch name} {12-hex})` |
| cherry-pick | `HEAD ({12-hex})` | `parent of {12-hex}` | `{12-hex} ({first 50 chars of the subject})` |

A subject is untrusted vault data. Every character outside printable ASCII becomes `_`, and the label is
truncated to 80 characters, so it can never start a new line or contain a marker on its own line.

**Internal options, for tests only:** `favor: ours|theirs|union` resolves every conflict to one side or both (Git's
`--ours/--theirs/--union`, G-oracle), used by property tests. No CLI flag.

### 5.5 The bridge: `Vault__Content_Merger`

```
class Vault__Content_Merger(Type_Safe):
    crypto         : Vault__Crypto
    obj_store      : Vault__Object_Store
    line_merge     : Vault__Line_Merge
    conflict_style : Enum__Conflict_Style = None
    labels         : Schema__Conflict_Labels
    blob_fetcher   : object = None          # callable(list[blob_id]) -> None; fetches and verifies missing blobs
    def merge_entry(self, path, base_entry, ours_entry, theirs_entry, read_key) -> tuple   # (Schema__Content_Merge_Outcome, bytes)
```

`merge_entry` steps:

1. If ours or theirs has no entry (modify/delete): return `NOT_TEXT_PAIR` (the classifier keeps today's rule).
2. Collect the blob ids (base is `None` for add/add). Missing locally ones go to `blob_fetcher` (one batch). If any
   is still missing: `MISSING_BLOB`.
3. Decrypt them (`crypto.decrypt(read_key, obj_store.load(id))`). Base = `b''` for add/add, as Git does.
4. `line_merge.merge(...)`.
5. **Clean:** `blob_id, large, content_hash = Vault__Sub_Tree.encrypt_or_reuse_blob(content, ours_entry,
   read_key)`. A result equal to ours reuses ours' blob. The new entry is:
   - `blob_id`;
   - `size = len(content)`;
   - `content_hash`;
   - `content_type = ours_entry.content_type or theirs_entry.content_type`;
   - `large`.

   Return `CLEAN` with the entry's `blob_id`.
6. **Conflict:** return `CONFLICT` with `kind = MARKERS` and the marker bytes. Nothing is stored in the object
   store: markers never become a blob until the person commits them, and the commit guard (§5.8) refuses that.
7. **Anything else:** return the outcome. The classifier falls back to `WHOLE_FILE`.

### 5.6 Changes to `Vault__Merge.three_way_merge`

The signature becomes:
```
def three_way_merge(self, base_map, ours_map, theirs_map, content_merger=None, read_key: bytes = None) -> dict
```

- **Without `content_merger`:** byte-identical behaviour to today (the `files` style; all current callers pass
  nothing until wired).
- **With it**, at the two "both changed differently" branches only (`:47-49` and `:57-60`), call
  `content_merger.merge_entry(...)`:
  - `CLEAN`: `merged_map[path] = new_entry`, add the path to `modified` and to a new `line_merged` list.
  - `CONFLICT` (markers): `merged_map[path] = ours_map[path]` (unchanged, exactly today's entry), add the path to
    `conflicts` and to `marker_conflicts[path] = (marker_bytes, hunks)`.
  - Other outcomes: today's whole-file conflict, plus `fallbacks[path] = outcome.reason`.

The return dict gains `line_merged : list`, `marker_conflicts : dict`, `fallbacks : dict`. Every other path
(one-sided, identical, deletions) is classified exactly as today, so the line engine runs **only** on files both
sides changed. That is also why the cost is zero on folder-separated agent work (§8).

`write_conflict_files(...)` gains `skip: set = None` and skips the paths in `marker_conflicts`. A new method
`write_marker_files(directory, marker_conflicts) -> list` writes each marker file through
`Vault__Path_Guard().is_writable` + `safe_join` (as today's `.conflict` writer) and returns the paths written.

### 5.7 Pull and branch merge wiring (`Step__Pull__Merge`)

1. **Choose the style.** `Vault__Sync__Pull.pull(..., merge_style=None, conflict_style=None)` sets
   `ws.merge_style` and `ws.conflict_style` (like `ws.no_checkout`, `Vault__Sync__Pull.py:111-114`).
   `Step__Pull__Merge.execute` resolves the effective style with a new `Vault__Merge_Style_Resolver(Type_Safe)`:
   `resolve(flag, local_config) -> (Enum__Merge_Style, Enum__Conflict_Style)` reads the flag, the environment
   (D1), `local_config.merge_style` and the default.
2. **Build the merger** when the style is `lines`: a `Vault__Content_Merger` with `obj_store`, the
   `crypto`, the labels (named branch name, short ids) and `blob_fetcher` = a new
   `Vault__Sync__Base._fetch_blobs_verified(directory, blob_ids)`. That method is extracted from
   `Vault__Sync__Sparse.sparse_fetch`'s download half (`:136-157` + `_save_verified`), so both use one verified
   path.
3. **Three-way path (`:120-185`):**
   - call `three_way_merge(base_map, ours_map, theirs_map, content_merger=merger, read_key=read_key)`;
   - pass the marker paths to the guard as extra writes: `_guard_working_tree(..., extra_writes=set(marker_conflicts))`.
     The marker write replaces the working file, so an uncommitted edit there must refuse the pull before
     anything is written, exactly as an incoming change would. `extra_writes` is added to `touched`, so the scan
     verifies those paths and `plan()` treats them as writes. The `.conflict` targets of whole-file conflicts
     also go to `blocked_targets` (fixes the silent overwrite of an untracked `x.conflict`);
   - `write(ours_map, merged_map, apply_map)` is unchanged. Clean line merges are in `apply_map` because their
     blob differs from ours;
   - on conflicts: `write_conflict_files(..., skip=set(marker_conflicts))` and `write_marker_files(...)`. In a
     selective working copy, record the marker writes with `selective.after_write(written_markers, [])`, so the
     file counts as checked out;
   - the state gets `new_state(..., merge_style, conflict_style, operation, marker_paths=sorted(marker_conflicts))`;
   - on a clean merge: unchanged (`build_from_flat` → commit). New blobs are already in the store.
4. **Report.** `Schema__Pull__State` gains `line_merged_files : list[Safe_Str__File_Path]` and
   `conflict_kinds : list[Schema__Merge_Conflict]`. `_pull_state_to_dict` adds `line_merged` and
   `conflict_details` to the result, and `CLI__Vault.cmd_pull` prints them (§3.1).
5. **Rewind re-apply (`_take_rewind`, `:245-310`):** pass the same merger. Clean line merges are accepted;
   any conflict (markers or whole-file) still refuses before anything is written. Markers are never written there.
6. **`history revert --as-commit`** (`Vault__Sync__History_Edit.py:85`): same rule. The merger comes from the
   clone's configured style (no flag on revert in this round); conflicts still refuse.

### 5.8 Commit, resolve, abort

**`Vault__Sync__Commit.commit`** (`:147-197`). New rules, applied before any blob is written:

1. Load the merge state as today. New helper `Vault__Merge.unresolved(directory, state, seen_conflict_files) ->
   list[Schema__Merge_Conflict]`:
   - a path in `state.conflict_paths` and not in `resolved_paths` is unresolved when it is a marker path whose
     file still contains a **complete marker block**;
   - or when it is a whole-file path whose `<path>.conflict` exists.

   A complete marker block is a line matching `^<{7}( |\r?$)`, followed later by `^={7}\r?$`, followed later by
   `^>{7}( |\r?$)`, checked per line with the file read through `Vault__Path_Guard.read_regular`. A lone
   `=======` underline (reStructuredText) is not a block.
2. Marker paths whose markers are gone (hand-edited) are moved to `resolved_paths` automatically. This is the
   analogue of `git add` after editing; decision D4.
3. **Unresolved paths make the commit refuse** with a new `Vault__Merge_Unresolved_Error` naming each path and the
   remedy. That replaces today's commit-anyway behaviour, under decision D3.
4. With no unresolved paths:
   - `operation` in (`None`, `pull`, `branch-merge`): today's merge commit (second parent `theirs_commit_id`), and
     the state is deleted;
   - `operation == cherry-pick`: §5.9.
5. **Belt and braces:** the scan never commits a `*.conflict` file whose base path is a conflict path of the
   current state. They are dropped from `new_file_map` with a warning line. That is the defect of §4.5.

The new error class `Vault__Merge_Unresolved_Error` goes in `sgit_ai/core/Vault__Errors.py` and joins the list of
deliberate refusals in `CLI__Main._print_friendly_error` (`CLI__Main.py:1204-1218`).

**`Vault__Merge__Resolve`** gains `crypto : Vault__Crypto` and `api : Vault__API = None` (constructed with them in
`CLI__Merge.cmd_resolve`):

| Method | For a marker path | For a whole-file path |
|---|---|---|
| `_resolve_ours` | decrypt ours' blob (`state.ours_commit_id`'s tree entry) and write it to `<path>` through the path guard | unchanged |
| `_resolve_theirs` | decrypt theirs' blob (`theirs_commit_id`'s tree, or the picked commit's for a pick) and write it | unchanged |
| new `mark_resolved(directory, rel_path, force=False)` | refuse while a complete marker block remains, unless `force` | remove `<path>.conflict` |

All three update `conflict_paths` and `resolved_paths` as today (`:30-38`). The `print` calls move to the CLI layer:
the class returns dicts.

**`Vault__Merge__Abort.abort`** is unchanged in shape. It removes the `.conflict` files (marker paths have none),
then `reset(ours_commit_id)` rewrites every file that differs from ours, marker files included. For a pick, it
resets to `sequence_start_id` instead.

### 5.9 Cherry-pick: `Vault__Cherry_Pick`

**`pick(directory, specs, record_origin=False, merge_style=None, conflict_style=None) -> dict`**

1. **Guards:**
   - the clone is not read-only;
   - no merge state (`check_not_in_progress(directory, 'cherry-pick')`);
   - the working copy is clean (`Vault__Sync__History_Edit._require_clean`, reused through a shared base method);
   - the clone has a head.
2. **Resolve every spec** with `Vault__Revision.resolve_soft`. For a full id that is not local, fetch it with
   `_fetch_missing_objects(commit_id=<id>, stop_at=<head>, include_blobs=True)`. That walks the picked commit's
   ancestry until it meets local commits; already-local objects are skipped.
3. **Signature policy:** if the vault has `signatures-required`, every picked commit must verify (`Vault__Signatures.
   status_of(...) == VERIFIED`) under the same rule pull applies (`Vault__Incoming_Check`). Otherwise
   `Vault__Signature_Error` names the commit. See §6, threat T3.
4. **For each commit `P`, in order:**
   - refuse a merge commit;
   - `base_map` = `flatten(P.parent.tree)`, or `{}` for a root commit; `ours_map` = `flatten(HEAD.tree)`;
     `theirs_map` = `flatten(P.tree)`. Scoped clones use `Vault__Scoped_Tree.flatten` and carry `theirs_opaque`
     from HEAD, not from P (§7);
   - merger as §5.7 with the cherry-pick labels; `three_way_merge(base, ours, theirs, content_merger=…)`;
   - **empty** (merged blob map == ours' blob map): stop with status `empty` and exit 1, writing nothing;
   - guard: `_guard_working_tree`-equivalent dirty check (the working copy is clean, but the check also catches
     untracked files in the way: `Vault__Pull__Guard.blocked_targets`);
   - write the working copy (deletions first, then `merged_map` entries that differ from ours) with
     `_remove_deleted_flat` and `_checkout_flat_map`, as revert does (`Vault__Sync__History_Edit.py:95-96`);
   - **conflicts:** write the `.conflict` and marker files and the merge state, with:
     - `operation = cherry-pick`;
     - `ours_commit_id` = HEAD;
     - `theirs_commit_id = P`;
     - `lca_id` = P's parent;
     - `source_commit_id = P`;
     - `remaining_commit_ids` = the specs not yet applied;
     - `sequence_start_id` = HEAD before the first pick;
     - `record_origin`.

     Stop with status `conflicts`;
   - **clean:** build the tree (`build_from_flat`, with `opaque` on a scoped clone), then
     `create_commit(parent_ids=[HEAD], message=pick_message(P, record_origin), signing_key=…)` signed with the
     clone key exactly as commit does (`Vault__Sync__Commit._load_signing_key`), write the ref, and record the
     reflog entry `cherry-pick: <subject>`.
5. **Return** `{status, picked, commit_ids, remaining, stopped_at, files, conflicts}`.

**`pick_message(P, record_origin)`:** P's decrypted message (`crypto.decrypt_metadata(read_key, P.message_enc)`),
falling back to `Cherry-pick <12-hex>` when undecryptable. With `record_origin`, append
`\n\n(cherry picked from commit <full id>)`.

**`continue_(directory)`:**
- requires a state with `operation == cherry-pick`;
- runs the unresolved check of §5.8; unresolved paths → `Vault__Merge_Unresolved_Error`;
- commits the working copy as a **single-parent** commit with `pick_message(source, record_origin)`. To do that
  without duplicating code, it calls `Vault__Sync__Commit.commit(directory, message=…, no_merge_commit=True)`;
  `no_merge_commit` already exists (`Vault__Sync__Commit.py:33,153`). The new commit refuses when the working copy
  equals HEAD ("now empty": status `empty`);
- deletes the state;
- if `remaining_commit_ids` is not empty, calls `pick(directory, remaining, …)` with the same options.

**`abort(directory)`:** `Vault__Merge__Abort` with `ours_commit_id := sequence_start_id`. Earlier successful picks
in the same sequence are undone too, as `git cherry-pick --abort` does.

**Commit attribution:** the new commit is authored and signed by this clone, like every sgit commit. The original
author survives only in the `-x` trailer and in `history log` of the source commit. Git keeps `author` separate
from `committer`; sgit has no author field (D7).

### 5.10 CLI wiring

| File | Change |
|---|---|
| `sgit_ai/cli/CLI__Main.py:398-405` | `pull_parser.add_argument('--merge', choices=['files','lines'], default=None, dest='merge_style')`, `--conflict` (`choices=['merge','diff3']`, `dest='conflict_style'`); `cmd_pull` passes both |
| `sgit_ai/cli/CLI__Branch.py:52-57,192-210` | the same two options on `branch merge`; `cmd_branch_merge` → `merge_branch(directory, name, merge_style=…, conflict_style=…)`; output adds line-merged and kind columns |
| `sgit_ai/core/Vault__Sync.py:230-234` | `merge_branch(..., merge_style=None, conflict_style=None)`; new `cherry_pick(...)`, `cherry_pick_continue(...)`, `cherry_pick_abort(...)` delegating to `Vault__Cherry_Pick` |
| `sgit_ai/cli/CLI__Vault.py:963-1043` | `cmd_pull` passes the flags and prints `line_merged` and the kind column |
| `sgit_ai/cli/CLI__Vault.py:826+` | `cmd_status` prints the merge block of §3.4 from the existing status fields plus `merge_marker_paths` and `merge_operation` (two new keys in `Vault__Sync__Status.py:219-226`) |
| `sgit_ai/cli/CLI__Merge.py` | `resolve <file>` with no side → `mark_resolved`; `--force`; constructs `Vault__Merge__Resolve(crypto=…, api=…)`; prints the remaining-count lines moved out of the core class |
| `sgit_ai/plugins/history/CLI__History.py` (after `revert`, `:141-151`) | `cp_p = hist_sub.add_parser('cherry-pick', help='Apply the change a commit made as a new commit on this clone (git cherry-pick)')` with `commits` (`nargs='*'`), `directory` via `--directory` (positional `commits` is variadic, so the directory moves to an option, as `resolve` does), `-x`, `--merge`, `--conflict`, `--continue`, `--abort`, `--json`; `set_defaults(func=CLI__Cherry_Pick(...).cmd_cherry_pick)` |

### 5.11 Storage and format impact, compatibility

| Concern | Impact |
|---|---|
| Vault objects | None new. A clean line merge produces an ordinary blob and an ordinary two-parent merge commit; a pick produces an ordinary one-parent commit. |
| Branch index, features, `min_client` | Untouched. **No version gate**: a reader of any version sees regular commits. |
| Old clients (0.17–0.26) pulling a line-merged commit | Normal fast-forward or merge: they see a modified file. Nothing to parse. |
| Web UI | Sees normal commits and files. Its own merges keep whole-file `.conflict` semantics. A marker file is never pushed, because commit refuses it (§5.8). |
| Local files | `merge_state.json` and `config.json` gain optional fields; both directions load (§5.2). |
| Pack vaults, `blob-deflate`, pack indexes | New blobs go through `encrypt(deflate=True)` and `obj_store.store` like any commit's blobs, so push writes them into the commit pack and the commit index lists the changed path. Nothing specific. |
| Interop vectors | None needed: no crypto changes. The line-merge vectors (§9.2) are text-only. |

### 5.12 Settings summary

| Setting | Where | Values | Default |
|---|---|---|---|
| `--merge` | `pull`, `branch merge`, `history cherry-pick` | `files`, `lines` | from below |
| `--conflict` | the same | `merge`, `diff3` | from below |
| `SGIT_MERGE_STYLE` (D1) | environment | `files`, `lines` | unset |
| `merge_style` | `.sg_vault/local/config.json` | `files`, `lines` | unset = `files` |
| `conflict_style` | the same | `merge`, `diff3` | unset = `merge` |

Until a `config` command exists (roadmap open choice), the clone-level fields are written by
`Vault__Merge_Style_Resolver.set_default(directory, style, conflict_style)`, used by tests and by a later command.
Nothing in the CLI writes them in this round (decision D10).

---

## 6. Security and threat model

| # | Threat | Actor | Treatment | Test |
|---|---|---|---|---|
| T1 | **A marker file written outside the tree or into `.git/`, `.sg_vault/`** (paths come from decrypted vault data) | A5 (a vault member), A1 + A3 | `write_marker_files` and resolve's side writes use `Vault__Path_Guard.is_writable` + `safe_join`, like `.conflict` today (`Vault__Merge.py:97`); links are never followed (`read_regular`/`O_NOFOLLOW` reads; writes refuse a link component) | `tests/unit/appsec/test_AppSec__Path_Traversal__Write_Sites.py`: add the two new write sites (`write_marker_files`, `Vault__Merge__Resolve._resolve_ours/_theirs` on marker paths), with `../x`, `.git/hooks/pre-commit`, `.sg_vault/local/vault_key`, a path under an in-tree symlinked folder |
| T2 | **Label injection:** a branch name or commit subject containing `\n=======\n` or `>>>>>>> ` corrupts the marker structure, so a later "resolved" check is fooled or text is smuggled into a clean-looking region | A3 (any writer names branches and messages) | `Safe_Str__Conflict_Label` keeps printable ASCII only (`\n` and `\r` become `_`), max 80; markers are only ever written at line start by the assembler | `Test_Vault__Line_Merge.test_labels_are_sanitised` |
| T3 | **Cherry-pick launders authorship:** content from an unsigned or forged commit (another branch, or fetched by full id from the host) gets **this clone's** signature on the new commit, so `signatures-required` no longer flags it | A3 + A1 | Under `signatures-required`, every picked commit must verify before its content is used (§5.9 step 3), the same policy pull applies to incoming commits. Without the policy, behaviour equals Git (cherry-pick re-signs as committer). New row: **TM-R (next free id) "cherry-pick re-signs another commit's content; under the policy the picked commit must verify first"**. | `tests/security/test_Security__Fixed__Cherry_Pick_Policy.py` (unsigned pick refused under the policy; control: accepted without it) |
| T4 | **Markers committed and pushed by mistake** (the line-merge analogue of §4.5) | user, agent | The commit refuses complete marker blocks on unresolved marker paths (§5.8); `resolve --force` is the deliberate override. Whole-file `.conflict` files are never committed for conflict paths. New row: **TM-F (next free id) "`.conflict` files of an unresolved merge were committed and pushed to every teammate"** (pre-existing, found here; fixed under D3). | `tests/security/test_Security__Fixed__Conflict_Files_Not_Committed.py`; `Test_Commit__Marker_Guard` (§9) |
| T5 | **Uncommitted work destroyed by the marker write** | user | Marker paths are extra writes for the dirty-tree guard (§5.7 step 3); refusal before any write | `Test_Pull__Line_Merge.test_dirty_edit_on_a_marker_path_refuses_before_writing` |
| T6 | **Resource exhaustion** with a crafted pair of files (diff blow-up) | A3 | Caps: 8 MiB, 200,000 lines, edit cost 5,000; linear-space Myers; fallback to whole-file. (DoS is out of the security review's scope, but the caps keep a pull bounded.) | `test_too_different_falls_back`, `test_too_large_falls_back` |
| T7 | **The host substitutes a blob fetched for the merge** (sparse clone) | A1 | `_fetch_blobs_verified` writes only objects whose bytes hash to their id (`Vault__Verified_Write`), as sparse fetch does | `Test_Pull__Line_Merge__Sparse.test_substituted_blob_refused` |
| T8 | **Zero knowledge** | — | All merging is client-side on plaintext; the host sees one new blob (size, as for any commit: TM-R08) and nothing about the merge style. No new metadata. | — |

The threat-model rows are added to `team/explorer/appsec/threat-model/v0.21.0__threat-model.md` with the next
free `TM-R` and `TM-F` numbers at implementation time. Other design documents of this round may take numbers too.

---

## 7. Interactions

| Feature | Behaviour with `lines` |
|---|---|
| **Scoped clone** (`clone --path`) | The flat maps are scope-only (`flat_of`, `Step__Pull__Merge.py:44-52`), so conflicts and line merges happen only inside held folders; out-of-scope entries stay opaque by id. The blobs of held folders are local (scope fetch includes them). **Cherry-pick:** if `P` changes any path outside the scope (diff of `P.parent` → `P` touches an opaque folder id), refuse: `cherry-pick of <id> changes files outside this clone's folders (…); run it from a full clone or widen with sgit fetch <folder>`. This is the same shape as revert's scoped refusal (`Vault__Sync__History_Edit.py:63-65`), but narrower: allowed when P stays in scope. |
| **Shallow clone** | If the LCA lies beyond the boundary, `find_lca` returns `None`, so `base_map = {}` and every both-present differing path is add/add (base `b''`, G16), as today's classifier already does. Cherry-pick of a commit whose parent is beyond the boundary: refused (`Vault__Revision._parent` already names the shallow case, `Vault__Revision.py:158-161`). |
| **Sparse clone** (`--sparse`) | Blobs are not fetched by pull. The merger fetches the base, ours and theirs blobs of **only** the both-changed paths, verified (§5.7 step 2). Offline → `MISSING_BLOB` → whole-file fallback with the reason printed. |
| **Selective working copy** (`--no-checkout`, `checkout`) | Clean merged files follow `selective.split` like any change (written if checked out, else recorded for `checkout --since-pull`). Marker files are always written (a conflict must be visible) and recorded with `after_write`, as are `.conflict` files. `pull --no-checkout` with a conflict: conflicts need the working copy, so pull refuses before writing: `--no-checkout cannot leave conflicts; pull without it to resolve` (a new check after classification, before any write). |
| **Read-only clone** | No merge (read-only pull re-checks out). Cherry-pick refused by `_check_read_only`. |
| **Pack vault, `blob-deflate`, pack-store** | Reads through `obj_store.load` (packs read by offset, verified); new blobs as in §5.11. No special case. |
| **Rewind re-apply** | Uses the style; clean line merges accepted; conflicts refuse (§5.7 step 5). |
| **`history revert --as-commit`** | Uses the clone's style; conflicts refuse (§5.7 step 6). |
| **merge-abort** | Restores ours, including marker files (§5.8); for a pick, `sequence_start_id`. |
| **resolve** | §3.2 / §5.8. `resolve --show` keeps its 3-way verdict view and adds the kind. |
| **stash** | `vault stash` during a merge: today's behaviour is unchanged (stash is not merge-aware). `stash pop` is a file overwrite, not a merge, so it is not in scope. A line-merging `stash pop` is a candidate follow-up. |
| **status** | Prints the merge or pick block (§3.4). The `.conflict` files keep showing as untracked additions. |
| **`commit --amend`** | Refused during a merge or pick (`_amend_plan`, `Vault__Sync__Commit.py:212-213`); unchanged. |
| **branch switch** | Its pull uses the configured style. Conflicts behave as today (`_report_switch_pull`, `CLI__Branch.py:222-223`). |
| **Pull guard (`Vault__Pull__Guard`)** | Unchanged logic; it receives marker paths as writes. |
| **Two scoped agents** | Unchanged: they never conflict. |

---

## 8. Performance

**Where the cost goes.** The classifier (`three_way_merge`) is unchanged and O(paths). The line engine runs
**only** on paths both sides changed to different blobs. Measured workloads:

| Workload | Both-changed paths | Extra cost of `lines` |
|---|---|---|
| Newsroom pass pull (300 files on 228,000; agents in separate folders) | 0 | none: the merger is never called |
| 76,000-file vault, `push` / `pull` of both (release-readiness §3) | 0 | none |
| A typical team conflict: 1–20 text files of 100–5,000 lines | 1–20 | 3 decrypts + 2 diffs + 1 encrypt per file |

**Engine targets**, pure Python on the 4-core sandbox; benchmarks in `Test_Vault__Line_Merge__Perf`, marked slow
and excluded from `-n auto` unit runs by name filter only if needed:

| Input | Target |
|---|---|
| 5,000-line file, 50 scattered changes per side | < 50 ms per merge |
| 50,000-line file, 500 changes per side | < 2 s |
| 200,000 lines (cap), 2 changes per side | < 1 s (prefix/suffix trim dominates) |
| Edit cost reaching 5,000 | stops at the cap; < 3 s wall before fallback |
| Binary or over-cap detection | O(8,000 bytes) / O(1) via the entry's `size` before decrypting: an entry whose `size` field exceeds 8 MiB is `TOO_LARGE` without loading the blob |

**Memory:** linear-space Myers, O(N+M) ints, plus the three byte strings (≤ 3 × 8 MiB).

**Cherry-pick:** three flattens (base, ours, theirs). On a pack vault with indexes these come from the flat cache
or the index (`flat_of`). On the 76,000-file vault a flatten from cache is ≈0.5 s, so ≈1.5 s plus the
classification, before any line merge.

**No effect on `files` style:** byte-identical code path (`content_merger=None`).

---

## 9. Test plan

All tests are real objects: `Vault__API__In_Memory`, `Vault__Test_Env` two-clone snapshots
(`tests/_helpers/vault_test_env.py`, `setup_two_clones`). No mocks, no `__init__.py` in tests, names
`test_<Class>.py` / `Test_<Class>`.

### 9.1 Engine unit tests

**`tests/unit/core/text/test_Vault__Line_Splitter.py` → `Test_Vault__Line_Splitter`**
- `split(b'')` is `[]`; `split(b'a')` is `[b'a']`; `split(b'a\n')` is `[b'a\n']`;
- `split(b'a\r\nb')` is `[b'a\r\n', b'b']`; `split(b'\n\n')` is `[b'\n', b'\n']`;
- `is_binary`: a NUL at byte 0, at 7,999 and at 8,000 (not binary, Git's rule); UTF-16 text is binary;
- `eol_of`.

**`tests/unit/core/text/test_Vault__Line_Diff.py` → `Test_Vault__Line_Diff`**
- **Fixed cases:** empty/empty, insert-only, delete-only, replace, common prefix/suffix only, completely
  different;
- **Edit script:** applying the hunks to A reproduces B (for all fixed cases and 2,000 seeded random pairs);
- **Minimality:** on 500 random pairs of ≤ 40 lines over a 6-symbol alphabet, the edit cost equals an O(NM)
  dynamic-programming LCS reference implemented in the test class;
- **Cap:** a pair with edit cost 5,001 raises `Vault__Line_Diff__Too_Different`; 5,000 does not;
- **Determinism:** the same input gives the same hunks across runs;
- **Compaction:** `a,b,b,c` vs `a,b,b,b,c` places the insertion at the lowest position, matching
  `git diff --no-index` (checked against a fixture vector).

**`tests/unit/core/text/test_Vault__Line_Merge.py` → `Test_Vault__Line_Merge`**
- One test per G1–G17 (§1.2), asserting the exact bytes and hunk count;
- **Labels:** `test_labels_are_sanitised` (newline, `=======`, non-ASCII, 200-char subject);
- **Diff3:** `test_diff3_style_is_eager_not_zealous` (G9);
- **Equal sides:** `test_one_side_equal_to_base_returns_other_side_clean` and its mirror;
- **Shapes:** `test_both_sides_delete_same_lines_clean`, `test_delete_vs_edit_same_line_conflict`,
  `test_empty_files`, `test_only_eol_differs_conflicts` (CRLF vs LF, Git parity);
- **Fallbacks:** `test_too_large_falls_back` (8 MiB + 1 byte; 200,001 lines), `test_too_different_falls_back`,
  `test_binary_any_side`;
- **Determinism:** `test_result_is_deterministic`.

**`tests/unit/core/text/test_Vault__Line_Merge__Properties.py` → `Test_Vault__Line_Merge__Properties`**
(seeded random, 3,000 cases each)
- P1: `O == B` ⇒ clean and the result is `T`. P2: `T == B` ⇒ `O`. P3: `O == T` ⇒ clean and `O`;
- P4, symmetry: `merge(B,O,T)` and `merge(B,T,O)` have the same outcome and hunk count; the conflict sections are
  swapped;
- P5: `favor=ours` gives the same bytes as `git merge-file --ours` (when git is available), and the result never
  contains markers;
- P6: a clean result, diffed against B, contains every ours-only and theirs-only hunk;
- P7: a merge with markers, resolved by taking ours in every block, equals the `favor=ours` result.

### 9.2 Vectors, committed

`tests/_fixtures/line_merge_vectors.json` holds about 80 cases: G1–G18 plus generated ones (unique-line,
repeated-line, CRLF, no-final-newline, add/add, coalescing boundaries). Each has `base`, `ours`, `theirs`
(base64), `style`, the `expected` bytes and the `exit` code, all produced by `git merge-file -p [--diff3] -L ours -L
base -L theirs`. A generator class `Test__Generate_Line_Merge_Vectors` lives in the test tree and is excluded from
runs by default (`-k generate`).

`tests/unit/core/text/test_Vault__Line_Merge__Vectors.py` → `Test_Vault__Line_Merge__Vectors` asserts byte
equality and hunk count == exit for **every** vector, so CI does not need git for these.

### 9.3 Live Git oracle

`tests/unit/core/text/test_Vault__Line_Merge__Git_Oracle.py` → `Test_Vault__Line_Merge__Git_Oracle`. It runs
`git merge-file` through `subprocess` (`shutil.which('git')`, skipped when absent) on temp files in `tmp_path`:

| Corpus | Cases | Assertion |
|---|---|---|
| (a) unique lines: lines drawn without repetition, so the diff is unique | 1,500 per style (merge, diff3) | **byte-exact** equality and hunk count == exit |
| (b) repeated lines (alphabet of 4 lines) | 1,500 | the outcome (clean vs conflict) and the hunk count equal Git's; bytes are compared and any difference is **collected** and asserted to be ≤ 2% of cases. The collected differences print in the failure message for review. Placement of ambiguous hunks is the only allowed difference (§5.3 step 6). |
| (c) CRLF and no-final-newline variants of (a) | 500 | byte-exact |

If D9 asks for exact parity on (b), xdiff's compaction and split heuristics must be ported exactly (+1–2 days).

### 9.4 Classifier and integration tests

**`tests/unit/core/actions/merge/test_Vault__Merge__Content_Merger.py` → `Test_Vault__Merge__Content_Merger`**
(real `Vault__Object_Store` in `tmp_path`)
- **Clean:** a new blob is stored, the entry has the right `size`, `content_hash` and `content_type`, and the
  path is in `line_merged`;
- **Conflict:** `merged_map[path]` is ours' entry unchanged, the marker bytes are returned, and **no blob is
  stored**;
- **Fallbacks:** binary, too large via the entry `size` without decrypting, missing blob with a fetcher that
  fetches, missing blob with no fetcher;
- **Shapes:** modify/delete unchanged; add/add with base `b''`;
- **Regression:** `content_merger=None` gives byte-identical results to the current implementation on the
  existing `Test_Vault__Merge` cases.

**`tests/unit/workflow/pull/test_Pull__Line_Merge.py`** (two clones, `_TwoClones` pattern from
`test_Pull__Dirty_Working_Tree.py:24-56`):

`Test_Pull__Line_Merge__Default_Is_Files`:
- without a flag: `x.txt.conflict` is written, the file is ours, there are no markers, `merge_style` in the state
  is `files`;
- exactly today's result dict keys (plus the empty `line_merged`).

`Test_Pull__Line_Merge__Clean`:
- Alice and Bob change different lines of `notes.md`; `pull(merge_style='lines')` gives status `merged`;
- the file holds both changes; the head is a 2-parent commit;
- `push`, then a third clone's `pull` gets the merged bytes (the blob was uploaded);
- the old classifier's result for the other paths is unchanged.

`Test_Pull__Line_Merge__Conflict`:
- markers in the file; `marker_paths` recorded; the clone ref has not moved;
- `commit` refuses with `Vault__Merge_Unresolved_Error` naming the path;
- after a hand edit (markers removed), `commit` makes the 2-parent merge commit and the state is deleted;
- `resolve --ours` restores ours' bytes; `resolve --theirs` restores theirs';
- `resolve <file>` while markers remain refuses; `--force` accepts;
- `merge-abort` restores ours and deletes the state;
- `resolve --all --theirs`.

`Test_Pull__Line_Merge__Guard`:
- `test_dirty_edit_on_a_marker_path_refuses_before_writing`: nothing written, ref unchanged, edit intact;
- an untracked `x.txt.conflict` in the way refuses (whole-file style).

`Test_Pull__Line_Merge__Settings`:
- `local_config.merge_style = lines` with no flag → lines;
- `--merge files` overrides the config;
- `SGIT_MERGE_STYLE` (if D1), set through `monkeypatch.setenv` (an environment fixture, not a mock);
- `conflict_style = diff3` → `|||||||` present.

`Test_Pull__Line_Merge__Fallbacks`: binary → `.conflict`, reason printed; over the cap → `.conflict`; a mix of a
markers path and a whole-file path in one pull.

`Test_Pull__Line_Merge__Partial_Clones`:
- a scoped clone merges inside its folder;
- a shallow clone with the LCA beyond the boundary (add/add semantics);
- a sparse clone fetches exactly 3 blobs per conflict path (counted with the in-memory API's request log);
- `test_substituted_blob_refused` (T7: the in-memory store is altered to serve wrong bytes);
- a selective working copy: a clean merge not checked out is recorded for `checkout --since-pull`;
- `pull --no-checkout` with a conflict refuses.

`Test_Pull__Line_Merge__Pack_Vault`: `init --packs` (`blob-deflate`) and a `clone --pack-store` second clone →
clean merge, push, fresh clone reads it, `pack index verify` ok.

`Test_Pull__Line_Merge__Rewind`: an accepted rewind with a clean line merge re-applies; a conflicting one still
refuses with nothing written.

`Test_Branch_Merge__Line_Style`: `branch merge feature --merge lines` clean and conflict.

**`tests/unit/core/actions/history/test_Vault__Sync__History_Edit__Line_Revert.py` →
`Test_History_Revert__Line_Style`:** a revert whose target file changed later on other lines succeeds with
`lines` and refuses with `files`.

**`tests/unit/core/actions/commit/test_Vault__Sync__Commit__Merge_Guard.py` → `Test_Commit__Marker_Guard`:**
- complete marker blocks refuse; a lone `=======` (rst) does not;
- markers in a non-conflict path do not refuse (it is content);
- CRLF markers are detected;
- with `.conflict` files present the commit refuses (D3) and never includes a `*.conflict` file of a conflict
  path.

**`tests/unit/core/actions/history/test_Vault__Cherry_Pick.py` → `Test_Vault__Cherry_Pick`:**
- **Clean picks:** a clean pick has one parent, the same message, changed files; `-x` adds the trailer; a pick of
  a root commit works;
- **Refusals:** a merge commit, a dirty working copy, a pick or merge in progress, a read-only clone; an empty
  pick → `empty` with nothing written;
- **Conflicts:** files style → `.conflict`; lines style → markers; `--continue` after a hand edit makes a
  single-parent commit with the picked message; `--continue` with markers left refuses; `--abort` restores the
  start;
- **Sequences:** three commits with a conflict on the second → stops with `remaining=[third]`; `--continue`
  applies the third; `--abort` after two picks returns to the head before the first;
- **Sources:** a full id of a commit only on the server (another named branch pushed by Bob) is fetched and
  picked; tags and `HEAD~2` work as specs;
- **Scoped clone:** a pick inside the scope works; a pick touching outside refuses;
- **Signed:** the new commit verifies under the clone key (`check verify`).

**`tests/unit/cli/test_CLI__Merge_Style.py` → `Test_CLI__Merge_Style`:**
- argparse `--merge` and `--conflict` choices on `pull`, `branch merge`, `history cherry-pick`; an invalid value
  exits 2;
- pull output, clean and conflicts (the exact lines of §3.1), captured with `capsys`;
- `status` prints the merge block and the pick block (§3.4);
- `cherry-pick --json` shape; exit codes 0, 1 and 2.

**`tests/unit/cli/test_CLI__B07__Namespace_Moves.py`:** `TOP_LEVEL_COMMANDS` unchanged (assert still passes).
Add `cherry-pick` to any history-subcommand list there is.

### 9.5 Security tests

| Location | What it checks |
|---|---|
| `tests/security/test_Security__Fixed__Conflict_Files_Not_Committed.py` | Reproduces §4.5 (it fails on today's code) and passes after D3 |
| `tests/security/test_Security__Fixed__Cherry_Pick_Policy.py` | T3, with a control |
| `tests/unit/appsec/test_AppSec__Path_Traversal__Write_Sites.py` | T1: the new write sites |
| `test_Vault__Line_Merge.test_labels_are_sanitised` | T2 |

### 9.6 Acceptance checklist (implementation and deployment)

Tick each item in the PR description.

**Implementation**
- [ ] `pytest tests/unit/ -n auto` passes; `pytest tests/security` passes; `pytest tests/unit/core/text -q` runs in
      < 60 s.
- [ ] Every vector in `tests/_fixtures/line_merge_vectors.json` matches byte for byte.
- [ ] Oracle corpus (a) and (c) byte-exact; (b) outcome-equal, byte difference ≤ 2% (or 0% if D9 asks).
- [ ] With no flag, no env and no config, the files style is unchanged: all pre-existing merge, pull and resolve
      tests pass unmodified, except those encoding the §4.5 defect, which are updated and named in the commit.
- [ ] `--merge lines` clean merge: the merged file has both changes; push; a fresh clone reads them; a 0.26.0
      client (`pip install sgit-ai==0.26.0` in a venv) pulls the merge commit without error.
- [ ] Markers are never committed: commit refuses; `resolve --force` is the only way.
- [ ] `.conflict` files are never committed (security test).
- [ ] Dirty edit on a marker path: pull refuses, nothing written.
- [ ] Cherry-pick: clean, conflict + `--continue`, `--abort`, sequence, `-x`, policy refusal.
- [ ] Threat-model rows added (T3, T4); CHANGELOG `[Unreleased]` entries; README section "Merging line by line
      (opt-in)" and "Cherry-pick".
- [ ] `sgit help all` and `sgit history --help` list `cherry-pick`.

**Deployment** (on the dev pre-release, two real clones of a dev-server vault)
- [ ] `pip install --pre sgit-ai`; `sgit version` shows the `.dev0` build.
- [ ] Clone A and clone B; both edit different paragraphs of `notes.md`; A pushes; B runs
      `sgit pull --merge lines`. Expect `Line-merged 1 file(s)`, `sgit push` ok, the web UI shows both
      paragraphs, `sgit check verify` all verified.
- [ ] Both edit the same line → markers; `sgit status` shows the merge block; `sgit commit` refuses; edit,
      `sgit commit`, `sgit push`; the web UI shows the resolved text and no marker anywhere in the vault
      (`sgit history show HEAD`).
- [ ] The same with the default (no flag) → `.conflict` exactly as on 0.26.0.
- [ ] `sgit history cherry-pick <id from history log>` on a third clone → one-parent commit, pushes, verifies.
- [ ] On a pack vault (`sgit create --packs`), repeat the clean case; `sgit pack index verify --last 1` ok.
- [ ] Time a pull on the 76,000-file benchmark vault with `--merge lines` and no both-changed paths: equal to
      `--merge files` within noise.

---

## 10. Implementation steps (ordered commits)

| # | Commit | Contents | Estimate |
|---|---|---|---|
| 1 | `feat(text): line splitter and Myers line diff` | `sgit_ai/core/text/` package, `Vault__Line_Splitter`, `Vault__Line_Diff`, `Schema__Line_Hunk`, `Safe_UInt__Line_Number`, `Vault__Line_Diff__Too_Different`; tests 9.1 (splitter, diff) | 0.5 day |
| 2 | `feat(text): three-way line merge matching git merge-file` | `Vault__Line_Merge`, the merge enums, `Safe_Str__Conflict_Label`, `Schema__Conflict_Labels`, `Schema__Line_Merge_Result`; the vector generator + `line_merge_vectors.json`; tests 9.1 (merge, properties), 9.2, 9.3 | 1 day |
| 3 | `feat(merge): content merger behind the blob-id classifier` | `Vault__Content_Merger`, the `three_way_merge(content_merger=…)` extension, `write_marker_files`, the `_fetch_blobs_verified` extraction (sparse fetch now calls it); `Schema__Merge_State` and `Schema__Local_Config` fields; `Vault__Merge_Style_Resolver`; tests 9.4 (content merger) | 0.5 day |
| 4 | `feat(pull): --merge lines / --conflict on pull and branch merge` | the `Step__Pull__Merge` wiring (guard extra writes, `.conflict` target check, markers, selective, the `--no-checkout` refusal), rewind, revert, `Schema__Pull__State` fields, `_pull_state_to_dict`, CLI flags and output; tests 9.4 pull/branch/revert/rewind | 0.75 day |
| 5 | `fix(merge): commit refuses unresolved conflicts; .conflict files never committed; resolve marks, restores; status shows the merge` | §5.8 commit rules, `Vault__Merge_Unresolved_Error`, `Vault__Merge__Resolve` (crypto, `mark_resolved`, marker sides), the `resolve` CLI, the `cmd_status` merge block; tests `Test_Commit__Marker_Guard`, security test T4 | 0.5 day |
| 6 | `feat(history): cherry-pick` | `Vault__Cherry_Pick`, `CLI__Cherry_Pick`, the history plugin registration, `Vault__Sync` delegates, the policy check; tests `Test_Vault__Cherry_Pick`, security test T3, CLI tests | 1 day |
| 7 | `docs: line merge and cherry-pick` | CHANGELOG, README, threat-model rows, a response note under `team/humans/dinis_cruz/claude-code-web/<date>/`; full suite; the deployment checklist on dev with timings | 0.25 day |

**Total: about 4.5 days.** That is 2.1 ≈ 3.25 days (steps 1–5, 7) and 2.8 ≈ 1.25 days (step 6). The roadmap's
"2–3 days + 1 day" did not include the commit-guard fix, the status block or the oracle corpus.

---

## 11. Open decisions for Dinis

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | A per-session default for agents | (a) flag + clone config only; (b) also `SGIT_MERGE_STYLE` in the environment | **(b)**: agents set environment variables per session; it is read-only, below the flag, above the config |
| D2 | Default conflict style in `lines` mode | `merge` (Git's default) / `diff3` | **`merge`**; `diff3` via `--conflict diff3` or config |
| D3 | Commit while conflicts are unresolved (both styles) | (a) keep today: commit anyway (commits `*.conflict` files); (b) refuse, as Git does ("Committing is not possible because you have unmerged files") | **(b)**. Today's behaviour pushes `.conflict` files to everyone (§4.5). It is a behaviour change for the `files` style, listed in the CHANGELOG as a fix. |
| D4 | How a hand-edited marker file counts as resolved | (a) automatically, when no complete marker block remains; (b) only by `sgit resolve <file>` (Git's `git add`) | **(a) and (b)**: (a) keeps the agent loop "edit, commit"; (b) is there for files that legitimately contain marker-like lines (`--force`) |
| D5 | Cherry-pick v1 scope | (a) one commit; (b) several listed commits with `--continue` resuming the rest | **(b)**, ranges (`A..B`) later; +0.25 day |
| D6 | Exit code on conflicts | pull/branch merge: keep 0 (today) or 1 (Git); cherry-pick: 1 (Git) | **Pull unchanged (0)**: scripts and agents rely on it; a `--strict-exit` later if asked. **Cherry-pick 1**: a new command, Git parity. |
| D7 | Cherry-pick provenance | (a) Git default: no trailer unless `-x`; (b) always add the trailer | **(a)**: Git parity; sgit has no author field, so `-x` is the way to keep the origin |
| D8 | Engine caps and the too-different fallback | 8 MiB / 200,000 lines / edit cost 5,000, then whole-file; or xdiff's heuristic split (never gives up) | **Caps + whole-file fallback**: predictable, and the reason is printed |
| D9 | Exactness against Git | byte-exact on unique-line inputs and outcome-exact elsewhere; or port xdiff's split and compaction heuristics for full byte parity | **The first**; revisit if a user reports a difference (+1–2 days to port) |
| D10 | Writing the per-clone default | (a) no CLI this round (tests and `set_default` only); (b) add `sgit vault config merge.style lines` now (Rule 9: under `vault`) | **(a)** now, matching the roadmap's "flag and config field first"; (b) with the next settings need |
| D11 | Marker labels | the table in §5.4; or Git's literal `HEAD` / branch name | **§5.4**: `ours`/`theirs` match `sgit resolve --ours/--theirs` |
