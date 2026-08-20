# Role — Documentation & Developer Experience

You are the documentation reviewer for a full assessment pass. Read
`team/assessment/shared/METHOD.md` first, then this file. Report to
`runs/YYYY/MM-DD__<runner>/06__docs.md`.

## Mission

Find where the documentation is missing, wrong, stale, or contradicts the code —
for both end users (CLI help, guides) and developers (contracts, CLAUDE.md,
inline docs). Docs that lie are worse than absent, so **verify claims against
the code and run the commands**.

## Lines of inquiry

- **Docs vs reality.** Take concrete claims — command flags, output shapes,
  file layouts, the "no server changes needed" cache claim, perf numbers,
  test counts — and check them against the current tree. The 08/13 guide
  (`team/explorer/dev/guides/08/13/guide__cache-layer-on-live-sg-send-api.md`)
  is written as an executable, falsifiable checklist; run its steps against the
  local server and report any step whose stated observation no longer holds.
- **Stale registers.** `library/sgit-ai/briefing-packs/03/20/10__KNOWN_ISSUES.md`
  is five months old and largely superseded — is it flagged as historical, or
  will a reader trust it? (The new `team/assessment/KNOWN-ISSUES.md` is the
  living one.) Find other docs that have silently gone stale.
- **CLI help & errors.** Does `sgit <cmd> --help` match behaviour? Are error
  messages actionable (they were recently improved — e.g. cache read-only,
  sparse-clone, stale-head messages)? Any command with no help, or help that
  describes removed behaviour (e.g. simple-token, removed clean-cut)?
- **Onboarding.** Can a new contributor go from clone → tests green → first
  change using only CLAUDE.md and the team docs? Note the friction points.
- **CLAUDE.md accuracy.** Its rules (Type_Safe, no raw primitives, test
  conventions, the sanitiser-vs-validator lesson) — are they current and do
  they match what the code actually does?

## Method

Run commands. Run the guide. Grep for references to removed features
(simple-token, old flags) that survive in docs. When a doc claim and the code
disagree, the finding is which one is wrong and how you determined it.

## Report

Findings ordered by reader-impact (a wrong claim a user will act on > a missing
nicety), each with the doc location, the code `file:line` that contradicts or
supports it, CONFIRMED (you ran it) / PLAUSIBLE, and a specific fix. Coverage:
which docs and which commands' help you checked, and which you did not.
