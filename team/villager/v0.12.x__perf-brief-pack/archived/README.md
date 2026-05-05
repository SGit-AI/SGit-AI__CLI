# Archived — Reason

These briefs (B08, B08b) were authored when we expected B07's case-study
diagnosis to demand server-side packs urgently. After the diagnosis +
post-HMAC-IV dedup math, the server-pack work is **deferrable** — the
typical vault activity (dozens of files / commit, HMAC-IV from creation)
has expected clone times in the 10–20s range without server packs.

The decision (2026-05-05): defer B08 / B08b until we re-measure
post-migration (B10 in v0.13.x) and confirm whether the typical user's
clone time is acceptable. If it is, B08 stays archived and may move to
v0.14.x or later. If it isn't, the briefs are ready to pull back into
the active pack.

**Both briefs are durable design documents.** The wire format spec
(B08b §3), API endpoints (B08b §4), pack-builder algorithm (B08b §5),
cache policy (B08b §6), pre-warming hook (B08b §7), and backward-compat
strategy (B08b §9) are all valid and will not need redesigning when
the work is picked up.

**SG/Send team thread:** Dinis to graceful-pause the conversation.
Suggested wording in the v0.13.x sprint overview.

**When to revisit:**
- After B10 migration command lands.
- After post-migration B07-style re-measurement.
- If a class of users emerges (very large vaults, satellite/cellular,
  sub-second cold-clone UX) where 10–20s isn't acceptable.

**See also:**
- `team/villager/v0.12.x__perf-brief-pack/changes__case-study-diagnosis.md`
  — B07's quantitative analysis that drove the deferral.
- `team/villager/v0.13.x__brief-pack/01__sprint-overview.md`
  §"What v0.12.x deferred" for the sprint-level rationale.
