# Brief 16 — Schema: `Schema__Clone_Mode` for clone_mode.json

**Owner role:** **Villager Architect** (design + naming) + **Villager Dev** (implementation)
**Status:** Ready to execute. Recommended after brief 13 lands (the
write-file guard already depends on `clone_mode.json` shape).
**Prerequisites:** Brief 13 soft-recommended.
**Estimated effort:** ~2 hours
**Touches:** new schema in `sgit_ai/schemas/`, callers in
`sgit_ai/sync/Vault__Sync.py` (~lines 1550–1655), tests.

---

## Why this brief exists

Same root cause as brief 15: Architect finding 05 + Dev finding 10 +
AppSec mutation matrix M8 (overlap). `clone_mode.json` has no Type_Safe
schema. It currently holds at minimum:
- `mode` ("full" | "sparse" | "read-only" | similar)
- `read_key` (hex; intentional per Dinis — accepted-risk per AppSec F07)
- possibly other fields the debriefs don't fully document

Without a schema, `load_clone_mode` returns whatever dict is on disk,
and the only validation is implicit (callers do `if d.get('mode') ==
'full': ...`). Brief 13's write-file guard partially mitigates the
fail-open behaviour; brief 16 closes it structurally.

---

## Required reading

1. This brief.
2. `team/villager/architect/v0.10.30/05__type-safe-hygiene-on-additions.md`.
3. `team/villager/dev/v0.10.30/10__state-files-schema.md`.
4. `team/villager/appsec/v0.10.30/F07__clone-mode-plaintext-keys.md` —
   the read_key field is intentional.
5. `sgit_ai/sync/Vault__Sync.py:1550, 1654` — clone_mode.json write sites.
6. `team/humans/dinis_cruz/claude-code-web/05/01/v0.10.30/01__sparse-clone-on-demand-fetch.md`.
7. `CLAUDE.md` schema pattern + Safe_* type pattern.

---

## Scope

**In scope:**
- Define `Schema__Clone_Mode` with all fields actually written. Cite
  source lines.
- Use `Enum__Clone_Mode` (Type_Safe enum) for the `mode` field —
  enumerate valid values rather than `Safe_Str`. Per Dev finding 10
  question.
- Use `Safe_Str__Hex_Key` (or define if missing) for `read_key`.
- Refactor `load_clone_mode` and the two write sites to use the schema.
- Round-trip invariant test.
- Validation tests:
  - Unknown `mode` value fails to load (does not silently treat as full).
  - Missing required field fails to load.
  - Extra field fails to load (M8 closure for clone_mode).
- **Coordinate with brief 13's `load_clone_mode` fail-closed decision.**
  After brief 16 lands, fail-closed is automatic — schema validation
  raises on malformed input. Update brief 13's rationale if needed.

**Out of scope:**
- Removing `read_key` from disk. **Per Dinis: intentional.**
- Migration of existing `clone_mode.json` files in the wild. Per next-
  phase plan §1 decision 2: **loose migration on read.** This is in
  tension with strict schema validation — see "loose-vs-strict" below.

### Loose-vs-strict tension

The next-phase plan locked in **loose** migration on read (tolerate the
four-field shape + extras), but a Type_Safe schema by default rejects
unknown fields.

Resolution: implement a **read-with-tolerance** path that:
1. Tries `Schema__Clone_Mode.from_json(...)` first — if it succeeds,
   that's the canonical path.
2. On failure due to unknown extra fields, log a warning and parse only
   the recognised subset.
3. Always writes the full schema shape (no extras).

This preserves the "loose-on-read, strict-on-write" intent. The M8
mutation closer must therefore target the WRITE path (a malicious
extra field cannot survive a write-then-read round trip). Document
this distinction in the schema-class docstring AND in the mutation
matrix update.

**Hard rules:**
- Strict Type_Safe on the class.
- Loose-on-read tolerance with a warning log.
- Round-trip on the canonical schema fields only.

---

## Acceptance criteria

- [ ] `Schema__Clone_Mode` and `Enum__Clone_Mode` exist with Safe_* /
      Type_Safe naming.
- [ ] Loose-on-read tolerance implemented + tested.
- [ ] Strict-on-write enforced + tested.
- [ ] Round-trip invariant for canonical fields.
- [ ] M8 closer for the write path.
- [ ] Suite ≥ 2,105 passing, coverage ≥ 86%.
- [ ] No new mocks.
- [ ] Brief 13's `load_clone_mode` fail-closed wording updated if
      affected.
- [ ] Closeout entry on Architect finding 05.

---

## Deliverables

1. New schema + enum source files.
2. Refactored callers.
3. Test file(s).
4. Mutation matrix M8 update (for the clone_mode write path).
5. Closeout entry on Architect finding 05.

Commit message:
```
refactor: Schema__Clone_Mode + Enum__Clone_Mode

Closes Architect finding 05 + Dev finding 10 (clone_mode.json side).
Loose-on-read tolerance honours the next-phase plan decision; strict-
on-write closes M8 mutation gap on the write path.

read_key field remains on disk by design (Dinis decision; AppSec
F07 accepted-risk).

https://claude.ai/code/session_<id>
```

---

## When done

Return a ≤ 200-word summary:
1. Schema + enum field lists.
2. Loose-on-read tolerance behaviour (silently accept? warn?).
3. Test count.
4. Coverage delta.
5. Any issue with brief 13's interaction (escalate if needed).
