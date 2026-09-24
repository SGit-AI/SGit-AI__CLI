# 05. The daily run

What a session does each day, once v0.1 exists. Written so that a session with no memory of the last one can do it.

1. **Fetch.** `python3 tools/fetch_sources.py`. It overwrites `sources/sites/` and updates `manifest.json`. Commit the snapshot on its own: the git diff of that commit *is* the day's change set.
2. **Diff.** Compare today's manifest with the last committed one: new, changed and removed files per site. If nothing changed anywhere, stop: no edition today. Commit nothing else.
3. **Librarian.** Read every changed file. Write `data/changes/YYYY-MM-DD.json`; update the index, concepts and vaults.
4. **Journalist.** Write the edition, and a story for anything that deserves one.
5. **Historian.** On a day with a real moment, a short perspective piece. Every day, add any correction or rule from the sites' version logs to `history/lessons.md`, and any decision to `history/decisions.md`.
6. **Guest desks.** Scan the day's changes against the whole index for cross-pollination. Write a signal only when both sides are cited.
7. **Loose ends.** Add new ones; close ones the day's changes resolved, citing the change.
8. **Build and validate.** `python3 tools/build.py && python3 tools/validate.py`.
9. **Commit and push** with a message naming the day and the counts.

## Later, when v0.1 has proved itself

- **Read git, not only pages.** Most sites have public repos with version logs; commit messages and diffs are richer than page snapshots.
- **Run on a schedule**, once a day, as a Routine.
- **Send signals where they belong**: as a brief in the receiving project's repo, or into a vault through an append lane.
- **The newsroom's own memory in a vault**, so its desks can hand work to each other across sessions.
- **More desks**: Architect and Developer as regular desks once the signals prove useful.
