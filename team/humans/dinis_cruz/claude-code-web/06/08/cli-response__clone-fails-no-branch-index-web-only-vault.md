# CLI Response (follow-up) — `sgit clone` fails with "No branch index found" on a web-created vault

**To:** the SG/App + sg-vault loader team
**From:** SGit-AI CLI team (Claude Code web session)
**Date:** 2026-06-08
**Re:** `sgit clone <key>` → "No branch index found on remote" on `test-vault-1` (`7y6uk6gj`)
**Companion to:** `cli-response__open-loads-clone-branch-shadows-cli-pushes.md` (same date) — **share the two together**

---

## TL;DR

`sgit clone` of a vault that was created/edited **only in the SG/App web UI** failed with:

```
error: No branch index found on remote — is this a valid vault?
```

even though the vault opens fine in the web UI.

This is the **same two-ref-model family** as the companion brief, seen from the other end:

- The web UI writes its working state to the **clone** branch and advances the **named** ref
  (`ref-pid-muw-*`) only on **Publish/Push**. It also does **not** write a CLI-format **branch
  index** (`idx-pid-muw-*` at `bare/indexes/`) at all.
- The CLI's clone pipeline **required** the branch index and raised hard when it was missing —
  instead of falling back to the deterministic named ref, which the protocol docs said it should.

**Two sides, two owners:**

| Side | Issue | Owner | Status |
|---|---|---|---|
| CLI | Hard-errored on a missing branch index instead of the documented single-branch fallback; also masked a possible 403 as "no index" | **this repo** | **Fixed (shipped below)** |
| Web | Doesn't write the named ref / branch index until Publish; index path is `bare/idx/` vs CLI `bare/indexes/` | SG/App | Recommendations below |

The CLI fix is shipped. The web-side items determine whether *unpublished* web vaults are clonable at all.

---

## Symptom

```
sgit clone k36563x3d153c6w562b2s5i6q6e24r4t5x38r3f:7y6uk6gj patient-vault-1
  ▸ Deriving vault keys
  ▸ Downloading vault index
error: No branch index found on remote — is this a valid vault?
```

The web UI opens the same vault without error (it reads the **clone** branch preferentially — see
the companion brief).

---

## Diagnosis — three facts (all verified locally)

### 1. Key derivation is correct (ruled out as the cause)

We ran the CLI's own derivation against the vault key and compared to the READ KEY shown in the web
Vault Settings panel:

```
vault_key             : k36563x3d153c6w562b2s5i6q6e24r4t5x38r3f:7y6uk6gj
read_key (CLI-derived): 1c015c84df0a54eb01fa7fd2e120e6c3a4bbdc3f5cc0414445a5ddd36232387e
read_key (web UI)     : 1c015c84df0a54eb01fa7fd2e120e6c3a4bbdc3f5cc0414445a5ddd36232387e
match                 : True
```

Bit-for-bit identical. This is **not** a key-format / parse problem.

### 2. The CLI computes the right ids for this vault

```
branch_index_file_id : idx-pid-muw-b69ec449a18c     (looked up at bare/indexes/…)
named ref id         : ref-pid-muw-da0dea46b649      (deterministic, HMAC-derived)
```

### 3. The branch index is simply absent on the server

`bare/indexes/idx-pid-muw-b69ec449a18c` returns no payload, and the old CLI code raised immediately
(`Step__Clone__Download_Index`) with **no fallback**. That is consistent with a vault that has only
ever been touched by the web UI, which does not write the CLI-format branch index.

### Bonus gap found: "No branch index" could also mask a 403

`Vault__API.batch_read` collapses per-file **404 (not_found)**, **403 (forbidden)**, and transient
errors all into `payload = None` unless a `failures` dict is passed — and the clone step passed none.
So the message "No branch index found" was also being shown for **access-denied** (403) cases — e.g.
a vault that requires an **Access Key** (note `test-vault-1` has an Access Key field). The fix below
distinguishes these.

---

## Why this is the same family as the companion brief

From the companion brief's analysis of the web two-ref model:

- `_commit()` writes the **clone** ref (`ref-pid-snw-web-ui`) — the web's working store.
- `push()` (Publish) advances the **named** ref (`ref-pid-muw-*`).
- The web never writes the CLI-format branch index.

So a web vault that was **edited but never Published** has:

```
ref-pid-snw-<hmac(read_key, vault_id, 'web-ui')>   → populated (all the web work)
ref-pid-muw-*                                       → absent  (named branch never advanced)
idx-pid-muw-*  (bare/indexes/)                      → absent  (web doesn't write the CLI index)
```

The companion brief's symptom was **silent shadowing** on a shared vault. This brief's symptom is a
**hard clone error** on a web-only vault. Same root behavior (clone branch is the web's primary
store; named branch is publish-only), different CLI code path.

This exact interop gap was **predicted** in `team/.../04/16/vault-docs-review-part-1-protocol-and-interop.md`,
Finding 3:

> | Single-branch vault (no branch index) | No impact — **both clients 404 and fall back to the
> HMAC-derived `refFileId`** |

The fallback was specified but **never implemented in the clone pipeline**. The same review also
flagged the **path mismatch**: the web reads/writes the index at `bare/idx/`, the CLI at
`bare/indexes/` — so even a web-written index would be invisible to the CLI.

---

## The fix (shipped in this repo)

`sgit_ai/workflow/clone/Step__Clone__Download_Index.py` — implements the documented single-branch
fallback and stops masking 403s:

1. Read the branch index **with a `failures` dict** so absent (404) vs forbidden (403) is known.
2. **Index present** → unchanged behavior (multi-branch / v2 vault).
3. **Index absent (404)** → derive the deterministic named ref
   (`ref-pid-muw-' + derive_ref_file_id(read_key, vault_id)`) and:
   - if the named ref **exists** → synthesise a single-branch index (`'current'` → that ref),
     persist it locally, and let the remaining clone steps run unchanged → **clone succeeds**;
   - if the named ref is **also absent** → a clear, actionable error (below) instead of "No branch index".
4. **Index forbidden (403)** → an explicit access-denied error (check Access Key / credentials),
   never masked as "no branch index".

New "nothing published" error (covers both the wrong-key case and the unpublished-web-vault case):

```
Nothing to clone: this vault has no branch index and no named ref (ref-pid-muw-…) on the server.
  Two common causes:
    1. The vault key or ID is incorrect — double-check the value you pasted.
    2. The vault was created/edited only in the SG/App web UI and never Published.
       Web edits live on the (unpublished) clone branch, not the named branch the CLI clones.
       Open the vault in the web UI, click Publish/Push, then re-run sgit clone.
```

**Tests:** `tests/unit/workflow/clone/test_Step__Clone__Download_Index__Fallback.py` (7 new) — real
in-memory vault, index deleted from the store to reproduce the web-only case:
clone-succeeds-via-fallback, synthesises the deterministic named ref, persists the local index,
clear error when index+ref both absent, and the 403-honesty guard. Full suite: **3770 passed**.

### Deliberate non-goal (keeps the companion brief's risk closed)

The CLI fallback uses the **named** ref only. It does **not** read the web's clone branch
(`ref-pid-snw-web-ui`). Cloning the clone branch would resurrect the silent-shadowing /
named-vs-clone divergence described in the companion brief. The named branch stays canonical; the CLI
tells the user to Publish rather than quietly cloning unpublished web state.

### What this means for `test-vault-1`

- If it was Published at least once → `sgit clone` now **succeeds** (named ref present, index synthesised).
- If it was never Published → `sgit clone` now gives the **clear "open in web and Publish"** message
  instead of the cryptic one. Strict improvement either way.

---

## Recommendations for the SG/App team

1. **P1 — Write the named ref + branch index on vault creation (or first web commit), not only on
   Publish.** This makes a web-created vault immediately clonable and visible to CLI/agents, and
   removes the "edited but never Published → invisible to CLI" cliff. (Even a single-branch index at
   the agreed path would do.)
2. **P1 — Align the branch-index path.** Web `bare/idx/` vs CLI `bare/indexes/` (04/16 Finding 3).
   Pick one; until then, multi-branch vaults are not interoperable.
3. **P2 — Access Key interop.** If a vault requires an Access Key, the CLI needs a documented way to
   pass it on clone/read. Today a 403 from an access-gated vault was indistinguishable from "no
   index" (now fixed on our side to report 403 honestly, but the CLI still needs the credential path).
4. **P2 — Surface Publish state in the UI.** A "this vault has unpublished web edits / not yet
   published to the named branch" hint would pre-empt the "I cloned and got nothing" confusion (ties
   into the companion brief's HUD/ahead-behind recommendation).

---

## Repro & verification

- **Reproduced** in-memory: build a real vault, delete `bare/indexes/*` from the store, run the clone
  workflow → old code raised "No branch index"; new code clones via the named-ref fallback. (See the
  new test file.)
- **Key derivation** verified live against the web-shown READ KEY (match, above).
- **Live-server end-to-end** for `test-vault-1` needs either the Access Key (the vault appears to be
  access-gated) or the vault to be Published first — both covered by the recommendations above.

---

## Evidence index (CLI repo paths)

- `sgit_ai/workflow/clone/Step__Clone__Download_Index.py` — the fix (single-branch fallback + 403 honesty)
- `sgit_ai/network/api/Vault__API.py:126-163` — batch_read collapses 404/403/transient unless `failures` passed
- `sgit_ai/crypto/Vault__Crypto.py:69-79` — `derive_ref_file_id` / `derive_branch_index_file_id`
- `tests/unit/workflow/clone/test_Step__Clone__Download_Index__Fallback.py` — 7 new tests
- `team/humans/dinis_cruz/claude-code-web/04/16/vault-docs-review-part-1-protocol-and-interop.md` — Finding 3 (the documented fallback + path mismatch)
- `team/humans/dinis_cruz/claude-code-web/06/08/cli-response__open-loads-clone-branch-shadows-cli-pushes.md` — companion brief
