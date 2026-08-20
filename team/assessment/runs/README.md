# Assessment Runs — History

One folder per run: `YYYY/MM-DD__<runner>/` (e.g. `2026/09-01__claude/`,
`2026/09-01__codex/`). Each contains the seven role reports
(`01__security.md` … `07__ux.md`) and the conductor's consolidated
`00__assessment-pack.md`.

This history is load-bearing, not an archive: every run reads the most recent
folders here so findings are diffed, not rediscovered, and so persisting issues
accumulate visible age. Runs are committed via their assessment PR — merging the
PR is what makes a run part of the record.

The conductor's `00__assessment-pack.md` is the entry point for any single run;
`../KNOWN-ISSUES.md` is the always-current cross-run register.
