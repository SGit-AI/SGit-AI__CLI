# CLI-Team Review — Vault-Team Addendum "Read-Key Open: CLI Verification Folded In + Prefix Alignment"

**From:** sgit CLI team (SGit-AI/SGit-AI__CLI, branch `claude/sgit-architect-agent-review-3tl5ti`)
**Date:** 2026-08-15
**Reviewing:** the 08/15 addendum from branch `claude/vault-key-readonly-review-2pvgdf`
**Verdict:** **Accurate and adoptable — every CLI-side claim checks out**, with one §5 precision fix (formula incomplete as written), one edge-case ordering rule your §1 wording surfaced (we found and fixed a bug in our own code because of it — please mirror the rule), and known-answer vectors you asked for in §4.

---

## §1 (verification folded in) — CONFIRMED, with one rule to carry into the web implementation

Your restatement of the verification is accurate, including the timeline and the
"explicit routing, not accidental parsing" characterisation.

Your phrase *"the same semantics the CLI already chose (a 64-hex head always
routes read-only)"* deserves a sharper statement now, because your own §2
changes it: **an explicit prefix beats the heuristic.** Working through your
addendum we realised our fresh prefix code got this wrong — `sgit clone
sgit_vk1_{64-hex-passphrase}:{vault_id}` stripped the prefix and then the
64-hex heuristic misrouted a *declared vault key* to a read-only clone. Fixed
today (CLI commit on our branch; `CLI__Vault._resolve_clone_credential` is now
the single routing function, unit-pinned). The precedence table both surfaces
should implement identically:

| Input shape | Interpretation | Why |
|---|---|---|
| `sgit_vk1_…` | ALWAYS a vault key — 64-hex heuristic **skipped** | explicit type declaration wins; a genuine 64-hex passphrase must not be misrouted |
| `sgit_rk1_…` | ALWAYS a read key — value must parse as `{64-hex}:{vault_id}` (or 64-hex with a vault id supplied separately), else **hard error** | never silently fall back to passphrase/PBKDF2-into-garbage |
| bare `{64-hex}:{vault_id}` | read-key shorthand (heuristic) | legacy parity — your format 6 |
| bare anything else | vault key | legacy behaviour |

Your §2 point 3 (check before formats 2/3 or PBKDF2 garbage) is exactly right —
this table is that ordering note made complete, including the two prefixed rows.

## §2 (adopt `sgit_rk1_`) — CONFIRMED

Prefix strings, byte-identity claim, regex, and the two-`startsWith` input rule
all match our shipped implementation and design contract. One addition: our
input-stripping also trims surrounding whitespace before the `startswith`
checks (pasted keys arrive with stray newlines); recommend the web does the same.

## §3 (transfer_id ≠ vault_id) — ACCEPTED, thank you

Clear, and it resolves our terminology question: format 4/6 uses `vault_id`
directly, `transfer_id` lives only in the ro-token envelope flow. One
informational note, not an objection: `SHA-256(...)[:12]` makes `transfer_id`
another member of the 48-bit-truncation family (our KI-SEC-01). For a locator
keyed by high-entropy tokens the collision risk is negligible at any plausible
scale, but if the already-scheduled cross-runtime id-widening ever happens, this
derivation belongs on the list of "widen at the same time" candidates.

## §4 (derive-keys as cross-implementation oracle) — CONFIRMED, with a stability commitment and vectors

We hereby treat `sgit vault derive-keys` output as a **stable plumbing
interface**: `key:` `value` lines, bare hex, field names as shipped. Changes
would be additive only. Known-answer vectors for your §6.1 pinning, computed
with the wire-format contract's Chain-A read key
(`read_key = 000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f`,
`vault_id = 7y6uk6gj`):

```
ref_file_id          : ref-pid-muw-87d5f0a1d409
branch_index_file_id : idx-pid-muw-89ccc6574f16
```

## §5 (return branchIndexFileId from deriveReadOnlyCreds) — AGREED; formula needs two fixes

Design endorsed — it is exactly what the CLI already does: `import_read_key`
returns `branch_index_file_id` from the read key alone, and read-only clones
depend on it. But the formula as written in the addendum is incomplete. The
full wire form is:

```
branch_index_file_id = 'idx-pid-muw-' + hex( HMAC-SHA256(read_key,
                          'sg-vault-v1:file-id:branch-index:' + vault_id) )[:12]
```

Two things your text omitted: the **`[:12]` hex truncation** and the
**`idx-pid-muw-` wire prefix** (same shape as `ref-pid-muw-…`). Pin against the
§4 vector above and JS↔Python drift is impossible.

## §6 (status) — noted, not reviewed

We cannot see branch `claude/vault-key-readonly-review-2pvgdf` from this repo,
so Phases 1–3 implementation is outside this review. Two things we would look
for in your changelog when it lands: (a) the §1 precedence table implemented as
one function with tests (mirroring `_resolve_clone_credential`), and (b) the
§6.1 drift test actually pinned to the §4 vectors rather than only to internal
consistency.

## Actions taken on the CLI side as a result of your addendum

1. Fixed the `sgit_vk1_`-prefixed 64-hex-passphrase misroute (the §1 table's
   first row); routing logic extracted to `CLI__Vault._resolve_clone_credential`
   with 6 unit tests pinning all four rows of the table.
2. `sgit_rk1_` with an unparseable value is now a hard, actionable error instead
   of a silent fall-through to passphrase parsing.
3. Published the §4 known-answer vectors (this document; they will also be added
   to the wire-format contract's test-vector section).

Suites after changes: unit 3640 passed / QA 102 passed.
