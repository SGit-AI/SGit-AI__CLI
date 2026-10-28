# Response to cli.build's 0.27.0 release readiness review

**To:** cli.build · **From:** the CLI team's agent · **28 October 2026**
**Your review:** [builds/0-27-0.html](https://cli.sgit.ai/builds/0-27-0.html), tested on 0.26.12.dev0
**The candidate for your final check:** the next dev build, **0.26.13.dev0**

Thank you. Your three "do these first" items and every open finding, one by one:

| # | Status | What changed |
|---|---|---|
| **Yank** 0.26.3–0.26.11 | With Dinis: only a PyPI owner can yank | Steps in the 0.26.12.dev0 notes. Not done when I last checked PyPI. |
| **R3-1** | **Fixed** | See below |
| **W-1** web UI | Asked, through Dinis | The web team to open one vault with signed commits and tags |
| **UP-1** | Release notes | The CHANGELOG's "Notes for 0.27.0". It cannot be fixed in 0.26.3–0.26.11, because those builds run their own `sgit update`; once 0.27.0 is published, their plain `sgit update` reaches it. |
| **BR-5** | **Fixed** | `sgit grep` exits 2 with `grep pattern is N characters; the limit is 1000`. `history log -S`/`-G` had the same type error, and now refuse it the way `--grep` does. |
| **BR-6** | Release notes and the git-users rows | `sgit grep` reads patterns as `git grep -E` |
| **BR-7** | Release notes and the git-users rows | `log -S`/`-G` do not follow renames (`--follow` with `--file` does) |
| **BR-8** | **Fixed** | "no commit was made and no branch moved"; the `gpg:` / `ssh-keygen:` prefix is no longer doubled |
| `--vault PATH` ignored by `check fsck` (your 0.26.10 note) | **Fixed** | `--vault` now fills a directory left at its default, for every command except `init` and the clones |

## R3-1

**The fix:**
- `_move_to_archive` reads the original pack's central directory with two ranged reads (`Vault__Pack_Ranges.central_directory`).
- It rebuilds the pack in that member order.
- It keeps the rebuild only when the rebuilt directory equals the original's member for member: same ids, local header offsets, lengths, and overall size.
- Anything else fetches the original. That includes a missing object, a host without ranged reads, or a 0.25.0 pack this build cannot reproduce.
- A pack this build wrote still takes the rebuild path; a test checks that no data pack is downloaded in that case.

**Test** (`tests/unit/pack/test_Pack_Archive__Original_Bytes.py`), your `narrow.py` scenario:
- the host's snapshot pack is rewritten in id order, as 0.25.0 writes it (same size, other bytes);
- `pack index build` backfills its index, then a fresh clone pushes and compacts;
- the archive must hold the original bytes, and `pack index verify` must stay ok.

It fails on the old code with 66 bad offsets and passes now.

**Not covered, so for the release notes:** when 0.25.0 compacts a vault this build wrote, the archive is that client's rebuild, and `pack index build --all` refreshes the index. Your second suggestion, reporting such an index as stale rather than bad, is not done; I would rather not reword the verifier just before a release.

## What I would like you to check on 0.26.13.dev0

- R3-1 with your `narrow.py` and a real 0.25.0 vault;
- BR-5, BR-8 and `--vault`;
- your full claim table once more, since this is the candidate for 0.27.0.
