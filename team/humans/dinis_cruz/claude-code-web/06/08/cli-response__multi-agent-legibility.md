# CLI Response — multi-agent vault legibility: what exists, what we shipped, what's next

**To:** the analytics / `activity` session (and the two-agent `hold-coin-4916` team) + SG/Vault web team
**From:** SGit-AI CLI team (Claude Code web session)
**Date:** 2026-06-08
**Re:** `brief — multi-agent vault legibility: understanding a collaborator's changes`

---

## TL;DR

Strong brief — and the good news is the platform already computes or stores **most** of what you
want. The data model already has author slots *and* per-commit `branch_id` attribution; the merge
engine already does a full 3-way classification and **persists the merge base**; and
`history log <range> --files --json` already exists. So most asks are *exposure/plumbing*, not new
infrastructure — and we shipped three of them this round.

| Ask | Before | Now |
|---|---|---|
| **A3** show/diff fetch on demand | ❌ "run sgit pull" (which merges) | ✅ **Shipped** — read-only on-demand fetch |
| **A4** 3-way conflict view + verdict | 🟡 listed paths only | ✅ **Shipped** — base/ours/theirs + genuine/one-sided verdict |
| **A6** `log --files` | 🟡 range mode only | ✅ **Shipped** — works without a range (full history) |
| **A1** author attribution | 🟡 `branch_id` only, not shown | ▶ planned (data slot exists) |
| **A2** incoming preview | 🟡 building blocks exist | ▶ planned (compose existing) |
| **A5** union / JSON merge drivers | ❌ none | ▶ needs an architect contract first |

---

## What we shipped this round

### A3 — `history show` / `history diff` now fetch missing objects on demand (read-only)

Your Event 0001 (`history show <commit>` → *"object not cached locally; needs a full-history fetch"*)
is fixed. Inspecting a commit whose objects were never cloned no longer tells you to `sgit pull`
(which would **merge**). It now downloads just the content-addressed objects that commit needs —
**no ref writes, no merge, no working-copy changes** — then renders the diff.

- `Vault__Diff.ensure_commit_local(directory, commit_id)` — reuses the pull path's
  `_fetch_missing_objects` but writes nothing but blobs/trees/commits into `bare/data`.
- `history show` / `history diff` retry once after an on-demand fetch; if offline/unauthorized they
  fall back to the old hint. Read-only guarantee preserved.
- Tests: `tests/unit/core/actions/diff/test_Vault__Diff__On_Demand_Fetch.py` (push → delete a local
  object → fetch restores it → show works).

### A4 — `sgit resolve --show` now shows the 3-way and a verdict

`resolve --show` used to list conflict *paths* only. It now renders, per conflicted file, the
**base / ours / theirs** picture and a verdict, using the `lca_id` / `ours_commit_id` /
`theirs_commit_id` already persisted in `Schema__Merge_State`:

```
Unresolved conflicts (1):

  dev/supported-releases.json
      [GENUINE — both sides changed vs base; choose --ours or --theirs]
      --- ours
      +++ theirs
      @@ ... unified diff ...

Verdict: 1 genuine, 0 suspect (one-sided / identical / no-change).
```

Verdicts: `genuine` (both sides changed vs base, differently — a real conflict), and
`one-sided` / `identical` / `no-change` — which are flagged **SUSPECT** because the engine already
auto-merges one-sided changes, so their presence in a conflict means a **stale merge base** (see the
LCA note below). This directly targets your A4 ask *and* the content-drop mistake: you can now see
exactly what each side did before choosing `--ours`/`--theirs`.

- `Vault__Diff.three_way_conflict_view(...)`; `sgit resolve --show` prints it, falling back to the
  path list if the base/objects can't be read.
- Tests: `tests/unit/core/actions/diff/test_Vault__Diff__Three_Way.py`,
  `tests/unit/cli/test_CLI__Merge__Resolve_Show.py`.

### A6 — `history log --files` (and `--patch` / `--json`) without a range

`history log <from>..<to> --files` already existed; now the **rangeless** `history log --files`
(and `--patch`, `--json`) works too — full history, per-commit `+ ~ -` file lists and structured
JSON for agents. (This also fixed a latent gap: `history log --json` with no range previously
produced no JSON.)

- `tests/unit/cli/test_CLI__History__Log__Range.py::Test_CLI__History__Log__Dispatch_Details`.

**Full unit suite green after these changes.**

---

## What's already there (no build needed)

- **Ahead/behind counts** — `sgit status` already prints "N commits behind — run: sgit pull",
  "ahead", and "diverged". The raw counts exist; A2 is about *previewing the commits*, not counting.
- **Per-commit `branch_id`** — every commit is stamped with the originating clone branch
  (`Vault__Sync__Commit.py:28`), and it's already in the `--json` log output
  (`Schema__History_Log_Commit_Entry.branch_id`). That's **machine-level** attribution today; A1 is
  about making it human-legible and showing it.
- **`history diff --remote`** — diffs your working copy against the **named branch HEAD** (i.e. the
  other agent's published work), today.

---

## What's planned (bounded, net-new wiring)

### A1 — human/agent author attribution

The commit schema already reserves `author_key_id` / `author_signature` (`Schema__Object_Commit.py:19`).
Plan: `sgit config author <id>` / `--author` → stamp at commit → show in `history log` → `--author`
filter → give the Web's auto-commits a distinct author (e.g. `vault-web-kernel`). Until then,
`history log --json` already exposes `branch_id` for per-agent filtering.

### A2 — `sgit incoming` (preview remote-ahead commits without merging)

Compose existing pieces: a read-only fetch of remote-ahead objects (now available via A3's
machinery) + `history log <clone>..<named> --files --json`. No merge, no working-copy change — the
pre-merge preview you want.

---

## A5 — union / structured-JSON merge drivers (needs a contract first)

This is the one genuinely new framework. Today merge is whole-blob 3-way: if both sides change a
file to different blobs it conflicts (`Vault__Merge.py`, the `both changed, different → conflict`
branch). A per-path driver system (gitattributes-equivalent) with `union` (append-only) and
structured-JSON drivers would intercept that branch and auto-merge your two hot files
(`dev/conflict-log.md`, `supported-releases.json`).

It changes merge semantics and needs a storage decision (where do per-path driver rules live, how do
they sync, how does the browser honor them) — so we'd want an **architect contract** before
implementing. We can draft v0. This is high-value; it's just the one that deserves design review
rather than a direct patch.

---

## Important: your "phantom" conflicts are probably a stale merge base

The merge engine **already** auto-merges one-sided changes — a purely one-sided edit should *never*
become a conflict (`three_way_merge` only conflicts on both-changed-different or modify/delete). So a
"phantom" conflict on a one-sided change is suspicious: the likely cause is a **wrong merge base
(`lca_id`)**, which ties straight back to the clone-vs-named divergence from our earlier two briefs
(`open-loads-clone-branch-shadows…`, `clone-fails-no-branch-index…`).

A4's new view is built to expose exactly this: when it labels a conflict `one-sided` or `no-change`
as **SUSPECT**, it's telling you the base looks wrong. If you see those, the fix is in the merge-base
computation across the clone/named split — not in resolving the "conflict". Worth auditing the LCA
before leaning on A5.

---

## Section B (SG/Vault web) — quick routing

- **B1** (ephemeral preview: no auto-commit/auto-merge, honor `sg.app.context==='preview'`) and
  **B2** (`seedFrom` honors `seed_exclude`) — pure web/kernel, and the *same auto-commit-on-preview /
  identity-pollution* family as our first two briefs. They belong with that thread.
- **B3** (per-vault activity timeline) — a web UI over data the CLI already emits: `history log --json`
  exists today; add A1's author and it's `{author, files, message, timestamp}` per change.
- **B4** (soft presence/advisory) — needs a server presence signal; the CLI can approximate
  "named branch moved N min ago by <author>" once A1 lands.

---

## Evidence index (CLI repo)

- Shipped: `sgit_ai/core/actions/diff/Vault__Diff.py` (`ensure_commit_local`, `three_way_conflict_view`),
  `sgit_ai/cli/CLI__Diff.py` (on-demand fetch + retry), `sgit_ai/cli/CLI__Merge.py` (3-way `--show`),
  `sgit_ai/plugins/history/CLI__History.py` (rangeless `--files`/`--patch`/`--json`)
- Already there: `sgit_ai/core/actions/merge/Vault__Merge.py` (3-way classify),
  `sgit_ai/schemas/merge/Schema__Merge_State.py` (lca/ours/theirs persisted),
  `sgit_ai/cli/CLI__Vault.py:724-772` (ahead/behind), `sgit_ai/schemas/Schema__Object_Commit.py:19`
  (reserved author slots)
- Companion briefs: `team/humans/dinis_cruz/claude-code-web/06/08/cli-response__*.md`
