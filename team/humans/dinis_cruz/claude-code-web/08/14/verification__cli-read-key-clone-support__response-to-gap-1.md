# Verification — sgit CLI Read-Key Clone Support (response to the Gap-1 / F6 concern)

**From:** sgit CLI team (SGit-AI/SGit-AI__CLI, branch `claude/sgit-architect-agent-review-3tl5ti`)
**Date:** 2026-08-14
**Re:** the claim that "CLI-side support for `sgit clone <64-hex>:<vault-id>` is not confirmed" and that adopting bare format 6 on the web "would create a CLI↔web divergence"

## TL;DR

The premise is now settled, empirically: **the sgit CLI clones read-only from
just a read key + vault id, in three input forms, verified end-to-end against
a real SG/Send server.** The 07/24 review's F6 flagged a *verification gap*,
not an absence — the feature had already been in the CLI for seven weeks when
F6 was written. Adopting bare format 6 on the web creates **parity**, not
divergence.

## How it was verified (not code-reading)

The actual `sgit` binary was driven against a real in-process SG/Send HTTP
server (`Send__User_Lambda__Http_Server`, in-memory storage): create a vault
via the CLI, commit, push, then clone with read-key credentials only. All
four checks passed:

```
A) sgit clone {64-hex}:{vault_id}            → OK: clone_mode = read-only, file content correct
B) sgit clone {vault_id} --read-key {hex}    → OK
C) sgit clone sgit_private_read_{hex}:{vault_id}      → OK  (new prefixed form, see §4)
D) sgit commit on the read-only clone        → refused:
     "error: This vault was cloned read-only. To write, re-clone with the full vault key."
```

The shorthand is explicit routing, not accidental parsing: `CLI__Vault.cmd_clone`
detects a 64-hex head before the colon and routes to `clone_read_only`,
printing `(detected 64-hex read key in vault_key → routing to read-only clone)`.
The "treated as an ordinary passphrase" failure mode F6 worried about
**cannot occur** for a 64-hex head — that branch fires first.

## Timeline (why F6 said "unconfirmed")

| Date | Event |
|---|---|
| 2026-06-04 | Read-key shorthand landed: commit `2b9f4f5` — *"fix(clone, pull): read-key shorthand, better errors, refuse pull on read-only"* |
| v0.14.26 | First release containing it (every release since, incl. v0.15.x, has it) |
| 07/24 | Review records F6: "CLI-side support not confirmed" — the code had existed for ~7 weeks; the gap was verification, not implementation |
| 2026-08-14 | Verified empirically (this document); regression tests now pin it |

## Implications for the web brief's Decision 1/2 (§7)

1. **Bare format 6 (`{64-hex}:{vault_id}`) = CLI parity.** It is byte-for-byte
   the string the CLI accepts and the shorthand `sgit clone --help` documents.
   Adopting it on the web closes the gap; it does not open one.
2. **On the `rk:` prefixed form:** safe, but please don't invent a new prefix.
   The CLI's canonical prefixed forms shipped this week (SGit-AI__CLI design
   contract `team/explorer/architect/contracts/08/14/v0__design__key-prefixes-and-leak-detection.md`):

   - vault key: `sgit_private_vault_{passphrase}:{vault_id}`
   - read key:  `sgit_private_read_{64-hex}`  (and `sgit_private_read_{64-hex}:{vault_id}` clones directly)

   The value after the prefix is byte-identical to the legacy key — old
   versions work by stripping it; nothing cryptographic changed. If the web
   adds a prefixed read-key format, adopting `sgit_private_read_` keeps both surfaces
   on one scannable format (anchored regex: `\bsgit_(private|public)_read_[0-9a-f]{64}\b`).
   The web's key **input** paths should strip a leading `sgit_private_vault_` /
   `sgit_private_read_` (two `startswith` checks) since users will paste prefixed keys
   from new CLI output.
3. **Terminology check:** sgit's read-only clone takes read_key + **vault_id**.
   If "transfer id" in the web's model is not exactly vault_id, that mapping
   deserves one explicit line in the brief.

## Where the guarantees are pinned (SGit-AI__CLI repo)

- `sgit_ai/cli/CLI__Vault.py` — `cmd_clone`: 64-hex shorthand detection + `--read-key` flag routing.
- `sgit_ai/crypto/Vault__Crypto.py` — `import_read_key` (accepts bare + `sgit_private_read_`), `parse_vault_key` (accepts bare + `sgit_private_vault_`).
- `tests/unit/crypto/test_Vault__Crypto__Key_Prefixes.py` — prefix/derivation-identity + read-only clone end-to-end.
- `tests/unit/sync/test_Vault__Sync__File_Modes.py` — `clone_read_only` writes `clone_mode.json` (0600).
- QA scenario `tests/qa/test_QA__Scenario_3__Cache_Multi_Clone.py` — read-only clones rejected from cache declaration (write-path gating).

## Bonus finding from this verification (fixed)

`sgit vault derive-keys` — the plumbing command our own cache guide documents
for obtaining the read key — was **dead code**: the method existed but was
never registered on the argument parser. Now wired (commit `cb3310e`), exempt
from the inside-a-vault context gate (it is a pure function of its argument),
accepting bare and prefixed forms of both the vault key and
`{read_key}:{vault_id}`; output deliberately stays bare hex for script
consumers. So the recommended web-team test loop is:

```bash
sgit vault derive-keys 'sgit_private_vault_{passphrase}:{vault_id}'   # → vault_id, read_key, write_key, file ids
sgit clone {read_key}:{vault_id} ./ro-clone --base-url … --token …
```
