# Release readiness: the pack-indexes branch (27 Oct 2026)

**Branch:** `claude/charming-babbage-5hzcxq` at `f3c2040`, with `origin/main` merged in (`84d6c23`: only the 0.25.0
release commit; the version file now reads 0.25.0). **Verdict: ready to merge to dev and release as 0.26.0.**

## 1. The independent review of the fix round

A reviewer given the diff of the five fix commits and the original findings, not my conclusions, found nine
things; every one was reproduced by its proof script, then fixed with tests (`7d5ecc2`):

| # | Finding | Severity | Fix |
|---|---|---|---|
| R1 | `checkout --since-pull` took the bytes a `pull --no-checkout` left behind for an edit and never refreshed them (a regression of the fix round) | high | the pull records the hash of the bytes it leaves (`local/stale.json`); exactly those bytes are stale, not an edit |
| R2 | a file write that failed was still recorded, could make `checkout --all` flip to full, and a pull moved its head past it | high | the writer returns what it wrote; failures are reported, block the flip, and stop a pull before its head moves; a clone that cannot write its files is refused |
| R3 | a folder replaced by a file still failed when the folder held an untracked or ignored file | high | the guard refuses before writing anything when a folder or file is in the way |
| R4 | the orphan index sweep could delete a concurrent push's new index | medium | index listings first; an index younger than a day is left alone |
| R5 | each index lookup listed every local index file | medium | one map per reader |
| R6 | a rebuilt checkout record forgot pending deletions silently | low | announced on stderr; an unreadable record is rebuilt too |
| R7 | a pack-store handle closed in use could corrupt the reader counts | low | closed by its last reader |
| R8 | `history log` listings retried 14 s on a 5xx | low | fail fast; commits with no index remembered |
| R9 | a tree entry without a content hash always read as dirty in checkout | low | compared with the decrypted blob |

## 2. The build agent's round-2 review

It re-checked B1, B2, M1, M2, M5, M6, F3, C1, L1 and L2 on its own vault and approved the merge. Its four notes:
N1 (a `--no-checkout` or bare pack clone checked nothing) and N3 (the inflate cap, now 256 MB) are fixed in
`abce420`; N2 (the vault's first commit always walked by `history log`) is fixed in `7d5ecc2` and `f3c2040`;
N4 needs nothing.

## 3. Measured: 76,000 files in 58,553 folders, in-memory host, this machine (4 cores)

| Flow | 0.25.0 (`c3f410b`) | branch before the fixes (`a9f24d8`) | **this branch** |
|---|---|---|---|
| first push (snapshot) | 47 s | 83 s | 82–84 s |
| full clone | 117 s | 76 s | **61 s** |
| `clone --no-checkout` | n/a | 61 s | **28 s** |
| `clone --pack-store` | n/a | 62 s | **26 s** |
| `clone --path raw/c09` (1,520 files) | 36 s | 2.8 s | **2.8 s** |
| push, 300-file pass | 12.5 s | 14.5 s | **11.6–11.8 s** |
| push, 5-file commit | 6.2 s | 7.4 s | **4.5–5.2 s** |
| pull of both, full clone | 81 s | 6.3 s | **6.6 s** |
| `history log`, 4 commits | 3.2 s | 3.2 s | **0.45 s** |
| `history log` on a fresh clone after compaction | 6.1 s | 3.0 s | **1.1 s** (0.5 s again) |
| compaction | 58 s | 103 s | 95–109 s |

The other flows measured in the same runs:

| Flow | 0.25.0 | before the fixes | this branch |
|---|---|---|---|
| first commit, 76,000 files | 55.6–55.8 s | 61.5 s | 50.1–69.0 s (same code path; machine noise) |
| commit, 300-file pass | 6.3–6.8 s | 7.4 s | 6.2–7.2 s |
| commit, 5 files | 3.8 s | 4.4 s | 3.6–4.2 s |
| pull, `--no-checkout` clone | n/a | 3.8 s | 3.6–4.2 s |
| pull, `--pack-store` clone | n/a | 6.8 s | 6.6–7.3 s |
| full clone after compaction | 100.6–112.6 s | 70.5 s | 40.4–57.1 s |
| host after the first push | 88.3 MB | 119.9 MB | 119.9 MB (of which index packs 31.6 MB) |
| `.sg_vault` of a full clone | 68.9 MB | | 121.8 MB (the local index packs and flat cache) |
| `.sg_vault` of a `--pack-store` clone | n/a | | 174.4 MB |

Requests to the host: a clone 5 on 0.25.0, 7 on this branch (the index listings); a push 13 against 15 (the
index pack); compaction 26 against 46–71 (index packs archived and swept). The scoped clone of `raw/c09` took the
whole 88 MB pack in 5 requests on 0.25.0, and 12.5 MB in 24 ranged requests here. The 0.25.0 pull's 81–89 s is
the walk of every tree that the newsroom field-report fixes on this branch removed (`[Unreleased]`, "Fixed — from
the newsroom's first morning on 0.25.0").

**How these were measured.** One synthetic vault per run: `raw/c00..c49/s0..s9/d000..d115`, one text file of
about 1 KB in each of the 58,000 leaf folders plus a second in 18,000 of them (76,000 files, 58,553 folders),
built and pushed by the build under test. The in-memory host and every client run in one fresh process per
build, with the process flat cache cleared before each flow; disk caches are per clone, as in real use. Builds:
`c3f410b` (what went into 0.25.0) and `a9f24d8` (the branch the build agent first reviewed), each from its own
worktree; this branch at `84d6c23`, `abce420` and, for the history-log-after-compaction row, `f3c2040`, which is
why its cells give ranges. Where a build was run twice, both values are given. Same machine throughout (4 cores),
nothing else running. The build agent's numbers on its own vault agree in direction and roughly in size (its full
clone 84.0 s on its base against 48.3 s on this branch).

Two costs remain, both known and accepted: the first push and each compaction build the snapshot index (+35–50 s
on this vault, 31.6 MB beside an 88 MB pack; L4, deferred to Phase 4 with your decision). Everything else is
faster than 0.25.0, most of it by a wide margin.

## 4. Evidence

- `tests/unit` + `tests/security`: **4,728 passed**. `tests/integration` (real server, 3.12 venv): 75 passed, 1 skipped.
- Cross-version harness, released `sgit-ai==0.25.0` and this build against the real test server: **ALL COMMANDS OK**,
  trees equal at every hop.
- The reviewer's proof scripts: all pass except three that encode the old behaviour or the accepted R6 limit.

## 5. Before tagging

- Merge to dev (yours); the pipeline sets the version.
- Read the `[Unreleased]` CHANGELOG once as a release note: it is long, and the "Fixed — from the reviews" section
  may want trimming for users.
- Known and documented: `history log` makes up to two listings per new set of commits when a remote is configured;
  a `--pack-store` clone must not be opened with 0.25.0; the snapshot index size (L4).
