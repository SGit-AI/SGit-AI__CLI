# Design 04: rename detection, `history blame`, `grep` and pickaxe (roadmap 2.4, 2.5, 2.7)

> Read with [`design__00__index-and-reconciliation.md`](design__00__index-and-reconciliation.md): where the two disagree (shared foundations F1–F9, the in-progress rules), the index wins.

**Status:** design, not built. **Date:** 28 Oct 2026. **Roadmap:** `roadmap__git-parity.md` items 2.4, 2.5, 2.7
(priority 2). **Depends on:** nothing. **Feeds:** design 01 (line-level merge and cherry-pick) consumes the
rename-pairing API in section 5.2 and, if it does not define its own, the line differ in section 5.1.
**Checked against:** the code at `3a1d72a` and Git 2.43.0 (installed here; every Git behaviour marked "confirmed"
was run in a scratch repository on 28 Oct).

---

## 1. Summary and the exact Git behaviour matched

Three read-only features, all on plaintext the client already holds, none needing a server change or a format gate:

| Feature | Git behaviour matched | sgit today |
|---|---|---|
| **Rename detection** | `git diff`/`show`/`log --stat` find renames by default since Git 2.9 (`diff.renames=true`). Three passes in `diffcore-rename.c`: (1) exact (same blob), (2) same basename, unique on both sides, at a raised threshold, (3) an inexact similarity matrix, skipped when sources × destinations exceeds `diff.renameLimit`². Threshold `-M50%` by default. Output `R<score>` (`R095 b c`). `log --follow` follows one file across renames. | Exact renames only, and only in `history log --stat` (`Vault__Inspector._file_stat_from_diff`, `sgit_ai/objects/Vault__Inspector.py:252`), by the plaintext `content_hash`. `history diff`, `history show`, `--files`, `--patch`, `--json` and `--file` know no renames. |
| **`blame`** | `git blame [<rev>] [-L …] [-w] [--porcelain \| --line-porcelain] [--first-parent] -- <file>`: each line of the file at `<rev>` attributed to the commit that last changed it, following renames, through merges, boundary commits marked `^`. | Nothing. |
| **`grep`** | `git grep [-i -w -v -n -c -l -L -F -E -e … -o -q -A/-B/-C] <pattern> [<tree>…] [-- <pathspec>…]`: the tracked working-tree files by default, a tree when given (`HEAD~1:path:line:text`), exit 0 on a match and 1 on none. | Nothing (only `history log --grep` on messages). |
| **Pickaxe** | `git log -S <string>`: commits where the number of occurrences of the string in a file changed. `git log -G <regex>`: commits whose patch adds or removes a line matching the regex. Merge commits are not searched unless `-m`. | Nothing. |

Git behaviours confirmed in Git 2.43 for this document:

| Behaviour | Result |
|---|---|
| Rename threshold 50% | A 100-line file renamed and cut to 49 lines shows `D a` + `A b`; 49 → 51 lines shows `R095 b c`. |
| `diff.renameLimit` default 1000 | 1,001 deleted × 1,001 added files with **different basenames**, each edited: `warning: exhaustive rename detection was skipped due to too many files`, all `A`/`D`. With `-c diff.renameLimit=1001`: all `R`. |
| Basename pass bypasses the limit | The same 1,001 files moved to another folder **with the same basenames**, each edited: all `R`, no warning. |
| Exact pass bypasses the limit | 1,001 files moved unchanged: all `R100`. |
| A lone empty file moved | `R100 e1 e2`. |
| `-S` vs `-G` | `-S five` lists the commits that changed the count of `five` in a file; `-G five` the commits whose added or removed lines contain `five`. A moved line matches `-G`, not `-S`. |
| `grep` exit code | 1 when nothing matches. |
| `grep` on a tree | `git grep -n five HEAD~1` prints `HEAD~1:c.txt:5:five`. |
| `blame` default line | `^5349944 a.txt (A 2026-10-28 02:56:20 +0000  4) 4`: `^` for a boundary commit; the path column appears when any line's origin path differs from the final path. |
| `blame --porcelain` | `<sha> <orig line> <final line> <group size>`, then on a commit's first appearance `author`, `author-mail`, `author-time`, `author-tz`, `committer…`, `summary`, `previous <sha> <path>`, `filename <path>`, then the line after a TAB. |
| `blame -L 3,+2` and `-L /five/,+1` | Ranges as documented. |

Not confirmed here (no man pages in this container): `merge.renameLimit` default 7000. Design 01 should confirm it if
it adopts that value.

## 2. Scope and non-goals

**In scope**
- **Rename detection:** exact, basename and similarity passes, with `-M[<n>]`, `--no-renames` and the 1,000 limit.
- **Where renames show:** `history diff` (all modes), `history show`, `history log --stat / --files / --patch / --json`
  and the new `history log --file <path> --follow`.
- **For the merge:** the pairing API that design 01 calls.
- **`sgit history blame`:**
  - `<rev>`, `-L` (numeric, `+N`, `-N`, `/regex/`, repeatable)
  - `-w`, `--first-parent`
  - output: `--porcelain`, `--line-porcelain`, `--json`, `-s`, `-e` (show key id), `--abbrev N`
- **`sgit grep`** (and `sgit file grep`):
  - match flags: `-i -w -v -F -E -P -e`
  - output flags: `-n -c -l -L -o -q -h -H -A/-B/-C`, `--json`
  - what is searched: working copy, `<rev>`, `--untracked`, pathspecs
- **Pickaxe:** `history log -S <string>`, `--pickaxe-regex`, `-G <regex>`, combinable with `--grep`, `--since`,
  `--until`, `--author` and `--file`.
- **A prerequisite refactor:** `Vault__Diff` stops decrypting every file of both commits (section 4.3).

**Not in scope**
- **Copy detection** (`-C`, `--find-copies-harder`): a follow-up if asked.
- **More blame options:**
  - `--ignore-rev` / `--ignore-revs-file`: optional, a follow-up; section 11, D12.
  - `-M`/`-C` inside blame (moved or copied lines within or between files).
  - `-L :funcname`, `--incremental`, `--reverse`, `--since`.
- **More grep options:**
  - `--and` / `--or` / `--not` / `(…)` boolean expressions. Several `-e` patterns OR together, as in Git.
  - `--recurse-submodules`, `-p` / `--show-function`, `--threads`.
  - POSIX BRE (Git's default dialect); see D2.
- **Elsewhere:**
  - renames in `status` (Git shows them only for staged changes; sgit has no staging area); D10.
  - any server-side search: impossible under zero knowledge, by design.
  - reading without a clone (`--vault-key` on a bare checkout is supported, as `history log` supports it; a no-clone
    network read is roadmap item "cat --vault-key").

## 3. CLI surface

Rule 9 (`tests/unit/cli/test_CLI__B07__Namespace_Moves.py:104`): blame and pickaxe are about commits, so they go
under `history`. `grep` is a daily verb over files. It goes in the `file` namespace beside `cat`/`ls`/`write`, and also
at the top level as `sgit grep`, the same way `cat`, `ls` and `write` are both (`sgit_ai/cli/CLI__Main.py:472-495`,
`sgit_ai/plugins/file/CLI__File.py`). That adds `'grep'` to `TOP_LEVEL_COMMANDS`, as a deliberate edit (D1).

### 3.1 Rename options (on `history diff`, `history show`, `history log`)

| Option | Meaning | Default |
|---|---|---|
| `-M[<n>]`, `--find-renames[=<n>]` | Rename threshold, percent (`-M90`, `-M90%`, or `-M0.9` as in Git) | 50 |
| `--no-renames` | Exact pairing off too; adds and deletes as today | off (renames are on) |
| `-l <num>` / `--rename-limit <num>` | Sources × destinations above `<num>²` skips the inexact pass (exact and basename passes still run) | 1000 |
| `--follow` (with `history log --file`) | Continue across renames | off |

Human output:
- `history log --stat` keeps `R  old -> new` and adds the score when below 100: `R  old -> new (95%)`.
- `history diff` / `history show` print a git-style rename header before the hunk:

  ```
  diff --git a/docs/old.md b/docs/new.md
  similarity index 95%
  rename from docs/old.md
  rename to docs/new.md
  --- a/docs/old.md
  +++ b/docs/new.md
  @@ …
  ```

  With `--files-only`: `R095  docs/old.md -> docs/new.md`.
- When the limit was hit, stderr says, once, in Git's words:
  `warning: exact rename detection only: 1001 × 1001 files is over the rename limit (1000); pass --rename-limit 1001 to try them all`.

JSON (additive, existing fields keep their meaning; see D4):

| Schema (file) | Field added | Shape |
|---|---|---|
| `Schema__History_Log_Commit_Entry` (`history_log_v1`) | `files_renamed` | `[{old_path, new_path, score, exact}]`; a renamed file is no longer listed in `files_added` / `files_deleted` |
| `Schema__History_Diff_Result` (`history_diff_v1`) | `files_renamed` | `[{old_path, new_path, score, exact, lines_added, lines_removed}]` |
| `Schema__Diff_File` | `old_path`, `similarity` | `status='renamed'`; `similarity` 0–100 |

### 3.2 `sgit history blame`

```
sgit history blame [<rev>] [-L <range>]... [-w] [--first-parent] [-s] [-e] [--abbrev N]
                   [--porcelain | --line-porcelain | --json] [--text] [--offline]
                   [--vault-key KEY] [-d DIR] [--] <path>
```

**`<range>` forms** (as Git, confirmed): `N,M`, `N,+K`, `N,-K`, `N` (to the end), `,M`, `/regex/` (the first
matching line, to the end), `/regex/,+K`. Several `-L` options are merged and sorted.

**Default output, one line per line of the file:**

```
^3f9a2c1d0b7e docs/a.md (alice    2026-10-27 14:30:02 +0000  4) text
57567877efb2 docs/c.md (bob-agent 2026-10-28 02:56:21 +0000  5) five
```

| Column | Rule |
|---|---|
| Commit | The hex part of the id, `--abbrev` characters (default 12, the full format-1 width). `^` prefix for a boundary commit (the root, or a shallow boundary). |
| Path | Shown when any line's origin path differs from the final path, as in Git. |
| Author | The branch name from the branch index; else the first 12 characters of `author_key_id`; `-e` shows the key id always (D8). |
| Date | The commit's `timestamp_ms` in UTC, `+0000`. sgit records no time zone. |
| Line | The final line number, right-aligned to the width of the largest. |
| `-s` | Drops author and date. |

**`--porcelain` and `--line-porcelain`:** Git's exact layout, so tools that parse Git's output work unchanged.

```
<40-or-64-char id field> <orig line> <final line> [<group size>]
author <branch name or key id>
author-mail <key id or "unsigned">
author-time <seconds>
author-tz +0000
committer <same as author>
committer-mail <same>
committer-time <same>
committer-tz +0000
summary <first line of the message>
boundary                       (only for a boundary commit)
previous <parent id> <path>    (when the commit has a parent holding the file)
filename <origin path>
\t<line>
```

The id field is the full `obj-cas-imm-<hex>` id, never padded to 40.

**`--json` (`history_blame_v1`):**

```json
{"schema": "history_blame_v1", "path": "docs/c.md", "rev": "<commit id>", "boundary_reason": "",
 "commits": {"<id>": {"timestamp_ms": 0, "author": "bob-agent", "author_key_id": "…", "summary": "…",
                      "boundary": false, "previous_id": "…", "previous_path": "…"}},
 "lines": [{"final_line": 5, "orig_line": 5, "commit_id": "<id>", "orig_path": "docs/a.md", "text": "five"}],
 "stats": {"commits_visited": 0, "blobs_read": 0, "blobs_fetched": 0, "index_plan_used": true}}
```

`boundary_reason`:
- `''` when the root was reached;
- `'shallow'` when a shallow boundary was reached;
- `'offline'` when an object was missing and could not be fetched.

**Exit codes:**

| Code | When |
|---|---|
| 0 | Success |
| 1 | The path is not a file at `<rev>`; or the file is binary without `--text`; or an `-L` range is out of bounds or matches nothing (Git's message: `fatal: file has only N lines`); or the path is outside a scoped clone; or the regex guard refused the pattern |

**Notes, written to stderr after the output:**
- Shallow: `… blame stops at the shallow boundary (lines marked ^ may be older). Deepen with: sgit fetch --unshallow`
- Offline: `… N object(s) were not local and could not be fetched: lines marked ^ stop there`

### 3.3 `sgit grep` (also `sgit file grep`)

```
sgit grep [-i] [-w] [-v] [-F | -E | -P] [-n] [-c] [-l | -L] [-o] [-q] [-h | -H]
          [-A N] [-B N] [-C N] [-m N] [--untracked] [--text | -I] [--json] [--offline]
          [--vault-key KEY] [-d DIR]
          (<pattern> | -e <pattern>...) [<rev>...] [-- <pathspec>...]
```

**Pattern and dialect**
- The pattern is a Python regular expression (D2): `-E` (ERE) and `-P` (PCRE) are accepted and mean the same thing.
- `-F` takes the pattern literally.
- Several `-e` options are ORed.
- `-i`, `-w` and `-v` as in Git.

**What is searched**
- With no `<rev>`: the working copy's files, filtered by the ignore rules `status` uses, plus `--untracked`
  untracked files. The bytes on disk are searched, never followed through a symlink.
- With `<rev>` (any revision `Vault__Revision` resolves: `HEAD`, `HEAD~2`, a tag, a short id): that commit's
  tree, decrypted in memory.

**Output**
- One line per match, as Git prints it:
  - working copy: `path:line:text`
  - a revision: `<rev as typed>:path:line:text`
- `-n` adds line numbers.
- `-c` prints `path:count`; `-l` the matching files; `-L` the files without a match; `-o` only the matched parts;
  `-A/-B/-C` context with `-`/`--` separators as in Git; `-m N` stops after N matches per file.
- `-h`/`-H` hide or show the file name.
- A binary file (a NUL in its first 8,000 bytes, Git's rule; sgit's `BINARY_CHECK_BYTES` is 8,192 and is reused)
  prints `Binary file <path> matches`. `-I` skips binary files; `--text` searches them as text.

**Pathspecs:** after `--`, Git's basic form: a literal prefix (`docs/`, `docs/a.md`) or a glob with `*`, `?` and `[…]`
(fnmatch on the full path, `**` matching folders). Magic forms (`:(exclude)`, `:!`) are not supported and are
refused by name.

**`--json` (`grep_v1`):**

```json
{"schema": "grep_v1", "rev": "", "pattern": ["five"],
 "matches": [{"rev": "", "path": "c.txt", "line": 5, "text": "five", "spans": [[0, 4]]}],
 "files_searched": 0, "binary_matches": ["img.png"],
 "skipped": {"not_checked_out": 0, "not_local": 0, "outside_scope": 0}}
```

**Exit codes** (D3):

| Code | When |
|---|---|
| 0 | At least one match (with `-L`: at least one file printed; with `-q`: a match, and nothing printed) |
| 1 | No match |
| 2 | Error: bad pattern, guard refusal, unknown revision, pathspec magic, outside scope |

### 3.4 Pickaxe, on `sgit history log`

| Option | Meaning |
|---|---|
| `-S <string>` | Commits where the count of `<string>` changed in some file (against the commit's only parent) |
| `--pickaxe-regex` | `-S` takes a regex instead of a literal |
| `-G <regex>` | Commits whose diff adds or removes a line matching `<regex>` |
| `--pickaxe-all` | With `--stat`/`--files`, list every changed file of a matching commit, not only the matching ones (Git's flag) |
| `-i` / `--regexp-ignore-case` | Case-insensitive `-S`/`-G` (Git's flag) |

- **Combining:** pickaxe works with `--grep`, `--since`, `--until`, `--author` (all must hold), `-n`, `--oneline`,
  `--stat`, `--json` and `--file <path>` (only that file is searched). That lifts today's refusal
  (`CLI__History._dispatch_log`, `sgit_ai/plugins/history/CLI__History.py:30`) for these combinations only; a
  range with `--grep` stays refused.
- **Merges:** skipped as in Git without `-m`. The output ends with a note when any were skipped and the history
  had merges: `(N merge commit(s) not searched, as in git log without -m)`.

## 4. How the code works today

### 4.1 Objects and what can be compared without decrypting

| Fact | Where | Consequence |
|---|---|---|
| A blob is `encrypt(read_key, plaintext)` with a **random IV** | `Vault__Crypto.encrypt`, `sgit_ai/crypto/Vault__Crypto.py:300`; deterministic encryption is for trees and tree-entry metadata only (`:263`) | The same content written twice gets two blob ids. Blob-id equality means the same content; inequality says nothing. |
| A commit reuses the old blob id when a path's content is unchanged | `Vault__Sub_Tree.encrypt_or_reuse_blob`, `sgit_ai/storage/Vault__Sub_Tree.py:517` (compares the old entry's `content_hash` at the **same path**) | A renamed file always gets a new blob id: renames cannot be found by blob id. |
| Tree entries carry `content_hash_enc`, `size_enc`, `content_type_enc` | `Schema__Object_Tree_Entry`, `sgit_ai/schemas/Schema__Object_Tree_Entry.py` | `content_hash` = the first 12 hex of sha256(plaintext) (`Vault__Crypto.content_hash`, `:335`), 48 bits. It is the **committer's claim**: nothing re-hashes it on read. |
| Flat maps: `{path: {blob_id, size, content_hash, content_type, large}}` | `Vault__Sub_Tree.flatten` (`:133`), process cache `FLAT_CACHE` and disk cache `.sg_vault/local/flat-cache/<tree id>.json` (0600, newest few kept, `:413`) | Exact renames can be found from two flat maps or a pruned diff with no blob read. The disk cache holds paths, sizes and content hashes in clear: TM-R41, accepted. **No file content is ever cached on disk.** |
| Pruned tree diff | `Vault__Sub_Tree.diff_trees` (`:259`): opens only folders whose ids differ, returns `added`, `deleted`, `modified` entries | The cost follows the change. It is the base for every per-commit diff here. |
| Path lookup | `Vault__Sub_Tree.resolve_path_target` (`:437`) loads trees through `Type_Safe` (`_load_tree`, ~3 ms a tree) | Too slow to call per commit. Section 5.4 uses `_load_tree_entries` (plain JSON, `:326`). |

### 4.2 Exact renames today

`Vault__Inspector._file_stat_from_diff` (`sgit_ai/objects/Vault__Inspector.py:252-276`) pairs each added path with the
first unused deleted path of the same `content_hash` (falling back to `blob_id`). Ties go in sorted path order, not
Git's basename preference. It is used only by `history log --stat` through `inspect_commit_chain` (`:97`), whose
per-commit diff comes from three sources, in order:
1. the pack index's `changes` member (`_diff_from_provider`, `:217`);
2. two cached flat maps (`_diff_from_flats`, `:187`);
3. `diff_trees`.

A `D` record from the index carries the old `content_hash` (`Vault__Pack_Index.changes_of`,
`sgit_ai/core/actions/pack/Vault__Pack_Index.py:201`), so exact pairing works on the index path too.

### 4.3 `history diff` / `show` / `log --files/--patch/--json` decrypt everything

`Vault__Diff` (`sgit_ai/core/actions/diff/Vault__Diff.py`):

| Method | What it does |
|---|---|
| `diff_commits` (`:66`) | Reads both commits' files through `_read_commit_files` → `_flatten_commit` (`:636`), which **loads and decrypts every blob of the tree** |
| `show_commit` (`:78`) | The same for the commit and its parent |
| `log_range_with_details` (`:290`) | Calls `show_commit` per commit, so `history log --patch` decrypts the whole vault twice per commit |
| `diff_files` (`:453`) | Then compares `{path: bytes}` maps by sha256 of the bytes and runs `difflib.unified_diff` (`:540`) |

On the 228,000-file vault that is about 1.2 GB decrypted per side, per commit. `diff_vs_head` / `diff_vs_remote` /
`diff_vs_commit` (`:35-58`) also read every working-copy file and every committed blob.

`log_file` (`:125`) walks the first-parent chain and, **for each commit and its parent, calls `flatten` on the whole
tree** to read one path's blob id. It compares blob ids only, so a writer that re-encrypts unchanged content (the web
UI) shows as `modified`.

On-demand fetch: `CLI__Diff._try_fetch_commits` (`sgit_ai/cli/CLI__Diff.py:35`) → `Vault__Diff.ensure_commit_local`
(`:736`) → `Vault__Sync__Pull._fetch_missing_objects(..., include_blobs=True)`. It is gated on a configured remote
(`_on_demand_api`, `:15`: a never-pushed vault never reaches the default host). One blob is fetched in
`Vault__Sync__Sparse.sparse_cat` (`sgit_ai/core/actions/sparse/Vault__Sync__Sparse.py:177`): `api.read` or
`read_large`, then `_save_verified`.

### 4.4 `history log` dispatch and filters

- **Parser:** `CLI__History.register` (`sgit_ai/plugins/history/CLI__History.py:73`).
- **Dispatch** (`:18`):
  - a range, `--files`, `--patch` or `--json` → `CLI__Diff.cmd_log_range`;
  - `--file` → `CLI__Diff.cmd_log_file`;
  - else → `CLI__Vault.cmd_log` → `_print_log` (`sgit_ai/cli/CLI__Vault.py:2274`).
- **Filters:** `--grep/--since/--until/--author` are filtered in `Vault__Log_Filter`
  (`sgit_ai/core/actions/history/Vault__Log_Filter.py`). They walk the whole DAG (`inspect_commit_dag`), or the
  first-parent chain with `--stat`.
- **Regex guard:** `Vault__Log_Filter.nested_repeat` (`:50`) refuses nested repetitions (`(a+)+`), read from the
  parsed pattern.

### 4.5 Pack indexes (Phase 1 reader)

| Member | Written | Read today |
|---|---|---|
| `changes` (commit index): `[{path, op A/M/D, old_blob, new_blob, size, content_hash, content_type, large}]` against the first parent | `build_commit_members` (`Vault__Pack_Index.py:272`) | `changes_of_commit` (`Vault__Pack_Index__Reader.py:245`) for `history log` counts and stat, and pull plans |
| `file-commits:<xx>` (snapshot index): `{path: [commit ids that changed it, newest generation first]}`, sharded by `sha256(path)[:2]` | `build_snapshot_members` (`:340-352`), `_file_commits` (`:356`) | **Nobody** |
| `blob-paths:<xx>`: `{blob_id: [paths at the head]}` | `:340` | **Nobody** |
| `commit-gen`, `commits:<n>` | `:330-338` | Generation numbers via `generation_of` |

TM-R42: a snapshot index is anchored to the root tree only, and is a plan, never a proof.

### 4.6 Partial clones

- **`Vault__Scope`** (`sgit_ai/storage/Vault__Scope.py:30`):
  - `is_scoped`, `is_shallow`, `contains_path`, `boundary_ids`;
  - `Vault__Scoped_Tree.flatten` returns `(flat, opaque)` for a scoped clone.
- **Selective working copies:** the `--no-checkout` record. A tracked file absent from disk is "not checked out",
  not deleted (CHANGELOG 0.26.0).
- **Safe types:** `Safe_Str__File_Path` **rewrites every character outside `[a-zA-Z0-9/\_.- ]` to `_`**
  (`sgit_ai/safe_types/Safe_Str__File_Path.py`; the AC-L-001 / TM-R36 family). An output schema that types a vault
  content path with it mangles `josé.md`. The new schemas use a Unicode-tolerant type (section 5.8).

## 5. Design

### 5.1 Line differ: `Vault__Line_Diff`

**One** line differ for blame, `-G`, the unified diff and the merge.
- Design 01 (diff3) needs matching blocks between base/ours and base/theirs. If design 01 specifies its own line
  differ, this design uses that class instead and the names below are aliases. There must be one implementation.

**Interface**
- **File:** `sgit_ai/core/actions/diff/Vault__Line_Diff.py`, class `Vault__Line_Diff(Type_Safe)`.
- **Fields:**
  - `ignore_whitespace : bool = False` (`-w`: lines compared with all whitespace removed, as Git's `-w`);
  - `max_cost : Safe_UInt = 0` (0 = the default bound below).
- **Methods:**
  - `split_lines(data: bytes) -> list` — `bytes.splitlines(keepends=True)`. A final line without `\n` stays
    distinct from the same text with one, as in Git ("\ No newline at end of file").
  - `matching_blocks(a: list, b: list) -> list` — `[(a_start, b_start, length)]`, ascending, ending with the sentinel
    `(len(a), len(b), 0)`, the same contract as `difflib.SequenceMatcher.get_matching_blocks()`.
  - `opcodes(a, b) -> list` — `[('equal'|'replace'|'delete'|'insert', i1, i2, j1, j2)]` derived from the blocks.

**Algorithm: Myers O((N+M)·D) greedy diff, the algorithm behind Git's default**
- Common prefix and suffix are stripped first, as xdiff does.
- Lines are interned to integers (hash map of line → id; with `-w`, the key is the line with whitespace removed).
- Linear-space divide and conquer (middle snake) above 10,000 lines.
- When D passes a cost bound (default `max(256, sqrt(N+M) * 16)`, xdiff's "heuristic" idea), it falls back to
  `difflib.SequenceMatcher(None, a, b, autojunk=False)` on the remaining window, so a pathological pair never runs
  quadratic for minutes.

**Why not `difflib` alone**
- `SequenceMatcher` finds longest matching blocks, not a minimal edit script. With `autojunk=True` (the default) it
  treats lines that occur in more than 1% of a file over 200 lines as junk, and loses matches on files full of blank
  lines.
- Blame attribution would then differ from Git's on common files.
- `difflib.unified_diff` stays for printing hunks today. It is switched to `opcodes()` in step 3 so that the printed
  diff and blame agree.

### 5.2 Renames: `Vault__Renames`

**Classes**
- **File:** `sgit_ai/core/actions/diff/Vault__Renames.py`, class `Vault__Renames(Type_Safe)`.
- **Fields:**
  - `min_score : Safe_UInt__Rename_Score = 50` (percent);
  - `limit : Safe_UInt = 1000`;
  - `enabled : bool = True`;
  - `exact_only : bool = False`.
- **Schemas** (`sgit_ai/schemas/diff/`):
  - `Schema__Rename_Pair`: `old_path : Safe_Str__Content_Path`, `new_path : Safe_Str__Content_Path`,
    `score : Safe_UInt__Rename_Score` (0–100), `exact : bool`;
  - `Schema__Rename_Result`: `pairs : list[Schema__Rename_Pair]`, `limit_hit : bool`,
    `candidates : Safe_UInt` (sources × destinations considered), `unread : Safe_UInt` (blobs that were not local
    and not fetched; those files took part in the exact pass only).

**Entry point (also the API design 01 consumes)**

```python
def detect(self, deleted: dict, added: dict, content_of=None) -> Schema__Rename_Result:
    """deleted/added: {path: flat entry} (the diff_trees / flatten shape: blob_id, size, content_hash, ...).
    content_of: callable(entry) -> bytes | None, the plaintext of an entry (None = not available).
    Without content_of only the exact pass runs. Never raises for a missing blob."""
```

**Pass 1, exact (always, no limit):**
1. Group `deleted` by `(content_hash, size)`, skipping entries without a `content_hash`.
2. For each added path in sorted order, the candidates are the deleted paths with the same key not yet used. Pick
   the one with the same basename if any (Git's preference), else the first by path.
3. Score 100, `exact=True`.
4. A source pairs at most once. A second destination of the same content is an add (copies are out of scope).
5. Empty files take part (Git 2.43 pairs a lone moved empty file; confirmed). With several empty files, only
   same-basename pairs are made, so empty files never pair at random. Test 9.1 R10 checks this against Git.

**Pass 2, basename (needs `content_of`, no limit):**
1. Among unpaired paths, take basenames that occur exactly once among the remaining sources and exactly once among
   the remaining destinations.
2. Score each such pair by `similarity`.
3. Accept at `min_basename_score = min_score + (100 - min_score) / 2` (75 at the default), Git's rule from 2.33.

**Pass 3, inexact matrix (needs `content_of`):**
1. If `len(src) > limit or len(dst) > limit` and `len(src) * len(dst) > limit * limit`, skip the pass and set
   `limit_hit=True` (Git's `too_many_rename_candidates`).
2. Else, for each destination, score every source that passes the size precheck, keep the best four
   (`NUM_CANDIDATE_PER_DST`, as Git), sort all kept pairs by score descending then by destination path, and accept
   greedily, each path once, at `score >= min_score`.

**`similarity(src: bytes, dst: bytes) -> int`** follows Git's `diffcore-delta.c` and `estimate_similarity`.
1. **Size precheck:** with `max_size = max(len)` and `delta = abs(len(src) - len(dst))`, return 0 when
   `max_size * (100 - min_score) < delta * 100`. A file cannot be a 50% rename of one under half its size.
2. **Chunking (`hash_chars`):** chunk each buffer. A chunk ends after a `\n` or after 64 bytes. For a text buffer (no
   NUL in the first 8,000 bytes), a `\r` directly before `\n` is skipped. Key each chunk by its bytes; the count is
   the chunk's length.
3. **Count:** `copied = Σ min(src_count[k], dst_count[k])` over keys present in both.
4. **Score:** `copied * 100 // max_size`, truncated as Git prints it (Git computes on `MAX_SCORE = 60000` and prints
   `score * 100 / MAX_SCORE`; the integer percent is the same up to rounding). Test 9.1 R4 compares with Git within
   ±1.
5. Empty `src` or `dst`: 0 (an empty file is only ever an exact rename).

**`content_of` cost control**
- Callers pass `Vault__Blob_Reader.content` (5.3).
- Blobs larger than `RENAME_MAX_BYTES = 4 MB` (Git uses `big_file_threshold` 512 MB, but our reads are decrypts) are
  scored by exact pass only and counted in `unread`.
- In-memory chunk maps are memoised per blob id for one `detect` call.

**Trust:**
- `content_hash` is the committer's claim. For **display** (diff, show, log), pairing by the claim is accepted: a
  lying writer (A3) can make `--stat` show a false rename and nothing else.
- For the **merge**, design 01 must call `detect(..., content_of=...)` with `verify_exact=True` (a keyword on
  `detect`). Each exact pair is then confirmed by decrypting both blobs and comparing bytes, and an unconfirmed
  claim drops to pass 3.

**Coordination note for design 01**
- `three_way_merge` (`sgit_ai/core/actions/merge/Vault__Merge.py:14`) compares blob ids, and blob ids are random per
  write (4.1). The same content written independently on both sides is reported as a conflict today
  (`ours_bid != theirs_bid`). Comparing `content_hash` + size (verified when it matters) fixes that.
- The merge's rename pairs: `detect(base_deleted_in_ours, ours_added)` and the same for theirs.

### 5.3 Reading content: `Vault__Blob_Reader`

**Purpose:** one place that turns a flat entry into plaintext, for renames, blame, grep, pickaxe and the pruned diff.

**Interface**
- **File:** `sgit_ai/core/actions/history/Vault__Blob_Reader.py`, class `Vault__Blob_Reader(Type_Safe)`.
- **Fields:**
  - `crypto`, `obj_store`, `read_key : bytes`, `vault_id : str`, `sg_dir : str`;
  - `api : object = None` (set only when a remote is configured: the `_on_demand_api` rule);
  - `offline : bool = False`;
  - `memo_bytes : Safe_UInt = 64 MB`;
  - counters `blobs_read`, `blobs_fetched`, `blobs_missing` (`Safe_UInt`; reported in `--json` stats and used by the
    tests instead of a counting double).

**Behaviour**
- `content(entry) -> bytes | None`:
  1. A local object → `obj_store.load` (this also reads from a `--pack-store` clone by offset).
  2. Else, with `api` and not `offline` → fetch with `api.read` / `read_large`, `_save_verified` (verified by
     content address before it is written, as `sparse_cat` does), then load.
  3. Else → `None` and `blobs_missing += 1`.
- Decryption errors propagate (a wrong key must fail loudly, as `history log` does with `InvalidTag`).
- `prefetch(entries: list) -> None`: one `api.batch_read` for every missing blob in the list, in batches of the
  existing batch size. Blame and grep call it before walking, so a sparse clone makes a handful of requests instead
  of one per file.
- The memo is an LRU keyed by blob id up to `memo_bytes` of plaintext, **in memory only**.

### 5.4 Path history: `Vault__Path_History`

**Interface**
- **File:** `sgit_ai/core/actions/history/Vault__Path_History.py`, class `Vault__Path_History(Type_Safe)`.
- **Fields:** `crypto`, `obj_store`, `read_key`, `sub_tree : Vault__Sub_Tree`, `tree_memo : dict` (tree id →
  `{name: entry}`, bounded at 4,096 trees).

**Methods**
- `entry_at(tree_id, path) -> dict | None`: walks the path's folders with `_load_tree_entries` (plain JSON) and returns
  the file's flat entry (the `_entry_dict` shape) or None. Cost: one tree read per path segment, memoised by tree id.
  Tree ids are content addresses, so the memo never needs invalidating.
- `same_at(tree_a, tree_b, path) -> bool`: true when the entry at `path` is identical in both. It short-circuits from
  the root: equal root ids → True; then each folder on the path, and the first equal folder id → True. At the file:
  equal blob ids → True, else equal `(content_hash, size)` → True. That treats a re-encryption of unchanged content
  as unchanged, which fixes `log_file`'s false `modified` (4.3).
- `changed_paths(tree_new, tree_old) -> dict`: `diff_trees` passthrough, memoised per pair for one command.

**Consumers**
- `Vault__Diff.log_file` is rewritten on it: `entry_at` per commit instead of `flatten` per commit.
- `--follow`, blame and pickaxe with-`--file`.

### 5.5 The pruned diff (prerequisite)

`Vault__Diff` gains `_changed_files(tree_new, tree_old, renames: Vault__Renames) -> list[Schema__Diff_File]`:
1. Take `diff_trees` (or the index's `changes` when the caller has them).
2. Run `Vault__Renames.detect` over `added`/`deleted`.
3. For each modified or renamed file, read both sides with `Vault__Blob_Reader` and run the unified diff. For an
   added or deleted file read one side (needed for `--patch` of an added file and for the binary flag).

The diff methods change as follows:

| Method | Change |
|---|---|
| `diff_commits`, `show_commit`, `log_range_with_details`, `diff_range` | Switch to `_changed_files`. They no longer call `_flatten_commit` / `diff_files` for two commits. |
| `diff_vs_head`, `diff_vs_remote`, `diff_vs_commit` | Scan the working copy through the scan cache (`Vault__Sync__Base` scan: the size/mtime/hash rule) to find changed paths. Read and decrypt only those, plus the committed side. Unchanged files are no longer read. |

**Output stays the same** except that renames now appear (D4). `Schema__Diff_Result.files` loses its `unchanged`
rows for commit-to-commit diffs. They were never printed (`CLI__Diff._print_result` skips them,
`sgit_ai/cli/CLI__Diff.py:271`), and no JSON path emits `Schema__Diff_Result` for two commits (`--json` there goes
through `diff_range`). The working-copy JSON path keeps them only if a test shows a consumer, else drops them too;
step 3 checks this.

### 5.6 Blame: `Vault__Blame`

**Classes**
- **File:** `sgit_ai/core/actions/history/Vault__Blame.py`, class `Vault__Blame(Type_Safe)`.
- **Fields:** `crypto`, `api : object = None`, `ignore_whitespace : bool`, `first_parent : bool`,
  `follow_renames : bool = True`, `text : bool = False`, `offline : bool = False`.
- **Schemas** (`sgit_ai/schemas/history/`):
  - `Schema__Blame_Line`: `final_line : Safe_UInt`, `orig_line : Safe_UInt`, `commit_id : Safe_Str__Commit_Id`,
    `orig_path : Safe_Str__Content_Path`, `text : Safe_Str__Diff_Text`;
  - `Schema__Blame_Commit`: `timestamp_ms`, `author : Safe_Str__Diff_Text`, `author_key_id`,
    `summary : Safe_Str__Diff_Text`, `boundary : bool`, `previous_id`, `previous_path`;
  - `Schema__Blame_Result`: `schema = 'history_blame_v1'`, `path`, `rev`, `boundary_reason`,
    `commits : dict[Safe_Str__Commit_Id, Schema__Blame_Commit]`, `lines : list[Schema__Blame_Line]`, `stats`.

**Entry point:** `blame(directory, path, rev='', ranges=None) -> Schema__Blame_Result`.

**Algorithm** (Git's `blame.c`, `assign_blame` / `pass_blame`, simplified to what we support):

1. **Start.**
   - Resolve `rev` (default the clone's HEAD) with `Vault__Revision`.
   - `entry = path_history.entry_at(commit.tree_id, path)`.
   - None, or a folder → exit 1 with `path not found in <rev>`.
   - Content via `Vault__Blob_Reader`. Binary (NUL rule) without `--text` → exit 1 with
     `binary file: pass --text to blame it line by line`.
   - Lines via `Vault__Line_Diff.split_lines`. `-L` ranges are resolved on this content.
2. **Entries.**
   - A *blame entry* is `(final_start, count, suspect_start)`, held per *origin* `(commit_id, path, entry)`.
   - Start: one entry per `-L` range, all on origin `(rev, path, entry)`.
   - Origins wait in a priority queue keyed by **generation number** (from the pack index's `commit-gen`, or
     `Vault__Pack_Index.generation_of` with its local memo) and then `timestamp_ms`, highest first. Git's queue
     orders by commit date; generation avoids clock skew between agents and gives the same order on linear history.
3. **Process the next origin O** (commit C, path P, entry E):
   - **Parents:** C's parents in order; with `--first-parent`, only the first.
   - **Boundary.** C has no parents; or C is a shallow boundary (`Vault__Scope.is_boundary`); or C's parent commit
     object is not local and cannot be fetched. Then every entry of O is final and C is marked `boundary`.
     `boundary_reason` is set to `shallow` / `offline` when that is the cause.
   - **Find each parent's version.** `E_p = entry_at(parent.tree_id, P)`.
     - If None and `follow_renames`: run `Vault__Renames.detect` on `diff_trees(C.tree, parent.tree)` restricted to
       destination `P` (all deleted paths as sources, only `P` as destination; the limit counts 1 × sources, so the
       inexact pass always runs). A pair gives `(P_p, E_p)`.
     - If still None, that parent does not hold the file.
   - **Whole pass.** If some parent has `same_at(C.tree, parent.tree, …)` for the file (same blob, or same
     `content_hash` + size), all of O's entries move to that parent's origin unchanged, without a diff. Git does this
     for an identical parent, and it is the step that makes blame cheap on a long history. Done with O.
   - **Diff pass.** Otherwise, for each parent holding the file, in order:
     - Diff `parent content → C content` with `Vault__Line_Diff` (honouring `-w`).
     - For every `equal` block `(i, j, n)`, the overlap of each remaining entry's suspect range `[j, j+n)` moves to
       the parent's origin with `suspect_start` remapped to `i + (s - j)`. Entries are split at block edges.
     - Lines left after all parents stay blamed on C.
     - At a merge, lines equal to the first parent go there first and the rest are offered to the next parent:
       Git's order.
   - **Merge origins.** A parent origin already in the queue (same commit, same path) gets the entries appended, so
     a commit is diffed once per path.
4. **Finish.** Final entries are sorted by `final_start` and expanded to lines with `orig_line = suspect_start + k`.
   Commit metadata is collected:
   - `author`: the branch name from the branch index (`_branch_names` as in `CLI__Vault`, `:2338`), else the key id;
   - `summary`: the first line of the decrypted message;
   - `previous`: the first parent holding the file and its path.

**Pack index acceleration (step 9).**
1. When the head's snapshot index is local and verified (`open_index(kind='snapshot')`), read
   `file-commits:<shard_of_path(P)>` for `P`.
2. The listed commits are the **plan**: the walk visits only them, and treats each unlisted stretch between two
   listed commits as unchanged for `P`.
3. Because the snapshot index is anchored only at the root (TM-R42), the plan is checked as it is used. For each
   step from listed commit `C` to the next listed ancestor `C'` on the walk, `same_at(parent(C).tree, C'.tree, P)`
   must hold: the file must really be unchanged across the skipped stretch.
4. One failed check drops the plan for the rest of the command (noted once on stderr:
   `index plan for <path> did not match the trees; walking`) and the walk continues commit by commit.
5. A lying index can therefore cost time, never a wrong attribution.
6. Renames end the plan at the commit where the path was added. The plan of the old path is read from its own shard.

**Partial clones and limits:**
- **Scoped:** `P` outside `scope.contains_path` → exit 1 with
  `'<path>' is outside this clone's folders (<list>); widen with: sgit fetch <folder>`.
- **Shallow:** boundary as above.
- **Sparse / selective:** blobs are fetched on demand (`Vault__Blob_Reader.prefetch` with the blobs of the planned
  commits when a plan exists).

### 5.7 Grep: `Vault__Grep`

**Classes**
- **File:** `sgit_ai/core/actions/history/Vault__Grep.py`, class `Vault__Grep(Type_Safe)`.
- **Fields:** `crypto`, `api : object = None`, options as typed fields:
  - `patterns : list[Safe_Str__Grep_Pattern]`
  - `fixed`, `ignore_case`, `word`, `invert`, `untracked`, `text`, `skip_binary` (`bool`s)
  - `max_count : Safe_UInt`, `before : Safe_UInt`, `after : Safe_UInt`
  - `only_matching : bool`, `offline : bool`
- **Schemas:**
  - `Schema__Grep_Match`: `rev`, `path : Safe_Str__Content_Path`, `line : Safe_UInt`, `text : Safe_Str__Diff_Text`,
    `spans : list`, `context : bool`;
  - `Schema__Grep_Result`: `schema = 'grep_v1'`, `matches`, `files_searched`, `binary_matches`, `skipped`.

**Engine**
1. **Compile.** One Python `re` pattern: `-F` escapes each pattern; several patterns join as `(?:p1)|(?:p2)`; `-w`
   wraps as `(?<![\w])(?:…)(?![\w])` (Git's word rule: the match must start and end at a word boundary of
   `[A-Za-z0-9_]`; test 9.3 G6 checks edge cases against Git); `-i` adds `re.IGNORECASE`.
   - Every pattern is checked first by `Vault__Regex_Guard.check(pattern)` (5.9).
   - Matching is on `str`: content is decoded `utf-8` with `errors='surrogateescape'`, so any byte sequence
     round-trips and non-UTF-8 files still match byte-for-byte on their ASCII parts.
2. **Prefilter per file.** One `search` over the whole decoded text; no match → skip the file without splitting
   lines. With `-v`, `-L` or `-c`, the prefilter is skipped (they need every line). That keeps the common case at C
   speed: one regex scan per file.
3. **Lines.** On a hit, iterate lines with offsets (`str.splitlines(keepends=True)` once), collect matches, context
   windows and `-m` cut-off, and emit `Schema__Grep_Match` rows in path order then line order.
4. **Binary.** NUL in the first 8,192 bytes:
   - default → one `Binary file <path> matches` row when the prefilter hits;
   - `-I` → skipped;
   - `--text` → treated as text.

**Sources**

| Mode | Files | How read |
|---|---|---|
| Working copy (no `<rev>`) | Tracked files present on disk: the head's flat map ∩ disk, filtered by `Vault__Ignore` as `status` filters, `--untracked` adds the rest; pathspec applied first | `Vault__Path_Guard.read_regular` (never through a link, never blocks on a FIFO), the same reader `_scan_working_files` uses (`Vault__Diff.py:814`). A tracked file not on disk (selective working copy) is **not** searched and is counted in `skipped.not_checked_out`, with a note: `N tracked file(s) not checked out were not searched; search them with: sgit grep <pattern> HEAD` (D7). |
| `<rev>` (one or more) | `flatten(tree)` (scoped: `Vault__Scoped_Tree.flatten`, opaque folders counted in `skipped.outside_scope`) ∩ pathspec | `Vault__Blob_Reader.prefetch` then `content`; missing and not fetchable → `skipped.not_local` with a note naming the count and `sgit fetch` |

**Order and streaming.**
- Files are processed in sorted path order and printed as they are found (no full result held unless `--json`), so
  `sgit grep x | head` returns at once.
- The reader's memo is off for grep, since each blob is read once.

### 5.8 Pickaxe: `Vault__Pickaxe`

**Interface**
- **File:** `sgit_ai/core/actions/history/Vault__Pickaxe.py`, class `Vault__Pickaxe(Type_Safe)`.
- **Fields:** `mode : Safe_Str` (`'S'` or `'G'`), `needle : Safe_Str__Grep_Pattern`, `regex : bool`,
  `ignore_case : bool`, `only_path : Safe_Str__Content_Path = None`, plus `Vault__Blob_Reader` and `Vault__Line_Diff`.
- **Method:** `matches(commit, parent, changes) -> list[path]`, where `changes` is the commit's change list (the
  index's `changes` member when available, else `diff_trees`).

**Rules**
- **`-S`:** for each changed file (A, M, D; restricted to `only_path`), count occurrences in old and new content
  (literal: `str.count`, non-overlapping as Git; `--pickaxe-regex`: `len(re.findall)`). Different counts → the path
  matches. Binary files are counted too (Git's `-S` does). An added file counts against 0 and a deleted file
  against 0.
- **`-G`:** run the line diff of old → new and test each inserted or deleted line with `re.search`. Binary files are
  skipped unless `--text` (Git's `-G` rule).
- **Merges** (more than one parent): skipped, counted in the note.
- **Wiring:**
  - `_print_log` (`CLI__Vault.py:2274`) gains a pickaxe branch: walk the DAG newest-first as the filtered log does.
  - For each non-merge commit get `changes` from `_index_changes_provider` or `diff_trees`, apply the other filters
    first (cheap: message, date, author), then `Vault__Pickaxe.matches`.
  - Stop once `-n` (default 50) matches are printed.
  - `--stat` shows the matching files only, or all with `--pickaxe-all`.

### 5.9 Shared pieces and safe types

| New | File | What |
|---|---|---|
| `Vault__Regex_Guard` | `sgit_ai/core/Vault__Regex_Guard.py` | `check(pattern) -> None` (raises `Vault__Revision_Error`, the class `--grep` already raises) and `nested_repeat(pattern)`, **moved** from `Vault__Log_Filter` (`:50-138`), which then delegates (its tests keep passing unchanged). Adds a pattern length cap of 1,000 characters. |
| `Safe_Str__Content_Path` | `sgit_ai/safe_types/Safe_Str__Content_Path.py` | A vault content path for output: regex `^[^\x00-\x1f\x7f]*$` in MATCH mode (any printable Unicode, no control characters), max 4,096, `trim_whitespace=False`, strict. A control character in a decrypted name is a refusal, never a rewrite. |
| `Safe_Str__Grep_Pattern` | `sgit_ai/safe_types/Safe_Str__Grep_Pattern.py` | Any printable text up to 1,000 characters, no NUL, `trim_whitespace=False`. |
| `Safe_UInt__Rename_Score` | `sgit_ai/safe_types/Safe_UInt__Rename_Score.py` | 0..100. |
| `Safe_Str__Blame_Range` | `sgit_ai/safe_types/Safe_Str__Blame_Range.py` | `^[0-9,+\-/]…$`-style spec text up to 200 characters; parsing in `Vault__Blame.parse_range`. |

### 5.10 File-by-file changes

| File | Change |
|---|---|
| `sgit_ai/core/actions/diff/Vault__Line_Diff.py` | New (5.1) |
| `sgit_ai/core/actions/diff/Vault__Renames.py` | New (5.2) |
| `sgit_ai/core/actions/history/Vault__Blob_Reader.py` | New (5.3) |
| `sgit_ai/core/actions/history/Vault__Path_History.py` | New (5.4) |
| `sgit_ai/core/actions/history/Vault__Blame.py` | New (5.6) |
| `sgit_ai/core/actions/history/Vault__Grep.py` | New (5.7) |
| `sgit_ai/core/actions/history/Vault__Pickaxe.py` | New (5.8) |
| `sgit_ai/core/Vault__Regex_Guard.py` | New; `Vault__Log_Filter` delegates (5.9) |
| `sgit_ai/schemas/diff/Schema__Rename_Pair.py`, `Schema__Rename_Result.py` | New |
| `sgit_ai/schemas/history/Schema__Blame_Line.py`, `Schema__Blame_Commit.py`, `Schema__Blame_Result.py` | New |
| `sgit_ai/schemas/history/Schema__Grep_Match.py`, `Schema__Grep_Result.py` | New |
| `sgit_ai/schemas/history/Schema__History_Rename.py` | New: `old_path`, `new_path`, `score`, `exact`, `lines_added`, `lines_removed` |
| `sgit_ai/schemas/Schema__Diff_File.py` | Add `old_path : Safe_Str__Content_Path = None`, `similarity : Safe_UInt__Rename_Score`; `status` may be `'renamed'` |
| `sgit_ai/schemas/history/Schema__History_Log_Commit_Entry.py` | Add `files_renamed : list[Schema__History_Rename]` |
| `sgit_ai/schemas/history/Schema__History_Diff_Result.py` | Add `files_renamed : list[Schema__History_Rename]` |
| `sgit_ai/core/actions/diff/Vault__Diff.py` | Pruned diff (5.5); `log_file` on `Vault__Path_History` with `follow` (5.4); rename headers in `_unified_diff`; `opcodes()` from `Vault__Line_Diff` |
| `sgit_ai/objects/Vault__Inspector.py` | `_file_stat_from_diff` delegates to `Vault__Renames` (exact only when no reader is given, so plain `log --stat` stays tree-only and fast; inexact with a reader); stat tuples gain the score |
| `sgit_ai/cli/CLI__Blame.py` | New `CLI__Blame(Type_Safe)`: `cmd_blame(args)`, the three output formats, the exit codes |
| `sgit_ai/cli/CLI__Grep.py` | New `CLI__Grep(Type_Safe)`: `register_args(parser)` (shared by top-level and `file grep`), `cmd_grep(args)`, exit codes 0/1/2 |
| `sgit_ai/plugins/history/CLI__History.py` | `blame` subparser; `-M/--find-renames`, `--no-renames`, `--rename-limit` on log/diff/show; `--follow`, `-S`, `-G`, `--pickaxe-regex`, `--pickaxe-all`, `-i` on log; dispatch: pickaxe allowed with the plain-log filters and `--file` |
| `sgit_ai/plugins/file/CLI__File.py` | `file grep` subparser via `CLI__Grep.register_args` |
| `sgit_ai/cli/CLI__Main.py` | Top-level `grep` parser, injection of `CLI__Blame` / `CLI__Grep` |
| `sgit_ai/cli/CLI__Diff.py` | Pass rename options; print rename headers and `R` rows; `cmd_log_file` prints `R` rows with `--follow` |
| `tests/unit/cli/test_CLI__B07__Namespace_Moves.py` | `'grep'` added to `TOP_LEVEL_COMMANDS` |

**Compatibility**
- **No format gate:** nothing is written to the vault or the host.
- **No change in what other clients see.**
- **Local state:** no new local file. The flat cache is read, never extended.
- **JSON consumers see added fields.** The one behaviour change, renamed files moving out of
  `files_added`/`files_deleted`, is D4.

## 6. Security and threat model

| Topic | Analysis | Decision |
|---|---|---|
| Regex denial of service | Patterns come from the user (or an agent driving sgit). Content comes from teammates (A3) and is verified by content address, so the host cannot pick it. Python's `re` has no timeout. A vulnerable pattern over hostile content is the risk. | Every user pattern (`grep`, `-G`, `--pickaxe-regex`, `blame -L /re/`) goes through `Vault__Regex_Guard.check`: nested repetition refused (the rule `--grep` already uses), length ≤ 1,000. `-F` and `-S` without `--pickaxe-regex` are literal and never compiled as a regex. |
| Plaintext on disk | Blame, grep, pickaxe and renames decrypt into memory only. The `Vault__Blob_Reader` memo is in-process and bounded. **No new on-disk cache.** The flat cache (paths, sizes, content hashes, types; TM-R41) is read, not extended. Fetched blobs are written to `bare/data` encrypted, as `history show`'s on-demand fetch already does. | A future blame or grep cache would be plaintext-derived and must live under `.sg_vault/local/` at 0600 and be added to TM-R41. Not planned. |
| Lying `content_hash` | A writer (A3) can claim any `content_hash`. Display: a false `R` row, nothing more. Merge: design 01 verifies exact pairs by bytes (`verify_exact=True`). | Accepted for display; closed for the merge. |
| Lying pack index plan | `file-commits` is anchored only at the root (TM-R42). Blame verifies every skipped stretch with `same_at` (5.6): a lie costs a fallback walk, never a wrong line. | TM-R42's row gains one sentence: "`file-commits` is used by `history blame` and `log --follow` as a skip plan, verified per stretch". |
| Terminal escapes in content | `grep`, `blame`, `cat` and `history diff` print decrypted file text raw, as Git does. A teammate's file holding ANSI or OSC sequences can rewrite what a terminal shows (A3). | **New row TM-R4x (accepted)**: "decrypted file content is printed raw by `cat`, `history diff/show`, `grep` and `blame`, as Git prints it; `--json` output escapes it". Known_Gaps test: a file containing `\x1b]0;x\x07` is printed byte for byte in plain mode and escaped in `--json`. |
| Control characters in decrypted names | A name with `\n` or `\x1b` could forge output lines. `Safe_Str__Content_Path` refuses control characters, so a JSON row cannot hold one. Plain output prints such a path quoted the way Git quotes it (`"a\nb"` with C escapes, `core.quotePath`). | `Vault__Grep` / `Vault__Blame` call one helper, `Vault__Path_Quote.quote(path)` (a method on a small new class in `sgit_ai/core/Vault__Path_Quote.py`), for every printed path. |
| Working-copy reads | Grep reads only regular files through `Vault__Path_Guard.read_regular`: no symlink followed (TM-F11, F27) and no FIFO blocking (F1). Ignored folders (`.sg_vault`, `.git`) are never entered. | The same reader as `status`. |
| On-demand fetch | Only with a configured remote (`_on_demand_api`). Fetched objects are verified before they are written. `--offline` forbids it. | Matches `history show` today. |
| Information to the host | A fetch on demand tells the host which blob ids a clone asked for, as `show`, `cat` and `fetch` already do (TM-R08 family). Grep in the working copy contacts nobody. | Noted in the user doc for `--offline`. |

## 7. Interactions

| Clone kind | Renames | Blame | Grep | Pickaxe |
|---|---|---|---|---|
| Full | All passes | Full walk, or the index plan | Working copy or rev | DAG walk |
| **Shallow** (`clone --depth`) | Normal for commits that are local | Stops at a boundary: lines blamed there are marked `^`, with a stderr note and `boundary_reason: 'shallow'` | Rev mode works for any local commit; a rev below the boundary → exit 2: `<rev> is below this clone's shallow boundary; deepen with: sgit fetch --unshallow` | Searches local history; the output ends with `… history stops here: shallow clone`, as `history log` does today (`CLI__Vault.py:2306`) |
| **Scoped** (`clone --path`) | Pairs within held folders only. Opaque folders carry no content, so a rename across the scope edge shows as A or D. | A path outside the scope → exit 1 with the widen hint | Rev mode searches held folders only, counted in `skipped.outside_scope` with a note | Changes outside the scope are invisible (their trees are not local); note: `searched inside <folders> only` |
| **Sparse / selective** | Blobs fetched on demand for inexact scoring; offline, exact pass only (`unread` > 0 → note) | Blobs fetched on demand (prefetch); offline → `offline` boundary | Working copy: on-disk files only + note (D7). Rev: fetch on demand, else `skipped.not_local` | Fetch on demand per commit; offline → that commit's unreadable files are counted, and the note gives the count |
| **Pack vault** | `changes` member gives the per-commit lists; blobs from the local store | `file-commits` plan (5.6) | As full | `changes` member per commit (no tree read) |
| **`--pack-store`** | Objects read by offset from kept packs, verified on read | Same | Same | Same |
| **Read-only clone** | Same as full (reading only) | Same | Same | Same |
| **`--vault-key` on a bare checkout** (`history log` already allows it, `CLI__Vault._read_key_or_exit`, `:2247`) | Supported | Supported (`rev` required, since no clone branch head → `history blame HEAD` is resolved from the named branch) | Rev mode only (no working copy) | Supported |

## 8. Performance, caps and limits

Reference vaults: the 76,000-file / 58,553-folder synthetic vault (release readiness, 26 Oct) and the 228,000-file /
38,000-leaf-folder one (0.25.0 notes). Estimates below are from the measured costs: ~3 ms a tree through `Type_Safe`
(avoided here), well under 1 ms through `_load_tree_entries`, and AES-GCM decrypt in C.

| Operation | Today | Planned | Bound |
|---|---|---|---|
| `history show` of a 5-file commit, 228k vault | Decrypts both trees' every blob (~2.4 GB) | `diff_trees` (folders on 5 paths) + 10 blob reads: under 1 s | Follows the change |
| `history log --patch -n 10`, 228k vault | 10 × two full decrypts | 10 × the line above | Follows the change |
| `history log --stat -n 50` with renames | Exact pairing, tree-only | The same by default (exact only without a reader); inexact only for commits with both adds and deletes, reading only those blobs | `RENAME_MAX_BYTES` 4 MB, limit 1000 |
| `history log --file P` over 2,000 commits | 4,000 full flattens (incremental from the flat cache, but a dict copy of 228k entries each) | 2,000 × `entry_at` (depth ≈ 5 tree reads, memoised; most short-circuit at the root) ≈ 1–3 s | Tree memo 4,096 |
| `history blame` of a 1,000-line file, 2,000-commit history, 40 commits touched it | n/a | Walk: 2,000 × `same_at` (root-equal fast path) + 40 diffs ≈ 2–4 s; with the index plan: 40 steps ≈ 0.5 s | Memo 64 MB |
| `sgit grep x` (working copy, 228k files, ~1.2 GB) | n/a | One read + one C-level `search` per file. Disk-bound: ~10–30 s on a fast disk. Prints as it goes. | No cap; progress on stderr after 5 s |
| `sgit grep x HEAD` (228k blobs) | n/a | Decrypt 228k objects (Python overhead per object dominates): ~60–120 s. A pathspec is the intended use. | A warning when more than 20,000 files are searched with no pathspec |
| `history log -S foo -n 20` | n/a | Per commit: the changed blobs (old + new). On the newsroom vault (~300 files per pass): ~1–2 s per pass commit. | Stops at `-n` |

Hard caps:
- pattern length 1,000;
- `-L` ranges 100;
- blame on a file over 50 MB refused (`file is larger than 50 MB: blame refused`);
- rename scoring per blob 4 MB;
- rename limit 1,000 (option);
- blob memo 64 MB.

## 9. Test plan

All tests are real objects. Vaults are built with `Vault__Test_Env` (`tests/_helpers/vault_test_env.py`: fixed test
key, in-memory API) and commits made with `write_file`. Where Git is the oracle, the same history is built in a
temporary Git repository (`git -c user.name=t -c user.email=t@t`). Those tests are skipped when `shutil.which('git')`
is None. CI runners have Git. No `__init__.py` in test folders.

### 9.1 `tests/unit/core/actions/diff/test_Vault__Renames.py` — `Test_Vault__Renames`

| # | Case | Expect |
|---|---|---|
| R1 | A file moved unchanged | One pair, score 100, `exact=True`; no blob read (`reader.blobs_read == 0`) |
| R2 | Two identical files deleted, one added with the basename of the second | Paired with the same-basename source |
| R3 | 1,001 unchanged moves | All exact pairs, `limit_hit=False` |
| R4 | 40 generated edits (insert, delete, change lines; CRLF; long lines over 64 bytes; no final newline) | Score equals `git diff -M --name-status` R-score ±1 for every pair, and the same R/A/D verdict |
| R5 | 100 lines → 49 lines | Not paired (A + D), as Git |
| R6 | 49 → 51 lines | Paired, 95 (Git: `R095`) |
| R7 | 1,001 × 1,001 edited, different basenames | `limit_hit=True`, all A/D; with `limit=1001`, all pairs |
| R8 | The same with identical basenames in another folder | All paired through the basename pass, no `limit_hit` |
| R9 | A binary file renamed with one byte changed | Paired by similarity (Git pairs binaries) |
| R10 | One empty file moved; then three empty files moved, one with the same basename | One pair; then only the same-basename pair (oracle: Git) |
| R11 | Size precheck: 10 KB → 3 KB | Not scored (`similarity` returns 0 without chunking) |
| R12 | `content_of` returns None for one side | Exact pass only for it; `unread` counted |
| R13 | `verify_exact=True` with a forged `content_hash` (two different contents, same claimed hash) | Pair rejected by the byte check |
| R14 | Determinism | The same input in shuffled dict order gives identical output |

### 9.2 `tests/unit/core/actions/diff/test_Vault__Line_Diff.py` — `Test_Vault__Line_Diff`

| # | Case |
|---|---|
| L1 | Identical, empty, one empty side |
| L2 | `matching_blocks` contract: ascending, the sentinel, total equal lines = LCS length for 200 random pairs (LCS by a reference dynamic-programming method in the test) |
| L3 | A file of 500 blank lines plus edits: no line lost to junk heuristics |
| L4 | `-w` ignores spaces and tabs inside lines |
| L5 | No final newline is a distinct line |
| L6 | The cost bound: a 20,000 × 20,000 random-line pair finishes under 2 s |

### 9.3 Other unit tests

**`tests/unit/core/actions/history/test_Vault__Path_History.py`**
- `entry_at`: root file, deep file, missing, a folder path.
- `same_at`:
  - root-equal fast path (no tree read beyond the root, asserted by the memo count);
  - re-encrypted identical content counts as the same;
  - a changed file.
- `log_file` regression: the statuses and order equal today's on the existing fixtures, except the re-encryption case.

**`tests/unit/core/actions/history/test_Vault__Blame.py` — `Test_Vault__Blame`.** Oracle: `git blame --line-porcelain`
mapped through unique commit messages.

| # | Case |
|---|---|
| B1 | Linear history: append, insert at the top, delete, change; every line's commit equals Git's |
| B2 | Rename then edit: lines before the rename are blamed on the original commit with `orig_path` = the old path |
| B3 | A merge: lines from both parents attributed as Git; `--first-parent` as `git blame --first-parent` |
| B4 | A whole-file pass across 50 untouched commits: `stats.commits_visited` shows no diff for them |
| B5 | `-L 3,5`, `-L 3,+2`, `-L 5,-2`, `-L /five/,+1`, two `-L`, an out-of-range `-L` (exit 1, Git's message) |
| B6 | `-w`: a whitespace-only change does not take the blame |
| B7 | Binary refused; `--text` blames it |
| B8 | Shallow clone (`clone --depth 2`): older lines on the boundary commit, `^`, `boundary_reason='shallow'`, note printed |
| B9 | Scoped clone: path outside → exit 1 with the widen hint; inside → normal |
| B10 | Selective clone (`--no-checkout`), remote configured: blobs fetched (`blobs_fetched > 0`), same result as full; `--offline`: `boundary_reason='offline'` |
| B11 | Pack vault with a snapshot index: the plan used (`index_plan_used`), fewer commits visited, same lines |
| B12 | **Lying plan**: a snapshot index rebuilt with `file-commits` omitting one commit that changed the file → the stretch check fails, the walk falls back, lines equal to B11's, note printed |
| B13 | Porcelain output: parsed by a small parser written to Git's documented grammar; every field present; `boundary` lines for `^` commits |
| B14 | JSON round-trip: `Schema__Blame_Result.from_json(r.json()).json() == r.json()` (the CLAUDE.md invariant) |
| B15 | A non-ASCII path (`docs/josé.md`) printed unmangled in all three formats |

**`tests/unit/core/actions/history/test_Vault__Grep.py` — `Test_Vault__Grep`.** Oracle: `git grep` on the same tree,
committed and checked out.

| # | Case |
|---|---|
| G1 | Each flag alone: `-n -c -l -L -i -w -v -F -o -h -H -m 1`, two `-e`; the output lines equal Git's (working copy and `HEAD~1` modes) |
| G2 | Context `-A 1 -B 2 -C 1` including overlapping windows and the `--` separator |
| G3 | Exit codes 0/1/2, and `-q` |
| G4 | Pathspec: prefix, glob, `**`; magic `:(exclude)` refused (exit 2) |
| G5 | Binary: `Binary file x matches`; `-I`; `--text` |
| G6 | `-w` edges: `foo_bar`, `foo-bar`, start and end of line; against Git |
| G7 | Untracked: not searched by default; `--untracked` searches it; ignored files never |
| G8 | Symlink in the working copy is not followed; a FIFO does not block (as the scan tests do) |
| G9 | Selective clone: the not-checked-out count and note; `HEAD` mode searches them with fetch on demand |
| G10 | Scoped clone in rev mode: `outside_scope` counted |
| G11 | Guard: `(a+)+$` refused (exit 2) before any file is read |
| G12 | Non-UTF-8 file: ASCII parts match; output bytes round-trip |
| G13 | Streaming: the first match is printed before the last file is read (a 2,000-file tree with the match in the first file; the reader counter at first output is < 2,000) |
| G14 | JSON schema round-trip |
| G15 | A path holding a newline: quoted as Git quotes it |

**`tests/unit/core/actions/history/test_Vault__Pickaxe.py` — `Test_Vault__Pickaxe`.** Oracle: `git log -S/-G --format=%s`.

| # | Case |
|---|---|
| P1 | `-S` count change vs a moved line (`-S` misses, `-G` matches), against Git |
| P2 | Added and deleted files |
| P3 | `--pickaxe-regex` |
| P4 | `-i` |
| P5 | Merges skipped, and the note |
| P6 | Combined with `--grep`, `--author`, `--since`, `--file` |
| P7 | `-n 2` stops early (`stats` shows fewer commits read than the history) |
| P8 | Pack vault uses the `changes` member (no `diff_trees` call: counted on `Vault__Path_History`) |
| P9 | Shallow note |

**`tests/unit/core/actions/diff/test_Vault__Diff__Pruned.py` — `Test_Vault__Diff__Pruned`.**
- Golden outputs of `show`, `diff A..B`, `log --files/--patch/--json` captured from the current implementation on
  `Vault__Test_Env` fixtures (commit them before step 3). The new implementation must match them exactly, with
  renames off.
- `blobs_read` equals the changed files' sides, not the vault size.

**`tests/unit/core/test_Vault__Regex_Guard.py`**
- The existing `Vault__Log_Filter` guard cases moved here.
- The `Vault__Log_Filter` tests still pass unchanged.

### 9.4 CLI tests

| File | Covers |
|---|---|
| `tests/unit/cli/test_CLI__Blame.py` | Parser, formats, exit codes, notes on stderr |
| `tests/unit/cli/test_CLI__Grep.py` | Top-level and `file grep` both reach `cmd_grep`; arguments after `--`; exit codes through `SystemExit` |
| `tests/unit/cli/test_CLI__History__Renames_Pickaxe.py` | `-M90`, `--no-renames`, `--rename-limit`, `--follow`, the lifted filter refusals and the kept ones |
| `tests/unit/cli/test_CLI__B07__Namespace_Moves.py` | `TOP_LEVEL_COMMANDS` includes `grep` |

### 9.5 Security tests

| File | Covers |
|---|---|
| `tests/security/test_Security__Known_Gaps.py` | New TM-R4x: raw terminal escapes printed by `grep` and `blame` (plain) and escaped in `--json` |
| `tests/unit/core/actions/history/test_Vault__Blame.py` B12 | The lying-plan case. It is a design guard, not a fix of a past finding, so it stays in unit tests and is cited in TM-R42's evidence column. |

### 9.6 Acceptance checklist (implementation and deployment)

**Tests**
- [ ] `pytest tests/unit -n auto` and `pytest tests/security` pass. The Git-oracle tests ran (not skipped) in CI:
      the job log shows their names as passed.
- [ ] `Vault__Log_Filter` tests unchanged and passing after the guard move.
- [ ] Golden tests: `history show / diff / log --files --patch --json` outputs byte-identical to before with
      `--no-renames`.

**Renames**
- [ ] On a scratch vault, `sgit history show` of a commit that moved and edited a file prints
      `similarity index NN%` / `rename from` / `rename to`. `git diff -M` on the same contents gives the same NN ±1.
- [ ] `sgit history log --file docs/new.md --follow` lists the commits before the rename with an `R` row.

**Blame and grep**
- [ ] `sgit history blame <file>` on a 5-commit history equals `git blame` line for line (commit mapping by
      message).
- [ ] `sgit grep -n foo` and `sgit grep -n foo HEAD~1` equal `git grep` output on the same tree. Exit code 1 when
      nothing matches.

**Pickaxe**
- [ ] `sgit history log -S foo --oneline` and `-G foo` list the same commits as Git (by message).

**Partial clones**
- [ ] Shallow clone: blame shows `^` lines and the deepen note. Scoped clone: blame outside refused with the widen
      hint. Selective clone: grep's not-checked-out note.

**Performance**
- [ ] On the 76,000-file vault:
  - `history show` of a 5-file commit under 2 s (was tens of seconds);
  - `history blame` on a file with 40 changes under 5 s, under 1.5 s with the index plan;
  - numbers recorded in the CHANGELOG.
- [ ] `sgit grep x | head -1` returns before the search finishes (streaming).

**Deployment**
- [ ] `sgit help all` lists `grep`. `sgit history --help` lists `blame`.
- [ ] CHANGELOG `[Unreleased]` entry; threat-model rows (TM-R4x new, TM-R42 sentence);
      `sgit-for-git-users` mapping rows for `blame`, `grep`, `log -S/-G`, `--follow`, `-M`.
- [ ] Dev pre-release (`0.x.y.devN`) installed with `pip install --pre sgit-ai` in a clean venv; the checklist's
      CLI items re-run against the installed build.

## 10. Implementation steps (ordered commits)

| # | Commit | Contents | Estimate |
|---|---|---|---|
| 1 | `refactor: Vault__Regex_Guard shared by --grep and the new search commands` | 5.9 guard; `Vault__Log_Filter` delegates; tests moved | 0.25 d |
| 2 | `feat(history): content paths, blob reader, path history` | `Safe_Str__Content_Path`, `Vault__Path_Quote`, `Vault__Blob_Reader`, `Vault__Path_History`; `log_file` on it | 0.5 d |
| 3 | `perf(diff): history show/diff/log --patch read only what changed` | Golden captures first (separate commit), then the pruned diff (5.5) and `Vault__Line_Diff` for hunks | 1.25 d |
| 4 | `feat(diff): rename detection (exact, basename, similarity) in diff, show, log` | `Vault__Renames`, schemas, options, headers, `--stat` scores, JSON `files_renamed`, `--follow` | 1.5 d |
| 5 | `feat(history): sgit history blame` | `Vault__Blame`, `CLI__Blame`, three formats, partial-clone behaviour | 1.5 d |
| 6 | `feat: sgit grep (working copy and revisions)` | `Vault__Grep`, `CLI__Grep`, top-level and `file grep`, Rule 9 edit | 1 d |
| 7 | `feat(history): log -S / -G (pickaxe)` | `Vault__Pickaxe`, dispatch changes | 0.5 d |
| 8 | `perf(pack): blame and --follow take the snapshot index's file-commits as a verified plan; pickaxe takes changes` | 5.6 acceleration, B11–B12 | 0.75 d |
| 9 | `docs: CHANGELOG, threat model, git-users mapping, measurements` | TM rows, numbers on the 76k vault | 0.25 d |
| | **Total** | | **≈ 7.5 days** |

The roadmap's 4–6 days (2.4 + 2.5 + 2.7) did not include step 3 (the pruned diff) or step 8. Step 3 is needed:
blame, renames and pickaxe on a large vault are unusable on top of the current full-decrypt diff. Step 8 can ship
later.

If design 01 lands first with its own line differ, step 3 uses it and `Vault__Line_Diff` is not written.

## 11. Open decisions for Dinis

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | Where `grep` lives (Rule 9) | (a) `sgit grep` top-level + `sgit file grep`; (b) `sgit file grep` only; (c) `sgit history grep` | **(a)**: a daily verb over files, the same pattern as `cat`/`ls`/`write`; one deliberate edit to `TOP_LEVEL_COMMANDS` |
| D2 | Regex dialect | (a) Python `re` for all, `-E`/`-P` accepted as synonyms; (b) emulate Git's default POSIX BRE | **(a)**: BRE emulation is a parser of its own for little gain; documented as a known difference (`\(…\)` in BRE is a group, in ours a literal parenthesis) |
| D3 | `grep` exit codes | (a) Git's: 0 match, 1 none, and 2 for errors (grep(1)); (b) sgit's usual 1 for errors | **(a)**: scripts written for `git grep`/`grep` rely on 1 = no match; errors must differ from that |
| D4 | Renames on by default, and JSON | (a) on by default (Git ≥ 2.9), a renamed file leaves `files_added`/`files_deleted` and appears in `files_renamed`; (b) off by default, `-M` opts in; (c) on, but JSON keeps listing renamed files in added/deleted too | **(a)** with `--no-renames` for the old output. An agent counting `files_added` sees a change, noted in the CHANGELOG. If an existing consumer is known, (c) for one release. |
| D5 | Line diff algorithm | (a) Myers (own, shared with design 01); (b) `difflib` with `autojunk=False` | **(a)**: blame attribution matches Git's on common files; (b) differs on files with many repeated lines |
| D6 | Blaming a binary file | (a) refuse unless `--text`; (b) blame it as Git does | **(a)**: an agent blaming an image gets noise |
| D7 | Grep in a selective working copy | (a) on-disk files only, plus a note pointing at `sgit grep <p> HEAD`; (b) also read the head's blobs for files not checked out | **(a)**: the working copy is what Git's default searches; (b) can fetch gigabytes silently |
| D8 | Blame's author column | (a) branch name from the index, key id fallback; (b) key id always | **(a)**, `-e` for (b) |
| D9 | On-demand fetch default for blame / grep `<rev>` / pickaxe | (a) fetch when a remote is configured, `--offline` to forbid; (b) never fetch, tell the user to `sgit fetch` | **(a)**: what `history show` does today (A3) |
| D10 | Renames in `sgit status` | (a) later, separate item; (b) now | **(a)**: Git shows them for staged changes only; sgit's status would need its own rule |
| D11 | Copy detection (`-C`) | (a) out of scope; (b) include | **(a)** |
| D12 | `blame --ignore-rev` / `--ignore-revs-file` | (a) follow-up (needs Git's "fuzzy" line matching to be useful); (b) include the simple form (skip the commit, pass all its lines to its parent) | **(a)** |
