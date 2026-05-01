# Brief 17 — Schema: extend `Schema__Local_Config`

**Owner role:** **Villager Architect** (design) + **Villager Dev** (implementation)
**Status:** Ready to execute.
**Prerequisites:** Recommended after briefs 15 + 16 land for naming
consistency.
**Estimated effort:** ~1.5 hours
**Touches:** existing schema in `sgit_ai/schemas/`, callers, tests.

---

## Why this brief exists

Architect finding 05 found that `Schema__Local_Config` declares one
field (`my_branch_id`) but the on-disk file accumulates four:
`my_branch_id`, `mode`, `edit_token`, `sparse`. The schema no longer
tells the truth about the file. Type_Safe rule 1 violated by the
implementation, even though no Type_Safe class declares a raw
primitive — the field set is just incomplete.

The fix: extend the schema to declare the full current field set. Use
the loose-on-read tolerance from brief 16 (per Dinis decision 2).

---

## Required reading

1. This brief.
2. `team/villager/architect/v0.10.30/05__type-safe-hygiene-on-additions.md`.
3. `team/villager/dev/v0.10.30/10__state-files-schema.md`.
4. The existing `Schema__Local_Config` source.
5. Audit-grep for what's actually written to `local_config.json`:
   ```
   grep -rn 'local_config\|Local_Config' sgit_ai/sync/
   ```
   Identify all fields written today, with file:line references.

---

## Scope

**In scope:**
- Extend `Schema__Local_Config` to include all fields actually written:
  - `my_branch_id` (existing)
  - `mode` (use the same `Enum__Clone_Mode` from brief 16 if applicable
    — coordinate with the Architect to decide whether `mode` is a
    `clone_mode.json` concept or a `local_config.json` concept; do not
    duplicate)
  - `edit_token` — Safe_* type, mask in `__repr__` if it's
    sensitive
  - `sparse` — boolean (use `Safe_Bool` if the project has one;
    otherwise check whether plain `bool` is allowed for Type_Safe
    classes — per CLAUDE.md, raw primitives are NOT allowed; if
    `Safe_Bool` does not exist, define it)
- Loose-on-read tolerance for legacy files that have only
  `my_branch_id` (per Dinis decision: loose).
- Round-trip invariant test for the new field set.

**Out of scope:**
- Splitting `local_config.json` into multiple files.
- Migration to a different file format.

**Hard rules:**
- Same Type_Safe rules as briefs 15 + 16.
- Loose-on-read tolerance — old files with only `my_branch_id` must
  still load.
- No new mocks.

---

## Acceptance criteria

- [ ] `Schema__Local_Config` declares all fields actually written.
- [ ] Loose-on-read tolerance for legacy single-field files.
- [ ] Round-trip invariant test on the full field set.
- [ ] All call sites refactored (no remaining `dict`-style reads of
      `local_config.json`).
- [ ] Suite ≥ 2,105 passing, coverage ≥ 86%.
- [ ] No new mocks.
- [ ] No raw primitives in the schema.
- [ ] Coordination with brief 16 if `mode` is duplicated — pick one
      home, document the choice.

---

## Deliverables

1. Extended schema source.
2. New Safe_* types if needed (`Safe_Str__Edit_Token`, `Safe_Bool`).
3. Refactored callers.
4. Test additions.
5. Closeout entry on Architect finding 05.

Commit message:
```
refactor: extend Schema__Local_Config to full field set

Closes Architect finding 05 + Dev finding 10 (local_config.json side).
Schema previously declared only my_branch_id; on-disk file has
my_branch_id + mode + edit_token + sparse. Schema now declares all
four with Safe_* types. Loose-on-read tolerance preserves
backwards compatibility with legacy single-field files (per next-
phase-plan decision 2).

https://claude.ai/code/session_<id>
```

---

## When done

Return a ≤ 200-word summary:
1. Field list added.
2. Safe_* types defined (which were new vs reused).
3. mode-field home decision (this schema vs Schema__Clone_Mode).
4. Test count.
5. Coverage delta.
