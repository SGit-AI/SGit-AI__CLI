# v1 — Full review pass: static-publishing pack (files 00–10)

**Date:** 2026-08-19 · **Scope:** every file in
`team/explorer/dev/impl-plans/08/17/static-publishing/` after the 17–19 Aug revision cycle,
plus a **live end-to-end run** of the whole flow (real CLI + in-memory server + simulated
GitHub/Pages) whose transcript is `10__tabletop__github-pages-one-repo.md`.

**Verdict:** the core is sound and now *empirically* sound — the live run confirmed I1, I4,
I6, the read-only static clone on both layouts, keyless custody, and the update cycle. The
pass found **one genuine spec contradiction** (R1 — expansion has three owners on paper),
**one code bug** (F2 — a refused push rewrites ref bytes), and a handful of gaps that are
cheap now and expensive after P2 ships.

---

## 1. Confirmed by execution (not re-argued, just recorded)

| # | Claim from the pack | Result |
|---|---|---|
| C1 | I6: publish → push adds nothing | ✔ `Nothing to push`, 12 → 12 objects |
| C2 | I1 makes the git double-commit ~free | ✔ 46 files → 29 blobs; **all 17** projection copies dedupe against the store |
| C3 | Static clone, api-path layout | ✔ real `clone_read_only` + spike transport; key classified `READ_PUBLIC` |
| C4 | Static clone, flat layout | ✔ against the **raw repo checkout** at `…/repo/.sg_vault` — no publish step involved |
| C5 | Custody without access | ✔ 18 objects mirrored from `manifest.json` with zero key material; 12 `obj-cas-imm-*` verified by content address |
| C6 | Update cycle | ✔ edit → sgit push → republish → git push → redeploy → fresh clone shows the change |
| C7 | Publish needs **only the read key** | ✔ ref decrypt + full commit parent-walk ran from `import_read_key(committed key filename)`; the vault key was never read |

C4 deserves its own sentence: **a repo that commits `.sg_vault/bare` is already a
statically clonable vault, today, with shipped code.** Publish adds the loader, the
manifest (custody), and key discovery — not clonability. That reframes P2's value
proposition and should be stated in the README.

C7 resolves a question the pack never asked: *which credentials does `sgit publish`
require?* Answer, now proven: the read key. P2 should state it, and it is what makes the CI
story work (§R3).

## 2. The one real contradiction — expansion has three owners on paper (R1)

Three files currently disagree about who decrypts vault content into a served root:

| File | Says |
|---|---|
| `01` §2/§3 | `sgit publish --with-plaintext` emits `files/…` **inside the publish output** |
| `07` §3/§5 | expansion is a **deployment-time** act by the deployer; publish output contains **no vault content** — and §7 says deployment is out of the CLI's scope |
| `02` mockup | a `sgit deploy ../site-repo/docs --expand` command that **no phase builds** |

These cannot all be true. `07` is the settled position (19 Aug, maintainer-confirmed), so:

- **`01`**: delete `files/…` from the layout and the `--with-plaintext` edge from the
  projection diagram.
- **`02`/README**: remove `--with-plaintext` from the `sgit publish` usage line. The I5
  refusal mockup then has no command to hang off — either the refusal moves to the future
  expand command, or I5 is restated as a property of *whatever* performs expansion.
- **Decide where expansion lives**: recommend a named future phase — `P8: sgit vault
  expand <dir>` (decrypt work-tree content into a deployment root, key required, refuses
  to write a key file unless visibility is public) — so I5 keeps an enforcement point
  inside the CLI. Until P8 exists, "fully expanded" deployments are the one-folder git
  pattern itself: the work tree *is* the expansion (tabletop step 4).

This is the only place the pack contradicts itself; everything else below is a gap, not a
conflict.

## 3. Bug found by the live run — refused push rewrites ref bytes (F2)

A `sgit push` that **refused** to run (uncommitted changes) still rewrote
`.sg_vault/bare/refs/ref-pid-muw-…` — same commit id, fresh IV, new bytes. Consequences in
the one-folder pattern: `git status` shows a modified ref after a no-op, producing noise
commits and spurious diffs; at minimum it defeats "the only path that changed is X"
reasoning anywhere we rely on it.

Where to look: the push pre-flight (fetch of the server named ref → local rewrite) runs
before the uncommitted-changes gate. Fix shape: compare-before-write (skip the rewrite when
the decrypted commit id is unchanged), or move the gate ahead of the pre-flight. Needs a
regression test asserting a refused push leaves `bare/` byte-identical.

Also recorded as **F1**: the root `.gitignore` is vault content (`sgit status` shows
`+ .gitignore`), so a vault cloned elsewhere carries the publisher's git ignore rules.
Cosmetic; document in the pattern guide rather than special-case it.

## 4. Gaps, in cost order

### R2 — Jekyll eats dot-directories on branch-root Pages deploys

Mode B (serve the whole repo from a branch root) only works with a **`.nojekyll`** at the
repo root: Pages' Jekyll pass silently excludes `.sg_vault/**`. The failure is invisible —
the site loads, the loader 404s on every object. Add a row to `07` §5's deployer table and
put `.nojekyll` in the canonical workflow/repo template (it is deployer config in the repo,
so I1 is untouched). The Actions-artifact mode (recommended) does not run Jekyll.

### R3 — the CI republish silently flips visibility to `bare`

Decision 5 (visibility in per-clone local config, fresh clone defaults `bare`) has a
knock-on the pack missed: a CI runner is *always* a fresh clone, so a republish that omits
`--visibility` **drops the key file** and the published site stops opening. Safe direction,
still a breakage. Resolution, consistent with the 16 Aug brief: the workflow file (in the
repo) passes `--visibility public` explicitly — the pipeline definition *is* the recorded
choice. Two additions:

- publish should **warn on downgrade**: if the existing `manifest.json` in the output says
  `public` and the new run resolves `bare`, say so loudly (refuse without `--yes`?
  maintainer's call — it is the mirror image of the private→public prompt).
- the pack should ship the **canonical workflow** (checkout → sgit publish → deploy-pages),
  since item 4 of the 16 Aug brief promised one and nobody wrote it. The tabletop's step 5
  YAML is the draft.

### R4 — publish-vs-store staleness in the committed-projection pattern

When `.sg_vault/publish/` is committed (tabletop mode), an author who `sgit push`es but
forgets to republish leaves the deployed projection **behind** the committed store — the
loader serves the old head while the fresh objects sit unreachable next to it. Cheap,
keyless detector (byte-compare, no crypto): projection ref file ≠ `bare/` ref file →
stale. Belongs in `sgit vault serve` (banner), in publish (auto-detected note), and in the
canonical workflow (fail the deploy or republish automatically — which C7 makes possible
keylessly for public vaults).

### R5 — `--force` is still in the usage line with no meaning

`02` §1 still lists `[--force]`; nothing defines it since the target argument was removed.
Delete it, or define it as "republish even when staleness checks say current". Leftovers
like this are what a developer agent implements *because the spec said so*.

### R6 — custody verifies content-addressed objects only

The mirror drill verified 12 of 18 objects: `refs/indexes/keys` are HMAC/random-named, not
content hashes, so a keyless mirror can only check their presence and sizes. `04` I3 and
P5's acceptance should say this explicitly — "every object verified" is currently
overstated — and `manifest.json` could carry `sha256` per object (of the ciphertext) to
close the gap for *all* files at zero cost, since publish is already hashing the plaintext
surface. Recommend: add `sha256` to `objects[]` entries; mirror verifies everything.

### R7 — `sgit vault serve` "stale" is undefined

P3 acceptance says "publishing first if absent or stale" with no definition. R4's byte
compare is the definition. State it, or drop "stale" and always republish (it is
deterministic and fast; the tabletop's 18-object publish is instant).

### R8 — Pages' `max-age=600` on the mutable ref

After a redeploy, readers can receive the **old head ref for up to ~10 minutes** (plus CDN
lag); immutable objects are unaffected. Not fixable from our side and mostly harmless —
but the deployer table should say it, because "I republished and the site still shows the
old version" is the first support question this feature will generate.

### R9 — bundles are waste on git-hosted targets

Zip containers do not dedupe against loose objects in git (measured logic, C2's inverse),
and git's own transfer protocol already delta-compresses. `--bundles` should be documented
as an object-storage optimisation; the canonical Pages workflow should not use it.

## 5. Smaller notes

- **Cover data source** is still unspecified (title/description/access): recommend
  per-clone local config with flags (`sgit publish --title …` persisting), consistent with
  decision 5's location; `updated` joins `generated_by` in the determinism caveat.
- **`keys/` in the projection**: the publish copies `bare/keys/key-rnd-imm-*` (encrypted
  PKI keys). Correct — they are ciphertext and the read path may need them — but no pack
  file mentions them; `01` §3's layout should list `keys/` (it currently shows
  `indexes/… keys/… data/…` in one line — fine — but the manifest example omits them).
- **Object count realism**: the live vault produced 15–18 published files for a 4-file
  site. The 3,000-per-directory GitHub UI truncation (the 08/15 sharding briefing) arrives
  at ~750 vault files under `data/`; the deployer table should cross-reference the sharding
  briefing as the eventual answer for big vaults on git hosts.
- **`10__tabletop` lab scripts** (`simulate_publish.py`, `reader_clone.py`,
  `ci_publish_readkey.py`) are session-scratch; promote to `scripts/` if wanted as living
  documentation — `simulate_publish.py` is ~120 lines and is, in effect, P2's first draft.

## 6. What I would do next, in order

1. Fix the R1 contradiction in `01`/`02` (delete `--with-plaintext` from publish; name P8).
2. File + fix F2 (refused push rewrites refs) with a bare-unchanged regression test.
3. Add R2/R3/R8 rows to `07` §5 and write the canonical Pages workflow into the pack.
4. Add `sha256` to manifest `objects[]` (R6) — one line in P2, closes the custody gap.
5. Promote the tabletop scripts; `simulate_publish.py` becomes the P2 skeleton.
