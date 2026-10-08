# Compatibility matrix: sgit CLI × vault web UI × SG/Send API, across the integrity roll-out

**Date:** 7 Oct 2026 · **Rule we hold:** a vault written by any client version stays readable
and writable by every other version in use. A newer client may *lose* nothing that an older
client does not already lose today (the web UI's single-entry index overwrite is the baseline
loss), and must never *break* an older client that is still writing. The API does not change
in any step below (Q1 answered: it is id-agnostic).

## 1. What ships now (on the branch, no cross-version effect)

| Change | Old CLI (≤ 0.18.0) on the same vault | Today's web UI on the same vault | API |
|---|---|---|---|
| `fsck` dedupe (270 s → 12 s) | local only | n/a | none |
| whole-vault guard names `sgit dev dump` | n/a | n/a | none |
| **canonical (JCS) signing input** | reads the commit as before; nothing verifies, so the changed bytes are invisible | same; it never reads `signature` | none |
| **`author_key_id` on new signed commits** | the field has been in `commit_v1` since March 2026 (`Safe_Str__Author_Key_Id`, `key-rnd-imm-…` matches); older CLIs parse it; any client without the field drops it on read | ignores it | none |
| interop vectors (fixtures) | n/a | gives them something to test against | none |
| website debrief, notes, briefs | n/a | n/a | none |

**Verdict: merge and release as 0.18.x or 0.19.0 with no coordination.** One property to
state in the release note: `vault move` re-encrypts and re-ids every commit, so signatures
made before a move do not verify after it (they never did; it only becomes visible once
verification exists). Move re-signs its own sentinel.

## 2. Next CLI batch (0.19): safe with today's web UI, degrades gracefully with old CLIs

| Change | Effect on an old CLI writing the same vault | Effect with today's web UI | Loss vs today |
|---|---|---|---|
| **Gate fields in the index** (`format`, `min_client`, `features`), read and preserved; written only by an owner command | an old CLI's push re-uploads its local index from a Type_Safe object that **dropped the unknown fields**, so the gate is erased by the next old-CLI push. **Fails open** (vault reads as format 1 again), never closed | the web UI's single-entry overwrite erases it the same way | none: a gate that is erased leaves the vault exactly as today |
| **`pull` / `status` re-read the remote index and merge entries** | old CLI unaffected (still reads its local copy) | after a web overwrite the new CLI merges its local entries back in and re-uploads, so the mapping is **restored** rather than lost | none; a gain when a new CLI pulls |
| **Index upload with `write-if-match` + merge-retry** | old CLIs keep blind writes; last-writer-wins remains between them, as today | web overwrites still win when they come last, as today | none |
| **Signature verification, warn mode** | read-only; no writes | read-only | none, but see noise below |
| **Hint fix** on the pattern-mismatch error ("run `sgit update`") | applies only to clients that have it | n/a | none |
| **`migrate apply` refuses on signed history** without `--force`, re-signs with it | old CLIs can still run the old migration; it rewrites history exactly as it does today | n/a | none |

**Noise, not breakage:** on the collaboration vault today, 247 of 674 commits verify, 315 have
no key mapping and 112 are unsigned (web UI and keyless clones). Warn mode must therefore be
quiet by default: a summary line in `sgit check fsck` and `history log --verify`, never a
warning per pull. Otherwise agents will learn to ignore it before it means anything.

## 3. Gated steps (need the other teams first; shipping them early would break the rule)

| Change | What breaks without the other side | Who must ship first |
|---|---|---|
| **Ref monotonicity** (0.20) | today's web UI pushes the named ref unconditionally and can drop another writer's commits; a monotonic CLI reports each one as a rollback. True, but a stream of alarms | web shells on `pushIfMatch()` with a reconcile step |
| **Signatures `required`** | every web commit fails policy (unsigned); 427 of 674 historic commits on the example vault can never pass | per-device web keys registered in the index; a checkpoint rule for history |
| **Format 2 (32-hex ids)** | **the one hard break:** any CLI ≤ 0.18 fails on a 32-hex id. Correction (8 Oct, reproduced): not a validation error; verify-before-write refuses the object, so a fresh clone reports `integrity check refused vault data … corrupt or substituted content` and a pull reports `missing file … try sgit check fsck`, both pointing at the wrong fix (`sgit update` is the fix). Today's web UI reads them fine but writes 12-hex ids for new objects (mixed, allowed) | web `computeObjectId` format-aware; old web releases retired; and, on our side, no pre-gate CLI still writing to vaults that are raised |

## 4. The matrix

API unchanged throughout. Cells read: what happens to a vault that both clients write.

| | **Web UI today** (single-entry index overwrite, random-IV trees, unconditional push, 12-hex ids) | **Web UI with the index fix** (read-merge-CAS, honours the gate) | **Web UI id-aware** (+ format-aware ids, deterministic trees, `pushIfMatch`) |
|---|---|---|---|
| **CLI ≤ 0.18.0** | today. Index mapping lost on each web push; tree ids differ per writer; lost updates possible on web push | mapping kept; otherwise as today | as today for this client; it **crashes on a format-2 vault** |
| **CLI 0.18.x / 0.19** (canonical signing, author_key_id, gate read+preserve, pull merges index, CAS upload, warn) | works. Gate erased by web pushes → fails open; new CLI restores mapping on its next pull; warn-mode counts are noisy | works. Gate holds; mappings hold; verification covers all new CLI commits | works. Verification covers web commits too once they sign |
| **CLI 0.20** (+ ref monotonicity) | works, but web lost-updates surface as rollback warnings (correct, noisy) | same noise until `pushIfMatch` | clean |
| **CLI format-2-aware** (+ 32-hex ids on raised vaults) | raised vaults: web reads fine, writes 12-hex ids (mixed, fine), **erases the gate** → an old CLI may then be let in and crash | raised vaults hold their gate; old CLIs refused by name only if they are ≥ 0.19, older ones crash | clean |

## 5. The two scenarios behind the question

**"A vault pushed by the new CLI must work in the old web UI and the old CLI."** It does, for
everything in §1 and §2. Nothing in those batches writes a byte an old reader cannot parse:
`author_key_id` is an existing field, the gate fields are dropped by old readers, the index
merge produces the same schema, canonical signatures are opaque base64 to everyone. The only
future write an old reader cannot parse is a 32-hex object id, and that is §3, gated.

**"It is fine if the web UI overwrites and we lose a little mapping."** Agreed, with the
precise statement of the loss: the web overwrite loses *other branches' index entries*, which
is what it loses today, and from 0.19 the next CLI pull restores them. Two things it must not
be allowed to lose silently: a *raised* gate (so raising a vault to format 2 waits for the web
index fix) and a *required* signature policy (same). Both fail open rather than closed, so the
failure mode is "back to today", never "vault unusable".

## 6. Order, with the dependency each step actually has

1. **Now:** merge the branch; release. No dependency.
2. **0.19:** gate (read/preserve/owner-write), pull index refresh and merge, CAS index upload,
   warn-mode verification in `fsck` and `history log --verify`, hint fix, migrate guard. No
   dependency: everything fails open against today's web UI and old CLIs.
3. **Web index fix ships** (their §3.1). From then on gates and mappings hold.
4. **0.20:** ref monotonicity, after the web shells use `pushIfMatch`.
5. **Format 2:** after the web `computeObjectId` change and once the fleet of CLIs writing to a
   vault is ≥ 0.19 (the gate can refuse by name only from 0.19 up). Raise vaults one at a time.
6. **`required` signatures:** after per-device web keys.
