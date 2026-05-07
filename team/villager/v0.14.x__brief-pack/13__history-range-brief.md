# Brief 13 — Commit range syntax on `history log` and `history diff`

**Date:** 2026-05-07
**Audience:** SGit Dev Agent
**Scheduling:** independent — can land any time after brief 12. Estimated effort: ~½ day.
**Author:** Villager orchestrator (Opus)

---

## 1. Why this exists

Today `sgit history log` walks all commits from HEAD with no way to bound the range. Users (and especially **conductor-style agents** that produce periodic vault-activity reports) need to ask:

> "What happened in this vault between commit `A` and commit `B`?"

That single question requires three sub-operations today, each a separate command and none of them range-aware:

1. List the commits in the range.
2. For each commit, show the files it changed.
3. For each commit, show the diff.

The workaround is a shell loop calling `history log` and `history show <id>` per commit. It works but is awkward, slow at scale, and unfit for an automated agent that needs to consume structured output.

This brief adds native range syntax to `history log` and `history diff`, plus a JSON output mode so agents can parse the result programmatically.

The motivating use case: a **conductor agent** producing automated vault-activity reports. A single command should give it everything it needs to report on a time window.

---

## 2. CLI surface

### 2a. `sgit history log` gains range syntax

```
sgit history log [<from>..<to>]
    [<directory>]
    [--oneline]
    [--graph]
    [--files]                 # NEW: include files-changed per commit
    [--patch]                 # NEW: include full diff per commit
    [--json]                  # NEW: structured output for agents
    [--file <path>]           # existing: filter by file (kept)
```

Range forms accepted:
- `<from>..<to>` — explicit two-sided range; commits reachable from `<to>` but NOT reachable from `<from>` (matches git's `..` semantics: `<from>` is exclusive).
- `<from>..` — from `<from>` (exclusive) to current HEAD.
- `..<to>` — from the root commit to `<to>` (inclusive).
- (no range) — existing behaviour: walk from HEAD.

Order: oldest-first when a range is supplied (forward chronological order is what reports want). Existing reverse-chronological behaviour is preserved when no range is given (matches today's `history log`).

Modes (mutually compatible):
- `--oneline` — one line per commit: `<short-id> <date> <message>`.
- `--files` — for each commit, include the list of files added/modified/deleted. No content diff.
- `--patch` — for each commit, include the full content diff (calls `Vault__Diff.show_commit` per commit).
- `--json` — emits a structured array (see §3).

### 2b. `sgit history diff` accepts the same range syntax

```
sgit history diff [<from>..<to>]
    [<directory>]
    [--files-only]
    [--json]                  # NEW: structured output
```

`<from>..<to>` is equivalent to `--commit <from> --commit2 <to>` (existing flag-based syntax stays as an alias for backwards compat — users can use either). The diff is the **aggregate net difference** between the two trees, not per-commit.

For per-commit diffs across a range, use `history log <from>..<to> --patch`.

---

## 3. JSON output format (the conductor-agent path)

When `--json` is set, output is a single JSON document parseable by an agent. Schema for `history log <from>..<to> --json --files --patch`:

```json
{
  "schema":      "history-log/1",
  "from_commit": "obj-cas-imm-aaa...",
  "to_commit":   "obj-cas-imm-zzz...",
  "commit_count": 5,
  "commits": [
    {
      "commit_id":     "obj-cas-imm-bbb...",
      "parent_ids":    ["obj-cas-imm-aaa..."],
      "timestamp_ms":  1747088400000,
      "timestamp_iso": "2026-05-12T10:00:00Z",
      "message":       "Add foo.py and update README",
      "branch_id":     "...",
      "files_added":    ["src/foo.py"],
      "files_modified": ["README.md"],
      "files_deleted":  [],
      "patch": "...optional, only when --patch is set..."
    },
    ...
  ]
}
```

Type_Safe schemas:
- `Schema__History_Log_Result` (top-level)
- `Schema__History_Log_Commit_Entry` (per-commit record)

Both must pass round-trip: `assert cls.from_json(obj.json()).json() == obj.json()`.

For `history diff <from>..<to> --json`:

```json
{
  "schema":         "history-diff/1",
  "from_commit":    "obj-cas-imm-aaa...",
  "to_commit":      "obj-cas-imm-zzz...",
  "files_added":    ["src/new.py"],
  "files_modified": [{"path": "src/foo.py", "lines_added": 10, "lines_removed": 4}],
  "files_deleted":  ["old.py"],
  "patch": "...optional, only when not --files-only..."
}
```

The conductor agent calls `sgit history log <from>..<to> --files --json` once, parses the output, and has everything needed to produce a report.

---

## 4. Implementation outline

### 4a. New method on `Vault__Diff`

`sgit_ai/core/actions/diff/Vault__Diff.py` (extending the existing class):

```python
def commits_in_range(self, directory: str, from_commit: str = '',
                     to_commit: str = '') -> list:
    """Return commit IDs in <from>..<to> range, oldest-first.

    <from> is exclusive; <to> is inclusive. Empty <to> means HEAD.
    Empty <from> means walk to root.
    """
    # 1. Resolve to_commit (default = HEAD)
    # 2. Walk parents from to_commit, collecting IDs
    # 3. If from_commit is set: stop at from_commit (exclusive)
    #    Set membership check; raise if from_commit isn't an ancestor of to_commit
    # 4. Reverse to oldest-first
    return [...]
```

Plus a helper that combines per-commit info:

```python
def log_range_with_details(self, directory: str, from_commit: str,
                           to_commit: str, include_files: bool = False,
                           include_patch: bool = False) -> Schema__History_Log_Result:
    """High-level: returns a fully-populated Schema__History_Log_Result.
    Used by the JSON output path AND by the human-readable --files/--patch path."""
    ...
```

### 4b. Range-syntax parsing

Small helper in `sgit_ai/cli/_helpers.py` (new file or existing):

```python
def parse_commit_range(arg: str) -> tuple[str, str]:
    """Parse <from>..<to>, <from>.., ..<to>, or '' (no range).

    Returns (from_commit, to_commit) as strings.
    Empty string for either side means open-ended.
    Raises ValueError on malformed input.
    """
    if '..' not in arg:
        return ('', '')   # not a range — treat as no-range case
    parts = arg.split('..', 1)
    return (parts[0], parts[1])
```

Used by both `cmd_log` and `cmd_diff`. Add a small validation: if `<from>` doesn't resolve to a commit, error with a clear message naming the prefix.

### 4c. Wiring in CLI handlers

`CLI__Diff.cmd_log`: detect range syntax in the first positional arg (if it contains `..`); parse; route to `log_range_with_details` if range, otherwise existing path. Render output based on `--oneline` / `--files` / `--patch` / `--json` flags.

`CLI__Diff.cmd_diff`: accept range syntax in addition to `--commit` / `--commit2`. If both are provided, range syntax wins with a one-line note.

### 4d. Schemas

New files:

```
sgit_ai/schemas/history/
├── __init__.py
├── Schema__History_Log_Result.py
├── Schema__History_Log_Commit_Entry.py
└── Schema__History_Diff_Result.py
```

All Type_Safe with round-trip enforced. Use existing `Safe_Str__Commit_Id`, `Safe_UInt__Timestamp`, `Safe_Str__ISO_Timestamp` (per the timestamp-fields debrief — `timestamp_ms` is integer, `timestamp_iso` is string ISO 8601 for the human-friendly field).

---

## 5. Tests

In `tests/unit/core/actions/diff/test_Vault__Diff__Range.py`:

1. `test_commits_in_range_walks_oldest_first` — vault with 5 commits A→B→C→D→E; `commits_in_range(B, E)` returns `[C, D, E]` (B exclusive, oldest-first).
2. `test_commits_in_range_inclusive_to` — `to_commit` is included in the result.
3. `test_commits_in_range_exclusive_from` — `from_commit` is NOT included.
4. `test_commits_in_range_open_ended_to_walks_to_head` — `to_commit=''` → walks to HEAD.
5. `test_commits_in_range_open_ended_from_walks_to_root` — `from_commit=''` → walks to root.
6. `test_commits_in_range_from_not_ancestor_raises` — `from_commit` is not an ancestor of `to_commit`; raises clear error.
7. `test_commits_in_range_full_history_when_no_range` — empty range returns full chain.

In `tests/unit/cli/test_CLI__History__Log__Range.py`:

8. `test_log_with_range_oneline` — produces oldest-first one-liner output for the range.
9. `test_log_with_range_files_includes_per_commit_files` — `--files` mode lists added/modified/deleted per commit.
10. `test_log_with_range_patch_includes_full_diff` — `--patch` mode includes content diff per commit.
11. `test_log_with_range_json_round_trips` — `--json` output parses through `Schema__History_Log_Result.from_json` and round-trips.
12. `test_log_open_ended_range_to_head` — `<from>..` works.
13. `test_log_open_ended_range_from_root` — `..<to>` works.

In `tests/unit/cli/test_CLI__History__Diff__Range.py`:

14. `test_diff_accepts_range_syntax` — `history diff A..B` is equivalent to `--commit A --commit2 B`.
15. `test_diff_json_round_trips` — `--json` output parses through `Schema__History_Diff_Result`.

In `tests/unit/schemas/history/test_Schema__History_Log_Result.py`:

16. `test_round_trip` — schema round-trip invariant.
17. `test_round_trip_with_optional_patch` — same with `patch` field set.

---

## 6. Out of scope

- **`<from>...<to>` (three-dot, symmetric difference)** — git's "merge base" semantics. Defer; not needed for the conductor use case.
- **`HEAD~3` / `<branch>~5` / `^` syntax** — relative refs. Useful but separate; v1 just supports explicit commit IDs (full or unique prefix).
- **Filtering by author / date** — `--author <name>`, `--since 2026-05-01`. Defer until the conductor agent actually needs them.
- **Topological sort variations** — for v1, the natural parent-walk order (which matches git's default for linear histories) is enough. Merge commits in non-linear histories will work but may surface in either parent's chain; document this caveat.

---

## 7. Why this is low-risk

- **Pure addition.** No existing command behaviour changes. `history log` without range arg behaves exactly as today.
- **Reuses existing primitives.** `commits_in_range` walks via the existing commit-load logic; per-commit details come from the existing `show_commit` method.
- **Small surface.** ~150 LOC of new code + 17 tests.
- **Independent from all other v0.14.x briefs.** Can land any time after brief 12; no dependencies.

---

## 8. Verification checklist

When done:

- All 17 new tests pass.
- `sgit history log A..B` lists commits in the range, oldest-first.
- `sgit history log A..B --files` shows per-commit files changed.
- `sgit history log A..B --patch` shows per-commit full diff.
- `sgit history log A..B --files --json` produces a `Schema__History_Log_Result` JSON document parseable by an external agent.
- `sgit history diff A..B` works as a synonym for `--commit A --commit2 B`.
- Open-ended ranges (`A..` and `..B`) work.
- KNOWN_VIOLATIONS unchanged.

Estimated effort: ~½ day total (range parser + `commits_in_range` ~1.5h, schemas ~1h, CLI wiring ~1h, tests ~2h, doc/help-text ~30min).

---

## 9. Conductor-agent example (for context)

Once this lands, a conductor agent producing a daily activity report runs:

```bash
LAST_REPORT_COMMIT=$(cat .conductor/last-report-commit.txt)
CURRENT_HEAD=$(sgit history log --oneline | head -1 | cut -d' ' -f1)

sgit history log "$LAST_REPORT_COMMIT..$CURRENT_HEAD" --files --json > /tmp/activity.json

# Agent parses /tmp/activity.json and produces:
# - Total commits in window
# - Files most-touched
# - Per-commit narrative
# - Day-by-day activity histogram
# - File-level change summary

echo "$CURRENT_HEAD" > .conductor/last-report-commit.txt
```

That's the entire vault-side surface the conductor needs. Single command, structured output, no shell loops, no per-commit API thrashing.
