# CLI Response — v0.33.5 branch-index fix: VERIFIED against live CLI code

**To:** the Vault Web team (Dev / Architect)
**From:** SGit-AI CLI team (Claude Code web session)
**Date:** 2026-06-08
**Re:** `v0.33.5__debrief__sgit-interop-branch-index-wire-reference.md` (your round-2 follow-up)
**Supersedes the verdict in:** `cli-response__round-2-web-index-payload-bugs.md`

---

## TL;DR

**Your v0.33.5 fix is correct. Approved.** I ran your exact documented payload, derivation, and
crypto envelope through the CLI's *real* code (not a re-read of the doc) — every check is green, and
§3/§4 match the CLI byte-for-byte. Both round-1 bugs are closed. **With this deployed, the CLI's
existing clone path consumes the index unchanged — no CLI change is needed for clone to work.**

One thing remains open and it's ours: the §8 graceful-degrade hardening is **not yet shipped**, and I
*proved* the gap (a present-but-malformed index still crashes `load_branch_index`). That's the next
CLI deliverable.

| Concern | State |
|---|---|
| Index payload `name:"current"` resolves via `get_branch_by_name` | ✅ verified end-to-end |
| Index payload `branch_id` (opaque hex) passes `Safe_Str__Branch_Id` | ✅ verified |
| `branch_id` derivation (§3) = `idx-pid-muw-` tail | ✅ matches CLI byte-for-byte |
| Crypto envelope (§4) `IV(12) ‖ AES-256-GCM(read_key,…)` | ✅ matches CLI byte-for-byte |
| End-to-end `load_branch_index` → `get_branch_by_name('current')` → named ref | ✅ verified |
| CLI graceful-degrade hardening (§8) | 🔴 **pending (ours)** — gap proven below |
| `display_name` (§7) field | 🟡 recommended, not yet added |
| Interop contract v0 (Option A) | 🟡 ready to draft |

---

## 1. What I verified — empirically, against the real CLI

I fed your §5 `test-vault-1` fixture and §3/§4 claims through the actual CLI classes
(`Schema__Branch_Index`, `Vault__Branch_Manager`, `Vault__Crypto`, `Safe_Str__Branch_Id`). Results:

```
[1] Schema__Branch_Index.from_json(your §5 fixture)
      ✓ round-trip invariant holds          (from_json(x).json() == from_json(x).json())
      ✓ schema == branch_index_v1

[2] Vault__Branch_Manager.get_branch_by_name(index, 'current')
      ✓ resolves                            (was None when name=='main' — round-1 Bug B)
      ✓ head_ref_id -> ref-pid-muw-da0dea46b649
      ✓ branch_id   == branch-named-b69ec449a18c
      ✓ branch_type == named

[3] Safe_Str__Branch_Id
      ✓ 'branch-named-b69ec449a18c' accepted
      ✓ 'branch-named-main'        rejected  (round-1 Bug A guard is real)

[4] Crypto envelope
      ✓ layout = IV(12) + ciphertext + GCM tag(16)
      ✓ crypto.decrypt(crypto.encrypt(x)) == x

[5] §3 derivation determinism
      ✓ idx-pid-muw-<tail> and branch-named-<tail> share the SAME 12-hex tail

[6] END-TO-END: Vault__Branch_Manager.load_branch_index (decrypt -> parse -> lookup)
      ✓ yields the named ref ref-pid-muw-da0dea46b649
```

### The two interop claims you asked me to confirm — both exact

- **§3 derivation** maps onto `Vault__Crypto.derive_file_id` (`sgit_ai/crypto/Vault__Crypto.py:65`):
  ```python
  def derive_file_id(self, read_key, domain_string):
      mac = hmac.new(read_key, domain_string.encode(), hashlib.sha256).hexdigest()
      return mac[:12]
  ```
  with `domain = "sg-vault-v1:file-id:branch-index:{vault_id}"` (`:74`) and the `idx-pid-muw-` prefix
  added by callers (`Vault__Transfer.py:77`). Your `branchIndexFileId` and `branch_id` formulas are
  **byte-for-byte** this. The "spot-check" property (id and file share the hex tail) holds.

- **§4 envelope** maps onto `Vault__Crypto.encrypt/decrypt` (`:199-210`): `iv(12) + AESGCM(read_key).encrypt(iv, pt)`,
  decrypt slices `[:12]`/`[12:]`. `GCM_IV_BYTES == 12`. Identical to the ref envelope you already
  interop with. **A branch-index byte-vector test is structurally your ref vector with a different
  plaintext — confirmed.**

So your "the index deserves an explicit byte-vector test like the ref vectors" is answered: the
envelope and the file-id derivation are the *same functions* the refs use; an index vector built from
the §2 plaintext will pass iff your ref vectors pass (they do).

---

## 2. The fix is correct — and the CLI already consumes it

`Schema__Branch_Meta` (`sgit_ai/schemas/Schema__Branch_Meta.py`) maps your payload cleanly:
`branch_id`, `name`, `branch_type` (default `NAMED`), `head_ref_id` — and every field you omit
(`created_at`, `public_key_id`, `private_key_id`, `creator_branch`) is optional/nullable, so the
single-named-branch payload parses with no churn. `created_at` defaults to `Timestamp_Now(0)` and the
field comment already documents it accepts int-ms **and** ISO-8601 — so your deliberate omission is
fine.

`Step__Clone__Download_Index` (`:49-57`) takes the present-index branch verbatim:
`load_branch_index` → `get_branch_by_name(index, 'current')` → `head_ref_id`. With your `name:"current"`
that now resolves. **No CLI change required for the happy path.**

---

## 3. Open CLI item — §8 hardening is still pending, and here's the proof

You endorsed (and I offered) making the clone step degrade a malformed/foreign index to the
absent-index fallback. It is **not yet implemented**, and the gap is real. I fed a malformed index
(your round-1 `branch_id:"branch-named-main"`, `name:"main"`) into the *real* `load_branch_index`:

```
[7] present-but-malformed index
      ✗ load_branch_index RAISES:
          ValueError: in Safe_Str__Branch_Id, value does not match required pattern:
                      ^branch-(named|clone)-[0-9a-f]{8,64}$
      -> Step__Clone__Download_Index:52 has no guard around load_branch_index /
         get_branch_by_name, so clone would CRASH rather than fall back.
```

That's the "interop bug = user-facing crash" class. The fix (ours): wrap the present-index branch so
that **`load_branch_index` raising, OR `get_branch_by_name('current')` returning None**, degrades to
the existing single-branch fallback (`_fallback_single_branch`) with a log line — turning any future
drift (a CLI schema bump, a web field we add, a partial write, a foreign index) into a graceful
fallback instead of a crash. This is belt-and-braces with your pinned tests + wire fix. **We'll ship
it.** (Not in this round — flagged so it's tracked and owned.)

---

## 4. `display_name` (§7) — agreed, recommend adding

A clean, additive, optional field. Adding `display_name : Safe_Str__Branch_Name = None` to
`Schema__Branch_Meta` lets the web show "main" without ever touching the wire `name` — which
pre-empts exactly how round 2 happened (a friendly-label desire leaking into the lookup key). The CLer
already tolerates unknown fields, so this is purely about making the label *first-class and pinned in
the contract*. We'll add it alongside the contract.

---

## 5. Interop contract v0 (Option A) — ready to draft

Everything the contract needs to pin is now verified against live code, so we can draft v0 with
confidence and citations:

| Field | Rule | CLI source (verified) |
|---|---|---|
| `schema` | `"branch_index_v1"` | `Schema__Branch_Index.schema` |
| `branch_id` | `^branch-(named\|clone)-[0-9a-f]{8,64}$`; opaque; web derives from index file-id tail | `Safe_Str__Branch_Id` |
| `branch_type` | `"named" \| "clone"` | `Enum__Branch_Type` |
| `name` (wire) | named branch MUST be `"current"` | `get_branch_by_name(...,'current')` |
| `display_name` (NEW) | human label; never used for lookup | to add to `Schema__Branch_Meta` |
| `head_ref_id` | the **named** ref only | rule we both follow |
| `created_at` | ISO-8601 **or** int-ms; web omits | `Schema__Branch_Meta.created_at` (`Timestamp_Now`) |
| index file id | `idx-pid-muw-` + `HMAC-SHA256(read_key,"sg-vault-v1:file-id:branch-index:{vault_id}")[:12]` | `derive_branch_index_file_id` + `derive_file_id` |
| crypto envelope | `IV(12) ‖ AES-256-GCM(read_key, IV, plaintext)` | `Vault__Crypto.encrypt/decrypt` |
| path | `bare/indexes/{index_file_id}` | `Step__Clone__Download_Index:44` |

Plus your requested **reference-payloads appendix** — the §2 single-named-branch plaintext as a literal
fixture both sides paste into a test (the CLI side is exactly the JSON I verified in §1 above). We'll
draft, you mark up.

---

## 6. Next steps, by owner

| # | Step | Owner |
|---|------|-------|
| 1 | Deploy v0.33.5 so the conformant index is live | Web/DevOps |
| 2 | Ship `Step__Clone__Download_Index` graceful-degrade hardening (malformed/foreign → fallback) | **CLI** |
| 3 | Add `display_name` to `Schema__Branch_Meta` | **CLI** |
| 4 | Draft interop contract v0 (+ reference-payloads appendix) | CLI drafts, Web marks up |
| 5 | Run the 3 live checks (create→clone no-fallback; CLI push→web shows it; web edit→CLI push→keep+flag) | both |
| 6 | Unblock the Access-Key path for `test-vault-1` end-to-end | Web/Server |

Items 2–4 are queued on our side and ready to go on your word.

---

## Evidence index

- Live verification script: parse/round-trip/lookup/regex/envelope/derivation/end-to-end — all green
  except the (intended) demonstration that a malformed index crashes `load_branch_index`.
- `sgit_ai/schemas/Schema__Branch_Index.py`, `Schema__Branch_Meta.py` — the schema your payload satisfies
- `sgit_ai/storage/Vault__Branch_Manager.py:87` (`load_branch_index`), `:100` (`get_branch_by_name`)
- `sgit_ai/crypto/Vault__Crypto.py:65` (`derive_file_id`), `:73` (`derive_branch_index_file_id`), `:199-210` (`encrypt`/`decrypt`)
- `sgit_ai/workflow/clone/Step__Clone__Download_Index.py:49-57` (present-index path), `:80-120` (absent-index fallback)
- Companion briefs: `team/humans/dinis_cruz/claude-code-web/06/08/cli-response__round-2-web-index-payload-bugs.md` (+ the two round-1 briefs)
