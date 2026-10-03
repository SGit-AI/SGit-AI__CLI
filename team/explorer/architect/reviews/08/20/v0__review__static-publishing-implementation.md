# Review — static-publishing implementation (`claude/sgit-cli-review-rxll54`)

**Reviewed:** `6c3e343..000a5fa` (6 commits, 96 files, +5548/−356) · **Date:** 2026-08-20
**Reviewer:** the architecture session that wrote the pack (r14)
**Against:** `team/explorer/dev/impl-plans/08/17/static-publishing/` phases P0–P7, P9, and
`03__review-contract.md`

---

## Verdict

**The work is good and the phases are genuinely done.** Every claim in the debrief that I
checked held up, including the two suite counts, and the spec corrections in r15 are honest
(one of them fixes an error of mine). The P0 regression suite is exactly the test the
maintainer's condition needed.

**Two findings block "supported", both about integrity rather than function**, and both were
verified by execution, not by reading:

- **A1** — SP-1 / invariant I7 is bypassable on **every** vault, not only moved ones. A
  hostile host can swap two objects and the clone accepts both silently. I reproduced it.
- **A2** — a vault can carry `.git/**` and `.sg_vault/**` paths, `sgit clone` writes them
  into the victim's directory, and tracked-wins now keeps them tracked. Also reproduced.

Neither is a reason to unwind the branch. A1 needs one line to become visible and a decision
to become closed; A2 needs a five-line exemption list.

## What I verified myself

| Check | Result |
|---|---|
| `pytest tests/unit/ -n auto` | **3796 passed** in 107s — the debrief's number is real |
| `pytest tests/qa -q` | **121 passed, 20 skipped** — also real |
| P0 regression suite is vault-level, not a stub | Confirmed — real vaults, real push, plus the converse and the deliberate-deletion case |
| Tracked-wins lives in the engine, all walk sites load it | Confirmed — 9 call sites |
| Publish takes no target argument | Confirmed from `--help` |
| Mirror honours SP-3 | Confirmed — content-address decides; a manifest hash can only ever yield `host-attested` |
| Docs-page CSP | Confirmed — `connect-src 'self'` present in both modes |
| Loader placeholder claims nothing it does not do | Confirmed |
| No model identifiers in code | Confirmed |

## A1 — SP-1 is bypassable on every vault (High)

`Vault__Verified_Write.verify` falls back to "does it AES-GCM-authenticate under the read
key?" whenever the content-address check fails **and a read key is present** — which is every
clone, fetch and pull. The debrief (§6) describes this as inherent to `sgit vault move`'s id
reuse. It is not scoped to moved vaults: it is unconditional, so **I7 is downgraded from
content-addressed integrity to "authenticates under the key" for every reader**.

Reproduced end-to-end against a real HTTP host, on a vault that was never moved — two
authentic ciphertexts swapped between their ids:

```
honest clone   : allowlist.txt: 'ALLOW: alice\n'
                 denylist.txt : 'DENY: mallory-was-here\n'

swapped obj-cas-imm-14d3b930286b <-> obj-cas-imm-5a8c4672ca57

hostile clone  : allowlist.txt: 'DENY: mallory-was-here\n'
                 denylist.txt : 'ALLOW: alice\n'
```

Both objects failed their content-address check. Both were accepted, written, and **no
warning was printed**. This is the rollback/substitution class decision 16 exists for, except
it needs no key and survives a reader who has one.

**QA's I7 cell does not catch it** — it serves bytes that cannot authenticate under any key,
so the fallback never engages. The suite is green and the criterion is satisfied in letter,
not substance.

Options, cheapest first:

1. **Make it visible today.** When the fallback rescues an object, count it and print once:
   *"N objects did not match their content address; accepted because they authenticate under
   your key — expected only for a vault that has been moved."* One line, no protocol change,
   and a hostile host stops being silent.
2. **Gate it.** Record a marker at move time (`move` records nothing today — I checked) and
   allow the fallback only for vaults that carry it.
3. **Close it.** Have `move` rewrite object ids, restoring the CAS invariant. Protocol change;
   decision-16 adjacent.

I would ship 1 now regardless of which of 2/3 is chosen, and add the swap case to the hostile-host
fixture.

## A2 — structural directories are not exempt from tracked-wins (High, chained)

Tracked-wins is implemented as git's rule — *ignore rules govern untracked files only* — and
applied to **all** rules, which is what the pack told it to do. But git does not merely
*ignore* `.git`; it **refuses** it. The same is true here for `.sg_vault`: those two are
structural invariants, not preferences, and they now yield to a tracked path:

```
.sg_vault/local/vault_key  -> should_ignore_file: False   (reason: 'tracked')
.git/hooks/pre-commit      -> should_ignore_file: False
```

The chain, verified:

1. A vault head **can** carry such paths — `write_file` accepts `.git/hooks/pre-commit` and
   `.sg_vault/local/…` with no structural check (pre-existing).
2. **`sgit clone` writes them into the victim's directory.** Confirmed both:
   `.git/hooks/pre-commit -> True` (code execution on the victim's next git command) and
   `.sg_vault/local/ATTACKER_MARKER -> True` — attacker-controlled bytes inside the clone's
   own key/config directory. Writing `.sg_vault/local/vault_key` through the same path broke
   the vault outright in my test (`ValueError: Invalid vault key format` on every later
   command).
3. **Tracked-wins now keeps them tracked**, so every subsequent walk descends into
   `.sg_vault/` and `.git/` and keeps propagating them.

Steps 1–2 are pre-existing. What changed is reachability and persistence: this branch's
headline feature is *clone a vault from any URL, no auth* — which is exactly how a crafted
vault reaches a victim — and P0 removed the pruning that used to limit the blast radius.

**Fix:** exempt the structural set from tracked-wins — `.sg_vault`, `.sg_vault_new`,
`.sg_vault_old_*`, `.git` — and apply the same refusal in `Vault__Sub_Tree.checkout`, which
today path-guards only against escaping the directory, not against writing *into* the vault's
own internals. `Vault__Path_Guard` cannot help: these paths are inside the destination.

## A3 — `--bind` disables the DNS-rebinding defence (Medium)

`_Serve_Handler._host_header_allowed` returns `True` unconditionally when the bind address is
not loopback. That is backwards: a rebinding attack against the operator's browser gets *more*
useful once the server is reachable off-host, and the printed warning at startup does not
defend the browser. Keep the check when widened — allow loopback plus the configured
host/IP — rather than dropping it.

## A4 — local static reads are not path-guarded (Low)

`Vault__API__Static._fetch` and `presigned_read_url` join a manifest-supplied `file_id` onto
the folder root with plain `os.path.join`. A hostile manifest with `../../…` reads outside the
served folder. Read-only, and the bytes are then verified/decrypted and discarded, so impact
is slight — but mirror guards the write side (SP-8) and the read side should match.

## A5 — non-404 HTTP status raises a bare `RuntimeError` (Low)

`_fetch` raises `RuntimeError` for any non-404 status, outside the typed transport-error
hierarchy, and aborts the run rather than failing soft per object. A 403 from a
misconfigured host will read as a crash rather than a diagnosis.

## A6 — the tracked-wins safety net fails open (Note, not currently reachable)

`Vault__Head_Paths.paths` catches every exception and returns an empty set, which silently
disables tracked-wins and restores the deletion hazard P0 exists to prevent. I tried to reach
it (corrupted a tree object): `status` fails loudly with `FileNotFoundError` in the same
scenario, so the two fail together and the hazard does not materialise. It holds by
coincidence rather than by construction — worth an assertion pinning it.

## Judgement calls I checked and agree with

- **Tracked-wins in the engine, not at a call site** — correct, and my spec was wrong about
  the call site. The r15 correction is accurate.
- **`Vault__Static_Server` in `core/serve/`** — correct; the layer rule beats my file path.
- **No `Schema__OpenAPI_Document`** — correct; an externally-specified nested-map format is
  not what Type_Safe schemas are for, and generating from the same enumeration prevents drift.
- **`cover.json`'s `updated` from the head commit** — necessary for determinism, and the
  reasoning is right.
- **I6 excluding `local/config.json`** — the visibility record has to live somewhere per-clone;
  disclosed rather than hidden.
- **Mirror's three-way verdict** (`verified` / `host-attested` / `refused`) — better than the
  spec asked for, and it is the vocabulary A1 should adopt.

## What is still owed (agreed, not findings)

P8 and cells 6/12 (deferred by decision 11); cells 5/10 (real Pages run); cell 8 and the real
loader JS (Web team); decision 15's workflow generator; read-write `attach` branch
registration; the integration suite (needs the 3.12 venv); decision 16.

## Recommended order

1. A1 option 1 (the warning) — one line, removes the silence.
2. A2 — the structural exemption list plus the checkout refusal.
3. A3, A4, A5 — small and independent.
4. A1 option 2 or 3 — needs a maintainer decision; belongs with decision 16.
