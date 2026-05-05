# Brief v05 — Activity Timeline

**Owner:** **Villager Dev**
**Status:** BLOCKED until v01 lands.
**Estimated effort:** ~1 day
**Touches:** `sgit_visual/analyses/Activity_Timeline.py`, `Renderer__Activity_Timeline__CLI.py`, JSON renderer, tests.

---

## Why this brief exists

Per D3 §"Activity timeline": a per-day commits-per-author sparkline + top-authors table. Useful for:
- Multi-agent vaults (the case-study has 4 agents collaborating).
- Activity audits (when did this vault last get pushed to?).
- Onboarding a new team member to a vault ("who's been working on this?").

Reuses `Vault__Local__Commits` data source from v02 — no new data source.

---

## Required reading

1. This brief.
2. `design__03__cli-visual-vocabulary.md` §"Activity timeline" (the sparkline + table example).
3. v02's `Vault__Local__Commits` data source.

---

## Scope

### Data source: reuse `Vault__Local__Commits`

No new data source. The commits + authors + timestamps are in `Schema__Vault__Commits` from v02.

### Analysis: `Activity_Timeline`

Bins commits per day per author. Output:

```python
class Schema__Activity_Timeline(Type_Safe):
    window_days     : Safe_UInt
    bins            : list[Schema__Activity_Bin]   # one per day in window
    by_author       : list[Schema__Author_Activity]   # sorted by recent activity
    total_commits   : Safe_UInt

class Schema__Activity_Bin(Type_Safe):
    date            : Safe_Str__ISO_Date
    commits         : Safe_UInt
    by_author       : dict[Safe_Str__Author, Safe_UInt]   # commits per author this day

class Schema__Author_Activity(Type_Safe):
    author          : Safe_Str__Author
    commits_in_window : Safe_UInt
    last_commit_ms  : Safe_UInt
    last_commit_age : Safe_Str__Plain_Text   # "2h ago", "3d ago"
```

### Renderer (CLI)

Sparkline (unicode block characters: `▁ ▂ ▃ ▄ ▅ ▆ ▇ █`) + author table per D3:

```
Activity (last 30 days)
30 ┤                          ╷
   │                          │  ╷
   │      ╷       ╷           │  │  ╷
   │  ╷   │   ╷   │   ╷       │  │  │  ╷
 0 ┴──┴───┴───┴───┴───┴───┴───┴──┴──┴──┴───
   1   5   10   15   20   25   30
                                                     (days ago)

Top authors
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
┃ Author           ┃  Commits  ┃ Last commit         ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
│ alice@team.dev   │       17  │ 2h ago              │
│ bob@team.dev     │        9  │ 3d ago              │
│ claude@anthropic │        4  │ 1d ago              │
│ dinis@team.dev   │       12  │ 5h ago              │
└──────────────────┴───────────┴─────────────────────┘
```

Sparkline scales: max bin → `█`, zero bin → ` ` (blank).

### JSON Renderer

Outputs `Schema__Activity_Timeline.json()`.

### CLI: `sgit show activity [--days <N>] [--author <pattern>] [--json] [--no-color]`

- `--days` window size (default 30).
- `--author` filter to single author or glob.

### Tests

- Single-author vault shows correct table + sparkline.
- Multi-author vault sorts authors by recent activity.
- Empty window shows zero-row sparkline + empty table.
- `--days 7` vs `--days 90` produce different windows.
- `--json` round-trip.
- "X ago" formatter handles seconds / minutes / hours / days / weeks.

---

## Hard rules

- **Type_Safe** for the schema family.
- **No mocks** — synthetic vault with seeded commit timestamps.
- **Sparkline width** adapts to terminal width.
- Coverage non-negative.

---

## Acceptance criteria

- [ ] `Activity_Timeline` analysis ships.
- [ ] CLI renders sparkline + author table correctly.
- [ ] Top-authors sorted by `last_commit_ms` descending (most-recent first).
- [ ] At least 6 tests.
- [ ] `--json` round-trip holds.
- [ ] "X ago" formatter unit-tested across all units.

---

## When done

Return a ≤ 200-word summary:
1. Tests added.
2. Sample CLI render (paste).
3. Sparkline scaling correctness on a 4-author 30-commit fixture.
4. Coverage delta.
