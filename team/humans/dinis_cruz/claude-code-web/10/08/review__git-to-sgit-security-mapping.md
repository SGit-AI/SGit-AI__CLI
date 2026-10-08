# Review: "Git security features → sgit: a one-way mapping"

*CLI team, 8 Oct 2026. Review of the research note of the same date, checked against the code,
plus what was built from it (on the branch, for 0.21.0).*

## Verdict

A good, honest map. The framing is right: one direction only, "N/A by model" kept separate from
real gaps, and the ranking puts the structural limit (no server-side enforcement) first. Three
statements are wrong or overtaken, one important gap is missing, and the four easy gaps are now
closed.

## Corrections

| § | The note says | Actually |
|---|---|---|
| 2 | `author_key_id` is "reserved / unused" | **Live since 0.19.0.** Every CLI commit carries it; it names the signing key and marks the canonical (JCS) signing form, and `check verify` uses it. The schema comment still said "reserved", which is what misled the note; the comment is fixed. `author_signature` and `attestations` are the genuinely unused fields |
| 6 | symlink tree entries "unconfirmed; one to verify" | **Closed, N/A by model.** A tree entry is a blob or a tree, nothing else; there is no symlink type and no code that creates one, so a vault cannot plant a symlink to write through |
| 6 | case/Unicode variants of `.git` are a "possible gap" | **Confirmed, and fixed** (see below). Your test was exactly right |

## A gap the note misses

**No per-writer authorisation.** In git hosting, who may push to which branch is decided per user
by the server. In sgit the write key is one per vault and every writer holds it, so authorisation
is all-or-nothing among key holders. Signatures give attribution (who wrote this commit), not
permission (who was allowed to). A key holder can write anything the server accepts: refs,
indexes, objects. The client-side defences (rewind refusal, `signatures-required`, tag signature
checks) detect much of the damage afterwards; nothing prevents it. This belongs next to gap 1 in
the ranking, and it is the real reason "server-side enforcement" matters: the server does not know
which writer is which.

## What was built from the note (branch, all with tests; verified on the live dev API)

| Gap (note's rank) | Now |
|---|---|
| 3. No tags | **`sgit vault tag create/list/show/delete`.** A tag is an immutable object (name, commit, message, tagger key, timestamp) signed over its canonical form, encrypted, content-addressed. Names live only in the encrypted branch index. Verification checks the signature and that the index entry's name equals the signed name, so an entry cannot re-point "v1.0" at another tag's object. Only pushed commits can be tagged; tags move only with `--force`, and pull reports moves. Deletes are tombstones a stale clone cannot undo. Tag names work in `history show/reset`. A 0.20.0 client drops tags from the index on its first push; the next current pull restores them (seen live) |
| 2. No reflog | **`sgit history reflog`**: every local ref move, newest first, local only, capped at 1,000; `history reset <old id>` brings a head back |
| 2. No force-with-lease | **`sgit push --force-with-lease [<commit>]`**: forces only if the remote is where this clone last saw it before the push (or at the commit given), and writes with compare-and-swap. It deliberately ignores the refresh that push itself does first; git's version has a known footgun there (a fetch silently satisfies the lease) |
| 4. `.git` spellings | **Path guard refuses** `.GIT`, `.Git`, `.git.`, `.git `, `GIT~1`, `SG_VAU~1`, `.git::$INDEX_ALLOCATION`, `.g‌it` and the same for `.sg_vault*`, on every platform (the vault may be checked out anywhere). `.github`, `.gitignore`, `src/git`, `notes.git` stay allowed |

Found on the way: `sgit push --force` from a clone that was behind the remote crashed ("object …
is not in the local store") on 0.20.0. Fixed.

## Still open, and why

- **Server-side enforcement and per-writer authorisation** (1 + the missing gap): need the server
  to know writers (per-writer write keys or signed writes the server verifies). An SG/Send API
  design question, not a CLI change.
- **Push certificates / nonces** (5): low value until the server verifies anything; rewind
  detection covers replay for clients that were there before.
- **Notes, attestations, a second signer** (6): the reserved fields can carry them; worth doing
  when there is a review workflow to serve.
- **Format 2 by default** (7): agree in principle. The blocker is clients ≤ 0.18, which cannot read
  a vault with 128-bit ids and say "corrupt", not "update". Make it the default for new vaults
  once 0.19+ is the norm; it is a one-line change in `init`.

## Suggested wording changes for the note

- §2 row 5: "author_key_id is live (0.19.0+); author_signature and attestations are reserved".
- §6: symlink row → N/A by model; case-variant row → Matched (0.21.0).
- §3/§5: reflog, force-with-lease, tags → Matched (0.21.0); signed tags Matched.
- Ranking: add "no per-writer authorisation" beside gap 1.
