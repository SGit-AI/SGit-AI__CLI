# Tabletop brief — 11: Publishing pipelines (DevOps, CI, providers, composition)

**For:** the Explorer/Architect agent, SGit-AI__CLI repo · **From:** the nhi.sgit.ai site
session, with the maintainer · **Date:** 2026-08-19 · **Status:** scenario brief — not yet
executed

**Format requirement:** same discipline as `10__tabletop__github-pages-one-repo.md` —
**executed, not imagined**. Every command block is real output; anything simulated is
marked at every appearance; lab scripts are committed so the run reproduces. One deliberate
change from tabletop 10: **this run should use real GitHub** — a throwaway repo, real
Actions, a real Pages deploy — because the remaining unknowns live exactly where tabletop
10 substituted a local git repo and `python3 -m http.server`. If the environment cannot
create a throwaway repo, say so in the header and mark every hosting step SIMULATED as
before — but the run loses most of its point.

**Why a second tabletop:** tabletop 10 touched CI in one step (the fail-first runner
drill, public vault only, simulated publish) and executed the **pre-r9** spec — the
composition step that a workflow must now perform has never run inside a pipeline. Three
of the traps below are expected to force a spec or CLI change, which is the test of
whether a tabletop is worth running.

---

> **Pack-side note on intake (r10):** §5's owed edits landed with this file's arrival —
> see `CHANGELOG.md` r10 — with one deviation: the maintainer removed the publish folder's
> `*` self-ignore entirely (§0 described it as a guard; the primary flow commits the folder,
> so the guard only added `git add -f` friction). §0's step-2 gap is now **executed
> evidence**: `clone-headless` refuses to run inside a vault, and `sgit status` on a fresh
> checkout errors on the missing `local/vault_key`. Executing this brief for real needs a
> throwaway GitHub repo added to the session's scope.

## 0. Ground truth to carry into every step (corrected 19 Aug)

Two ignore systems, orthogonal, both load-bearing. Conflating them has already produced
one wrong explanation; the brief states them once:

| System | Governs | Contents |
|---|---|---|
| **git's `.gitignore`** (one-repo pattern) | what reaches the GitHub repo | ignore `.sg_vault/local/` (secrets) — everything else in `.sg_vault/` is committed: all of `bare/`, and `publish/` when explicitly `git add -f`-ed past its own `*` self-ignore |
| **sgit's `ALWAYS_IGNORED_DIRS`** (`Vault__Ignore.py:5`) | what becomes vault content on `sgit push` | the entire `.sg_vault/` (+ `.sg_vault_new`, `.git`, `node_modules`, …) — nothing under it is ever vault content; this is what makes publish→push a no-op (I6) |

So: **the store is in git** (that is why CI and Pages have everything they need), and **the
store is never in the vault's own content**. The publish folder's `*` gitignore is a guard
against accidental commit of derived output, not a prohibition — commit it with
`git add -f`, or regenerate it in CI.

**Pre-registered finding to confirm (found by code inspection, 19 Aug):**
`.sg_vault/backups/` is a key-leak hazard. `Vault__Backup` writes zips into
`.sg_vault/backups/` containing `bare/` plus `local/{config.json, move-history.json,
migrations.json}`, and with the include-key option **the vault key itself as `VAULT-KEY`**
(`sgit_ai/core/actions/backup/Vault__Backup.py`, zip-assembly block). The tabletop-10
`.gitignore` ignores only `local/`, so one keyed backup + `git add -A` commits the write
key. Expected outcome: the canonical one-repo `.gitignore` becomes
`.sg_vault/local/` + `.sg_vault/backups/` + `.sg_vault_new/`, stated in the spec and
emitted by tooling — and step 1 below proves the failure before fixing it.

## 1. The cast

| Party | Has | Wants |
|---|---|---|
| **Publisher** (agent) | vault key, the repo | one-repo Pages site, updated by CI on every push |
| **CI runner, public vault** | a fresh `git clone`; **no secrets** | republish + deploy from the committed read-key filename alone |
| **CI runner, private vault** | fresh clone + the read key as a **repository secret** | deploy ciphertext-only site; never see or log the key |
| **Fork contributor** | a fork; **secrets do not follow forks** | open a PR; find out what CI can and cannot do for them |
| **GitHub / Pages** | the repo | — (serves what it is given) |
| **Second provider** (S3+CloudFront *or* Netlify — pick one, name it) | the composed folder | prove the deployer table's rows for a non-GitHub host |
| **Reader** | the live URL only | browse; `sgit clone` back; verify identical |
| **Rollback operator** | the repo, after a bad publish | serve last week's site again, coherently |

## 2. The steps

**Step 1 — canonical `.gitignore`, proven not asserted.** Set up the one-repo pattern.
Run `sgit vault backup` **with** the include-key option; run `git status`; show the zip
staged (the failure), then apply the canonical ignore set and show it excluded. This step
lands the pre-registered finding from §0 as executed evidence and fixes it in the spec.

**Step 2 — the attach drill.** Fresh checkout + a read key in hand → bind them **with a
shipped command**. Today this fails (`FileNotFoundError: local/vault_key`; tabletop 10
step 9 recovered with a lab script). This step forces the real command into existence —
`sgit vault attach --read-key <key>` or whatever the CLI team names it. Definition of
done: the lab script is deleted, replaced by the command.

**Step 3 — workflow provenance.** Produce the canonical workflow file. Decide, in this
step, **where it comes from**: recommended, a CLI generator (`sgit publish
--github-workflow` or similar, written into the repo for the user to commit) — the
argument is drift: publish semantics changed nine times in three days, and a docs-page
copy cannot track that; a generator versioned with the CLI can. Then observe: the next
`sgit push` sweeps `.github/workflows/pages.yml` **into the vault** (F1 generalised — the
work tree is vault content). Decide and record the policy: acceptable (deploy config
travels with clones) or ignored (add to `Vault__Ignore`). Do not leave it as a surprise.

**Step 4 — public-vault pipeline, end to end, real.** Push → real Action runs → **the
composition step** (this is the r9 material that has never run in CI):
mode A *assembled*: copy the surface to the artifact root + `bare/` to
`api/vault/read/<vid>/bare/` (keyless `cp`), `upload-pages-artifact`, deploy;
mode B *branch-root*: serve the repo with `.nojekyll` — confirm F3 for real (remove
`.nojekyll`, show the dot-dirs vanish from the served site, restore it). Confirm
loader precedence at the served root: the hydrated `index.html` is the site; the loader
serves from `.sg_vault/publish/`. Then the reader clones back from the **live Pages URL**
and diffs identical — tabletop 10 step 6, this time against real hosting.

**Step 5 — private-vault pipeline.** Read key as a repository secret; workflow passes
`--visibility` explicitly. Deliberately forget it once: confirm the R3 downgrade fires in
the safe direction (key file silently dropped, site breaks readable-nothing) and that the
warning added in r8 is actually visible in the Action log. Confirm the key never appears
in logs (GitHub masking) — assert on the raw log. Open a PR from the fork: secrets are
absent; record what the workflow does (fail legibly? skip deploy? — decide the intended
behaviour and encode it).

**Step 6 — update and staleness, measured.** Commit, push, redeploy; measure the real
propagation window on Pages (`max-age=600` was a documented number in tabletop 10 — here
it becomes an observed one: how long until a fresh reader sees the new head ref?).
Exercise the r9 stale check in `sgit vault serve` (manifest-hash compare) against a
deliberately stale checkout.

**Step 7 — rollback.** `git revert` the content commit(s), let CI redeploy, and answer:
does the previous site serve coherently — old surface, old head ref, immutable objects
still present? State what rollback *means* for a vault-backed site (the vault's own
history vs the repo's history are different timelines; the site should say which one it
follows).

**Step 8 — F2 in CI.** A refused `sgit push` rewrites mutable-ref bytes (tabletop 10, F2
— filed, not fixed). In a pipeline this makes runners dirty and non-idempotent workflows
flaky. Reproduce it in the Action, then either confirm the fix landed or write the
workaround into the canonical workflow with a comment naming F2.

**Step 9 — the second provider.** Same composed folder to the named non-GitHub host.
Assert at runtime: ACAO header (generalising test cell 10 beyond its Pages-shaped
assumption), cache-control behaviour, dot-directory handling, and the clone-back. Fill
the deployer table's row with measured values, not documentation.

**Step 10 — the closing table.** What every party ended up holding, tabletop-10 style —
with one addition: **what the runner held, and for how long**. The private-vault runner
is the one key-holding service in the whole model (the scoped-CI argument from the hub
pack, and nhi.sgit.ai's least-authority thesis, in one row). Say it plainly.

## 3. Definition of done

- [ ] Every command in the transcript is shipped CLI, or the gap is filed with a named
      proposed command — no lab-script recoveries left standing (step 2 in particular).
- [ ] Every simulated element (if any) is labelled at each appearance.
- [ ] The canonical `.gitignore` set and the canonical workflow file exist as committed
      artifacts, with an owner for keeping the workflow in lockstep with publish semantics.
- [ ] Findings land as a CHANGELOG r-entry (change control is already the pack's law).
- [ ] The deployer table has at least two rows of measured, not documented, values.
- [ ] The traps were walked into deliberately and each produced either a fix or a
      documented, decided behaviour: keyed backup in git (§0), forgotten `--visibility`
      (R3), fork PR without secrets, `.nojekyll` removal (F3), refused-push dirt (F2).

## 4. Out of scope (name it so it is not silently dropped)

Multi-vault monorepos; PR-preview deployments per branch; scheduled re-publishes;
non-Actions CI (GitLab CI, Jenkins). Each is a follow-up scenario, not part of this run.

## 5. Updates the existing pack files owe, independent of the run

The §0 findings stand on code inspection alone, so these edits should not wait for the
tabletop (each lands as its own CHANGELOG entry per the pack's own law):

| File | Update |
|---|---|
| `10__tabletop__github-pages-one-repo.md` | A correction note in the established style (like the r9 note): step 2's `.gitignore` (only `local/`) is insufficient — the canonical set is `local/` + `backups/` + `.sg_vault_new/`. Findings F1–F4 unaffected; the pattern as written commits a keyed backup zip if one is ever made |
| `01__architecture.md` | The publish folder's `*` self-ignore appears three times (§2 layout diagram, §3 listing, manifest example) — that gitignore is unaffected, but it is where a reader learns "the gitignore story", so add the distinction and a cross-reference: **two gitignores, two threats** — the self-ignore inside `publish/` guards derived output from accidental commit; the repo-side set (`local/` + `backups/` + `.sg_vault_new/`, in `07` §4 once it lands) guards **key material**. Without the cross-reference, 01 reads as if the ignore story were complete |
| `07__publish-target.md` §4 | The one-repo discussion states the publish folder's self-ignore; it should also state the **repo-side** canonical ignore set, with the reason per line: `local/` = live secrets; `backups/` = zips that contain `bare/` + local config and, with include-key, `VAULT-KEY`; `.sg_vault_new/` = a complete second store **including its own `local/` secrets** while a vault move is in flight |
| `00__DEV-BRIEF.md` | A rule or constraint: **key material never lands in git** — the canonical ignore set is part of the definition of done for any one-repo work |
| `02__commands-and-ux.md` | `sgit vault backup` inside a git work tree whose ignore rules do not exclude `.sg_vault/backups/` should print a warning (a load-bearing string, per the pack's own standard); the include-key confirmation should mention it too |
| `04__invariants-and-tests.md` | An assertion in the ALWAYS_IGNORED_DIRS style: the emitted repo-side ignore set asserted literally, and a cell — keyed backup in the one-repo pattern, then `git add -A`, assert **nothing under `.sg_vault/backups/` is staged** |
| `06__decisions-and-evidence.md` | Three candidate decisions: **13** — who owns the repo-side `.gitignore` (recommend: sgit emits/maintains the three lines when it detects a git work tree — a convention humans must copy is the drift problem again); **14** — the attach command (`sgit vault attach --read-key`, from step 2); **15** — the workflow generator (CLI vs docs page, from step 3) |
| `CHANGELOG.md` | r10 entry: trigger (maintainer review of this brief — the two-ignore-systems correction and the backups inspection), what changed, decisions 13–15 opened |
| `README.md` | The measured-facts list gains the backups fact once step 1 executes; the files table gains `11__tabletop__publishing-pipelines.md` when the run lands |

---

*Context for the reader: this brief was drafted from the nhi.sgit.ai working session that
captures the static-publishing pack (nhi.sgit.ai/packs/static-publishing/). Tabletop 10's
findings F1–F4 and review findings R1–R9 are referenced as in the pack's CHANGELOG.*
