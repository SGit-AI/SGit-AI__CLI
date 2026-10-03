# Review — fixes for A1–A6 (`63eded1`, `fe52646`)

**Reviewed:** `000a5fa..fe52646` on `claude/sgit-cli-review-rxll54` (26 files, +1160/−199)
**Against:** `team/explorer/architect/reviews/08/20/v0__review__static-publishing-implementation.md`
and the response at `…/static-publishing/responses/08/20/v0__response__implementation-review.md`
**Date:** 2026-08-20

---

## Verdict

**All six findings are genuinely fixed**, and A1 was taken to the root rather than the cheap
option. I re-ran my own reproductions and audited the new `move` rewrite independently.

| Finding | State | How I checked |
|---|---|---|
| A1 — SP-1 bypassable | **CLOSED** | my probe script now refuses both swapped objects; the substituted content never reaches the working copy |
| A2 — structural dirs | **FIXED** | `.git/hooks/pre-commit` and `.sg_vault/local/*` no longer written on clone; `.github` grandfathering intact |
| A3 — `--bind` Host check | **FIXED** | the IP-literal rule is the correct analysis (see below) |
| A4 — local reads unguarded | **FIXED** | inline containment in `_location`, layer-appropriate |
| A5 — bare `RuntimeError` | **FIXED** | typed `Vault__Static_Object_Error`, fails soft per object, F5 preserved |
| A6 — fail-open | **PINNED** | the assertion I asked for exists |
| Suites | **verified** | 3812 unit passed · 122 passed / 20 skipped |

Three new items below. Only **B1** should block release; **B2** is the migration decision the
response already surfaced, but it is worse than described.

## The `move` rewrite — audited, and I endorse the test reversal

This was the risky change, so I audited a moved vault directly rather than trusting the suite:

```
BEFORE files=5 objects=19 commits=5 bad_ids=0 dangling=0
AFTER  files=5 objects=20 commits=6 bad_ids=0 dangling=0
work tree identical : True      clone of moved vault matches : True
```

Every object verifies against its own id, no tree entry or commit parent dangles, the work
tree is byte-identical, and a fresh clone of the moved vault reproduces it. The +1 object /
+1 commit is the move sentinel, which the suite bounds at one per named branch.

**On the reversed tests — the call was right.** `test_object_ids_are_stable_after_move`
asserted the precise behaviour that caused A1: it protected an *implementation detail* (ids
survive) while claiming to protect an *intent* (no content lost). The replacement asserts the
intent directly, and adds the invariant that was missing. Keeping the old assertion would have
meant keeping the hole. I would have made the same call.

**The linkability point deserves more than a footnote.** A vault and its moved copy previously
shared every `obj-cas-imm-*` id — anyone seeing both stores could correlate them trivially,
which defeats the stated purpose of `move`. That was a real confidentiality weakness in a
product whose pitch is unlinkable identity, and it is now gone. It is arguably a bigger win
than the A1 fix that motivated it.

**A3's reasoning is correct and worth keeping in the comment:** DNS rebinding needs a *domain
name* in `Host`, so allowing IP literals while refusing names defends the operator's browser
on `0.0.0.0` without breaking legitimate LAN access. That is the right shape.

## B1 — a refused tree or commit object crashes the clone with a raw path error (Medium-High)

The per-object fail-soft covers **blobs**. A refused **tree or commit** object has no such
path, so the clone dies inside the workflow:

```
FileNotFoundError: [Errno 2] No such file or directory:
  '…/clone/.sg_vault/bare/data/obj-cas-imm-8b92f3b8a69b'
```

Reproduced by tampering with exactly **one** tree object on a hostile host. The operator is
shown an internal store path and no indication that an integrity check refused anything.

This also means **the new diagnostic never fires in the case it was written for**:

- `_warn_integrity_fallbacks` runs *after* `runner.run(...)`, and this scenario raises inside
  `runner.run` — so the "re-run `sgit vault move` to normalise" text is unreachable exactly
  when the whole store is un-addressed.
- It is routed through `on_progress`, which is `None` for every programmatic caller
  (`_p = on_progress or (lambda *a, **k: None)`), so a library consumer gets silence even on
  the success path. Only the CLI passes a callback.

This is the same failure shape as F5 — a security-relevant condition diagnosing as an
unrelated internal error — which the transport layer already got right. Suggested:

1. Raise a typed integrity error when a refused object is later required, naming the object
   and the remedy, instead of letting `FileNotFoundError` escape.
2. Emit the summary on failure paths too (`finally`, or in the error handler).
3. Fall back to `stderr` when `on_progress` is `None`.

## B2 — the legacy-moved-vault migration is worse than "a manual step" (Medium)

Verified by simulating a store moved by an older sgit (every object re-encrypted in place at
its old id) and cloning it over HTTP: the clone dies with the same raw `FileNotFoundError`, no
remedy text, nothing naming content addresses. With B1 fixed the operator would at least be
told what happened — but two problems remain that the response does not address:

- **The named remedy needs the vault key and a good copy.** "Re-run `sgit vault move`" is a
  *write-side* operation. A read-only consumer of a published legacy vault — precisely the
  audience this whole feature set exists for — has neither, and cannot act on the advice.
- **A published legacy vault is unreadable by any current-version reader**, and the publisher
  may not know. There is no detection on the publish side.

Options: detect-and-normalise on the write side (`sgit vault move` already rewrites — a
`--normalise` that only re-addresses would be a subset), or a read-side allowance gated on an
explicit flag rather than on silence. **Whichever way it goes, it should be decided before
release**, as the response says — I am only raising the severity, and noting that "there is a
diagnostic" is not currently true.

## B3 — the merge fixture contains no merge commit (Low, test gap)

`test_no_content_lost_with_merge_history` and its comment ("a merge commit has TWO parents —
both must be remapped") are the stated coverage for the multi-parent remap. The fixture
creates two **diverged** branches and never merges them, so every commit in it still has at
most one parent: the two-parent path is not exercised.

The code is correct by inspection — `commit['parents'] = [id_map.get(p, p) for p in …]` remaps
all parents, and `parents_of` feeds every parent into the post-order — and the divergent-branch
fixture does usefully cover *multiple roots*. But the assertion currently gives confidence it
has not earned. Add an actual merge to the fixture, or rename the test to what it covers.

## One documentation note

A move now changes **every** object id, so any previously published manifest, bundle or deep
URL for that vault is dead after a move. That is correct and is the point (it is the
linkability fix), but the move UX should say "republish after moving" — a publisher whose
Pages site silently 404s will otherwise reach for the wrong diagnosis.

## Recommended order

1. **B1** — the typed error plus the two delivery fixes. Small, and it makes B2 legible.
2. **B2** — a maintainer decision; do not release without it.
3. **B3** and the doc note — trivial.

Nothing else from v0 remains open.
