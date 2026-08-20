# 11 — Tabletop (executed): publishing pipelines — CI, providers, composition

**Date:** 2026-08-19 · **Brief:** `11__tabletop-brief__publishing-pipelines.md` · **Status:**
EXECUTED in **simulated-hosting mode**, at the maintainer's instruction ("no need to create
the repos, just simulate it"). Per the brief's own fallback clause: GitHub, Actions and
Pages are stand-ins (local bare repo, a runner script performing the workflow's exact
steps, `python3 -m http.server`) and are marked SIMULATED at every appearance. Everything
sgit-shaped is real: the CLI (editable install of this repo), the in-memory SG/Send server,
real crypto in the two lab stand-ins (`simulate_publish.py` for P2, `attach_simulated.py`
for P9). **Not measurable in simulation** and explicitly deferred to a real-GitHub run:
Pages propagation timing (step 6), secret masking in Action logs (step 5), ACAO /
cache-control / dot-directory behaviour of real providers (steps 4b, 9).

Vault: `o7oohxk7` (the tabletop-10 handbook), continuing that run's state at pack r10.

---

## Step 1 — the canonical `.gitignore`, proven not asserted (REAL)

```console
$ sgit vault backup --include-key --yes .
  vault-key included: yes                      # zip contains 52-byte VAULT-KEY + local/config.json
$ git check-ignore .sg_vault/backups/o7oohxk7__…__manual.zip     # .gitignore = local/ only
** NOT IGNORED — git add -A would stage the vault key **
$ printf '.sg_vault/local/\n.sg_vault/backups/\n.sg_vault_new/\n' > .gitignore
$ git check-ignore -v .sg_vault/backups/…zip
.gitignore:2:.sg_vault/backups/    …zip        # excluded
```

The brief's §0 pre-registered finding is confirmed **executed**: tabletop 10's
`local/`-only ignore commits the write key after one keyed backup. The canonical set is
three lines (decision 13).

## Step 2 — the attach drill (SIMULATED command, real crypto; P9's spec exercised)

```console
$ git clone …/acme-handbook.git runner && ls runner/.sg_vault
bare  publish                                        # no local/ — no shipped command can bind a key
$ attach_simulated.py runner --vault-key sgit_private_vault_wrong…:o7oohxk7
error: derived ref ref-pid-muw-bb8caef8d3ac not found in bare/refs — wrong key. Nothing written.
$ attach_simulated.py runner --read-key <committed key filename> --vault-id o7oohxk7
attached (read-only): vault o7oohxk7  ref ref-pid-muw-fb98b8b3444b verified in bare/refs
$ sgit status
On named branch: branch-named-…  (up to date)        # the vault OPENS
```

**Two P9 acceptance criteria were discovered by failing, not designed:**

- **F6a — attach is mode-exclusive.** A read-only attach followed by a read-write attach
  left a stale `clone_mode.json`, and the *shipped* clone-mode guard refused to open the
  vault ("prevents a silently-demoted read-only clone from accepting writes" — a good
  guard doing its job). Attach must remove the other mode's artifacts.
- **F6b — schema-exact or refused.** A hand-shaped `clone_mode.json` was rejected as
  malformed. P9 must write `Schema__Clone_Mode` exactly; the guard is the test.

## Step 3 — workflow provenance, and the file joins the vault (REAL)

The canonical workflow now exists as a committed artifact:
[`templates/github-pages.yml`](templates/github-pages.yml) — the future generator's output
(decision 15). Installed into the repo and committed:

```console
$ sgit status
  + .github/workflows/pages.yml            # ← swept into the VAULT as content (F1 generalised)
$ sgit commit && sgit push .               # policy: ACCEPTED — deploy config travels with clones
```

The policy is not hypothetical: in step 4 the **reader's clone arrived carrying
`pages.yml`**. A vault published this way tells its cloners how it deploys. Recorded as
accepted; the alternative (an sgit-side ignore) would either desync from git or
retroactively drop `.github/` content from existing vaults.

## Step 4 — the public-vault pipeline, end to end (runner SIMULATED, sgit REAL)

```console
[attach]  read key recovered from the committed key filename — zero secrets
[publish] Publishing vault o7oohxk7 -> .sg_vault/publish/     (read-only clone: works — C7 again)
[compose] cp .sg_vault/publish/* _site/ ; cp -r .sg_vault/bare _site/api/vault/read/o7oohxk7/bare
          _site: 32 files (168K)
[deploy]  → simulated Pages
[reader]  sgit clone (read key): layout api/vault/read/{vid}/{fid} — IDENTICAL to the author
          work tree, including .github/workflows/pages.yml
```

**The run also broke, twice, and both breaks are findings:**

- **F5 — a dead host reads as an empty vault.** The first clone-back hit a half-dead
  `http.server` (connections failing, HTTP 000) and the transport reported: *"Nothing to
  clone: this vault has no branch index and no named ref on the server."* Connection-level
  failure was indistinguishable from 404-absent. **P1 acceptance extended:** only an HTTP
  404 is `None`/absent; connection refused/reset/timeout must raise loudly with the host
  named. Diagnosing "empty vault" when the truth is "host down" sends an operator toward
  re-keying instead of restarting a server.
- **F7 — the F2 workaround, mis-ordered, destroys the head.** `git checkout --
  .sg_vault/bare/refs/` run *after* a successful `sgit push` reverted the freshly-updated
  head ref to the previous commit's bytes, and the next deploy served a stale head. Safe
  order, now in the workflow template: restore refs **before** sgit operations; **commit
  after** `sgit push`; never checkout refs after a successful push.

## Step 5 — the private-vault pipeline (SIMULATED runner)

- **R3, demonstrated:** on a read-only runner, republish **without** `--visibility` →
  `Visibility bare`, key-file count 1 → 0. The site silently locks readers out (safe
  direction). The r8 warning is P4's to ship; the workflow passes the flag explicitly.
- **Fork PR (secrets absent):** no committed key file + no secret → the workflow skips
  legibly: *"no key available (fork PR?) — skipping deploy, this is expected"* → exit 0.
  Found and fixed a template bug on the way: the guard must **file-test** the key glob —
  an unmatched shell glob is a non-empty literal string, so the naive `-z` check never
  fires.
- **Key in logs:** sgit-side output prints the vault id and ref id, never the key (grep:
  0 occurrences). The key does appear in the *invoking command line*; masking that is
  GitHub secret-masking — NOT MEASURABLE here, asserted in the real-GitHub run.

## Step 6 — update + staleness, the keyless check running (REAL)

Author pushes v2 to the vault and **forgets to republish**; the runner detects it without
any key, from the manifest's per-object hashes (the r8 addition earning its keep):

```console
[staleness check] manifest ref sha cda641337a91… vs bare on disk 947d27a39ac7… -> STALE
[workflow] STALE -> republish before composing
[reader sees] v2: security policy updated.        # after republish + redeploy
```

Pages propagation timing: NOT MEASURABLE in simulation; deferred.

## Step 7 — rollback (REAL git, SIMULATED hosting)

`git revert` of the v2 commit → CI redeploys → fresh reader clone has **no v2 marker**:
the site rolled back coherently, surface and store together, because both live in the same
git commit. The point to state: **the site follows the repo timeline, not the vault's** —
the SG server's head is still v2; a vault clone from the *server* sees v2, a clone from
the *site* sees v1. A published site is a projection of a git commit, and rollback means
`git revert`.

## Step 8 — F2 in CI, refined (REAL)

Under `local ref == server ref`, a refused push rewrote **nothing** (ref sha unchanged).
Combined with tabletop 10 (where the local ref had been git-restored to older bytes and
the refused push overwrote it), **F2 refines to:** the push pre-flight syncs the local ref
file to the server's bytes even when the push is refused — a state change on a refused
operation whenever local bytes differ. Less alarming than "fresh IV every time", still a
bug: refused operations should not write. The fix target and the regression test
(bare byte-identical after refused push) stand; the workflow's F7 ordering note covers CI
until then.

## Step 9 — the second provider (SIMULATED)

Same composed folder served from a second origin; clone-back **identical across providers**
(I1). The row this step exists for — measured ACAO, cache-control, dot-directory handling
on a real S3/CloudFront or Netlify — is NOT MEASURABLE in simulation and stays open in the
deployer table.

## Step 10 — who held what, and for how long

| Party | Key material held | Duration | Note |
|---|---|---|---|
| Author | vault key | permanent | the only write-capable party |
| GitHub repo | public read key (filename), ciphertext, plaintext work tree | permanent | exactly what `--visibility public` published |
| **Public-vault runner** | read key, **recovered from the repo itself** | job lifetime | zero secrets configured; everything it held, the world already had |
| **Private-vault runner** | read key, from a repository secret | job lifetime | **the one key-holding service in the whole model** — scoped, ephemeral, read-only; it can rebuild the surface and decrypt content, never write |
| Fork runner | nothing | — | skips legibly |
| Reader | read key from the site | their machine | read-only clone; no vault key anywhere downstream |
| Rollback operator | none (git only) | — | rollback is a git operation; no sgit credential needed |

---

## Findings ledger (this run)

| # | Finding | Lands where |
|---|---|---|
| F5 | dead host indistinguishable from empty vault; misleading "no named ref" diagnosis | **P1 acceptance** (404 ⇒ absent; connection errors ⇒ loud failure) |
| F6a/b | attach must be mode-exclusive and Schema__Clone_Mode-exact; the shipped guard enforces it | **P9 acceptance** |
| F7 | refs-checkout after a successful push destroys the head; safe ordering | workflow template comment |
| F2′ | refined: pre-flight rewrites local ref to server bytes on refused push *only when bytes differ* | v1 review F2, sharpened repro |
| — | fork-guard shell-glob trap (unmatched glob is a truthy literal) | workflow template, fixed |
| — | brief §0 keyed-backup hazard: executed, confirmed | `07` §4 canonical set (r10) |

**Definition-of-done check against the brief:** every command shipped-or-filed ✔ (attach →
P9; publish → P2, both with lab stand-ins named for retirement); simulated elements
labelled ✔; canonical `.gitignore` + workflow committed ✔; findings in CHANGELOG ✔;
deployer table measured rows ✖ — **needs the real-GitHub run** (steps 4b/5/6/9 carry the
NOT MEASURABLE markers that define its scope).
