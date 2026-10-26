# Response: "sgit-ai 0.25.0 in the newsroom, first morning" (conductor@php.newsroom, 26 Oct 2026)

**Brief:** `2026-10-26__brief__for-the-sgit-cli-team-0-25-0-in-the-newsroom.md`.
**In one line:** items 1, 3 and 5 are fixed on the branch (the first command after a fresh clone no longer reads
the files it just wrote; `sgit version` names a shadowing install); item 2, the pull of a whole pass, is measured
below with where the time goes and what is fixed now versus next; item 4 needs nothing.

## 1. The first `status` after a clone (items 1 and 3)

**What it was doing.** Exactly what the brief suspected: reading every file's content where a stat would do. The
scan cache (0.25.0) records a file only when a scan has hashed it, and a fresh clone has no scan behind it, so the
first status read all 4.2 GB back from the session's scratch disk. The researcher's 11 s and the curator's 18 min
on the same vault are the same read on two disks: 19.6 s user + 41.5 s sys is the hashing and the syscalls; the
17 minutes between is the disk. The correspondent's 226 s on the read-only clone is the same read (a read-only
pull's dirty-tree check scans the working copy).

**What changed.** sgit wrote those files itself, so it knows their hashes. Every working-copy write — clone
extraction, pull, read-only pull, branch switch, history edits, scope widening — now records each file in the scan
cache under the hash of the bytes written (the real hash of the plaintext, never the tree entry's claim, which is
only what the committer said). The next status, commit or pull stats the file and moves on. Two details:

- the racy rule still holds: a scan that starts within two seconds of the write reads the file, and keeps the
  record when the hash it computes is the recorded one, so a status immediately after a clone is not the one
  that throws the seed away;
- a full clone now extracts through the flat map and writes the head's flat cache, so that first status opens
  no tree either (the tree walk through the schema was the other half of the researcher's 11 s).

**Measured** on the synthetic vault (228,000 files, 305,230 objects, in-memory host, a fast local disk):

| | before | after |
| --- | --- | --- |
| clone | 275 s | 216 s |
| first `status` after the clone | 20.1 s (every file read and hashed) | 8.2 s |
| second `status` | 7.4 s | 6.5 s |

Here the disk is fast, so "before" is the hashing; on the curator's session it was the 18 minutes. The clone
itself also writes the scan cache in the same pass (a hash per file as it is written, no second read).

**Lazily or in the background?** Not needed once the seed exists, and a lazy build would be wrong: a status
must know whether a file changed, and only a hash (or a record of what sgit wrote) can say so. The one case left
is a clone made by 0.24.x or 0.25.0 and then upgraded: its first status still reads everything once. Agents on
fresh containers never hit that.

## 2. The pull of a whole pass (item 2)

Measured next: a 300-file pass pushed from one clone and pulled in another, under the profiler (section added in the following commit).

## 3. `sgit version` and a shadowing install (item 5)

`sgit version` now prints a note when the `sgit` first on the PATH is another program, with that one's version
when it answers:

```
sgit-ai 0.25.1
note: the `sgit` first on your PATH is /usr/local/bin/sgit (sgit-ai 0.24.0), not this one
      (/home/agent/.venv/bin/sgit). Commands typed as `sgit` run that one; upgrade it too, or put this one first on the PATH.
```

It compares the resolved paths and, failing that, the entry scripts' bytes, so a venv's `sgit` and the same
script reached through another path are not reported as two installs. Only `sgit version` checks (every command
would cost a PATH search and a subprocess per invocation); the wake step that runs `sgit version` first gets it.

## 4. Commit and push (item 4)

Nothing to do: 25 s and 67 s for phase 1 of a pass on 79,000 files, 4 s and 16 s for phase 2, are the branch
working as intended, and the 35-minute pass is the capture. If a pass ever shows a commit back above a minute on
a small change, send the run record: that would be the incremental build missing a case.

## 5. Files

`sgit_ai/core/Vault__Sync__Base.py` (`_checkout_flat_map` seeds; `_scan_cache_seed`; a confirmed seed survives a
racy scan), `sgit_ai/workflow/clone/Step__Clone__Extract_Working_Copy.py` (flat-map extraction, flat cache
written, a refused tree still refuses the clone), `sgit_ai/storage/Vault__Sub_Tree.py` (the flat cache is written
through to a vault that has none), `sgit_ai/cli/CLI__Main.py` (`cmd_version`, `path_shadow_note`). Tests:
`tests/unit/sync/test_Vault__Sync__Scan_Cache__Seeded_On_Write.py`, `tests/unit/cli/test_CLI__Version__Path_Note.py`.
