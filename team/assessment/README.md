# Assessment Pack — Recurring Full-Codebase Review

A prompt pack for running a **full, clean-context assessment** of the entire sgit
codebase at a regular interval or before a major release. Multiple independent
role agents each do one focused pass; a conductor consolidates everything into a
single assessment pack, diffed against the previous run and against the living
known-issues register.

The pack is runner-agnostic by design: the launcher prompt is tiny and points
here. It has been run with Claude (Routine / Claude Code) and ChatGPT Codex —
any agent that can read the repo, run commands, and commit can execute it.

## Layout

```
team/assessment/
├── README.md            ← you are here (includes the launcher prompts)
├── KNOWN-ISSUES.md      ← living register: open issues, accepted risks, security posture
├── shared/METHOD.md     ← ground rules every role MUST read before starting
├── roles/               ← one prompt per independent role agent
│   ├── 01__security.md      02__resilience.md     03__performance.md
│   ├── 04__bugs.md          05__features.md       06__docs.md
│   └── 07__ux.md
├── conductor/CONDUCTOR.md   ← consolidation prompt (runs LAST)
└── runs/                    ← committed history; every run reads the previous ones
    └── YYYY/MM-DD__<runner>/
        ├── 01__security.md … 07__ux.md   (one report per role)
        └── 00__assessment-pack.md        (the conductor's consolidated output)
```

## How a run works

1. **Branch**: create `assessment/YYYY-MM-DD-<runner>` from the latest `dev`
   (`<runner>` = `claude`, `codex`, …). Never run on `dev`/`main` directly.
2. **Ground**: every agent reads `shared/METHOD.md`, then `KNOWN-ISSUES.md`,
   then the most recent `runs/` folder (and the most recent one from a
   *different* runner, if any) — so known and previously-reported items are
   recognised, not rediscovered.
3. **Role passes**: each role agent works from a clean context, follows its
   role file in `roles/`, and writes its report to
   `runs/YYYY/MM-DD__<runner>/NN__<role>.md`. Roles are independent —
   run them in parallel (subagents) or sequentially (separate sessions);
   they must not read each other's reports.
4. **Conduct**: once all role reports exist, the conductor follows
   `conductor/CONDUCTOR.md`, writes `00__assessment-pack.md` into the same
   run folder, and updates `KNOWN-ISSUES.md` in place.
5. **Deliver**: commit everything on the assessment branch and open a PR
   titled `Assessment YYYY-MM-DD (<runner>)`. The PR is the deliverable;
   the human merges it, which is what makes the run part of history.

## Launcher prompt (Claude Routine / Claude Code)

> Clone SGit-AI/SGit-AI__CLI (branch dev) and read `team/assessment/README.md`.
> Execute a full assessment run as described there, with runner name `claude`:
> create the assessment branch, run all seven role passes as independent
> parallel subagents (each subagent reads ONLY `shared/METHOD.md`, its own
> role file, `KNOWN-ISSUES.md` and past runs — not the other roles' output),
> then run the conductor, commit, and open the PR.

## Launcher prompt (ChatGPT Codex)

> Read `team/assessment/README.md` in this repo and execute a full assessment
> run with runner name `codex`. Codex note: run the seven roles as seven
> sequential clean passes — before each role, re-read only that role's file
> plus `shared/METHOD.md`, and do not carry findings between roles in
> working memory (write each report to its file, then move on as if fresh).
> Finish with the conductor pass, commit on the assessment branch, open a PR.

## Cadence

Intended for: (a) a scheduled interval — monthly is a good default for a
codebase this size; weekly produces mostly-empty deltas — and (b) an
on-demand run before every major (x.y.0) release. The pack itself is
versioned: improve the prompts whenever a run shows a blind spot, in the
same PR as that run.

## Maintaining the pack

- A role that keeps reporting accepted items → tighten its "do not report" list.
- A bug that reached users without a run catching it → add the missing probe
  to the relevant role file (post-mortem rule).
- `KNOWN-ISSUES.md` is updated **only** by conductor runs and humans.
