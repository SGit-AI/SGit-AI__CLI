# Brief — How to Correctly Test Your Legacy Simple-Token Vaults

**From:** sgit CLI team (SGit-AI/SGit-AI__CLI)
**Date:** 2026-08-16
**To:** the agent maintaining the legacy-vault registry
**Subject:** your DEAD/ALIVE marks are unproven — the probe method used cannot tell a dead vault from a live one

---

## 1. What you got right

Your key derivation for `make-dose-3967` is **exactly correct**. I recovered the
deleted `Simple_Token` class from git history (commit `5e62605^`,
`sgit_ai/crypto/simple_token/Simple_Token.py`) and reproduced it:

```
vault_id = sha256(token)[:12]                                    -> e4ab4f83d3b7   ✅ matches
aes_key  = PBKDF2-HMAC-SHA256(token, salt=b'sgraph-send-v1', 600_000, 32 bytes)
read_key = HKDF-SHA256(aes_key, salt=None, info=b'vault-read-key')
        -> 39ee85f5e3e3983d4302ba4ccd92ad5bd2ff562339ef07baacf798b2682f6817        ✅ matches
```

(Also available: `write_key` = HKDF info `b'vault-write-key'`, `ec_seed` =
HKDF info `b'vault-ec-seed'`.)

## 2. What is wrong — and why every DEAD mark needs re-testing

**The `Full vault key: make-dose-3967:e4ab4f83d3b7` line is misleading, and all
three `Verify with:` commands are invalid on a current CLI.**

That string worked on pre-0.15 CLIs only because the old code detected a simple
token *in the passphrase slot* and **ignored the vault_id half entirely**. On
sgit ≥ 0.15 there is no such detection: `make-dose-3967:e4ab4f83d3b7` is parsed
as an ordinary `{passphrase}:{vault_id}` vault key and PBKDF2'd with a
different salt, producing a completely different read key:

| | read_key | derived ref it looks for |
|---|---|---|
| legacy (correct) | `39ee85f5…2f6817` | `ref-pid-muw-14a33bcc79b8` |
| what your command did | `81c42af9…324812` | `ref-pid-muw-36a6a47fb07b` ← never existed |

So **"no branch index / no named ref" is a false negative.** That command
returns the identical error whether the vault is full of data or completely
empty — it cannot distinguish them. Any registry entry marked DEAD on the
strength of it is **unproven**, and some of those vaults may be perfectly alive.

(Your `sgit receive` line has a separate problem: `receive` was removed in 0.14,
so it tests nothing on any modern install.)

## 3. The good news: removing the code did NOT make the data unrecoverable

The token → keys derivation is pure maths (reproduced above), and everything
*downstream* of the read key is **unchanged** in the current CLI. The legacy
`derive_keys_from_simple_token` ended at `(read_key, vault_id)` and then called
the very same `derive_ref_file_id` / `derive_branch_index_file_id` functions the
CLI uses today. Verified byte-identical:

```
legacy derive_keys_from_simple_token -> ref-pid-muw-14a33bcc79b8 / idx-pid-muw-93940b239d3c
modern import_read_key(read_key, vid) -> ref-pid-muw-14a33bcc79b8 / idx-pid-muw-93940b239d3c
```

**Therefore a modern read-key clone opens a legacy vault, with no old CLI
needed:**

```bash
sgit clone <read_key_hex>:<vault_id> recovered-<vault_id> \
    --base-url <endpoint> --token $SG_SEND_ACCESS_TOKEN
```

Also fine: the April-era object format still reads — the `tree-iv-determinism`
migration only affects CAS dedup, not decryptability.

## 4. Use this tool, not hand-rolled commands

`scripts/recover_legacy_simple_token_vault.py` (in SGit-AI__CLI, on branch
`claude/sgit-architect-agent-review-3tl5ti`) does the derivation and probes
**both** surfaces a legacy token could address — the vault object store *and*
the transfers API — then gives a real verdict.

```bash
export SG_SEND_ACCESS_TOKEN=<your token>

# one vault, full detail
python scripts/recover_legacy_simple_token_vault.py make-dose-3967 \
    --base-url https://dev.send.sgraph.ai --probe --self-check

# the whole registry in one pass (verdict table + clone commands for survivors)
python scripts/recover_legacy_simple_token_vault.py \
    --tokens-file registry-tokens.txt --base-url https://dev.send.sgraph.ai --probe

# machine-readable, to update the registry programmatically
python scripts/recover_legacy_simple_token_vault.py --tokens-file registry-tokens.txt \
    --probe --json > probe-results.json
```

It is standalone (derivation inlined, runs from a bare checkout) and
`--self-check` asserts that inlined derivation still matches the installed CLI.
It lives in `scripts/`, **not** `sgit_ai/` — the CLI must not regain
simple-token support; this is a recovery tool for vaults you own.

## 5. What the probe actually checks, and how to read it

| Signal | Meaning |
|---|---|
| `vault list … files=N` with N > 0 | **DATA PRESENT** — clone it |
| `ref object http=200` | **DATA PRESENT** — the real head ref exists |
| `files=0` + `ref 404` + `transfers/info 404` | no data *at that endpoint* |
| `transfers/check-token/<token>` → `{"valid": false, "reason":"not_found"}` | the server itself confirms the token is unknown |

Important: "no data at this endpoint" ≠ "unrecoverable". The keys are correct
forever, so if the objects exist on **another endpoint** or in an **S3 backup**,
they will open with them. Only the *location* is in question, never the crypto.

## 6. Result for `make-dose-3967` — DEAD is correct, but for the right reason now

Probed authenticated against `https://dev.send.sgraph.ai`:

```
vault list  /api/vault/list/e4ab4f83d3b7 (no prefix) -> 200, files: []
ref object  bare/refs/ref-pid-muw-14a33bcc79b8       -> 404   (the CORRECT ref)
transfers   /api/transfers/info/e4ab4f83d3b7         -> 404
token check /api/transfers/check-token/make-dose-3967 -> {"valid": false, "reason": "not_found"}
```

Genuinely empty. Keep the DEAD mark — but note it was reached by a method that
would have mislabelled a live vault identically.

## 7. What we suggest you do

1. **Re-probe every registry entry** with the tool in §4, including ones already
   marked DEAD. Record the *evidence* (file count + ref status), not just a verdict.
2. **Replace the `Verify with:` block** in every registry entry. Correct form:
   ```
   Verify with:
     python scripts/recover_legacy_simple_token_vault.py <token> --base-url <endpoint> --probe
     # if DATA PRESENT:
     sgit clone <read_key>:<vault_id> recovered-<vault_id> --base-url <endpoint> --token $SG_SEND_ACCESS_TOKEN
   ```
   Drop `Full vault key: <token>:<vault_id>` or relabel it
   `legacy vault key (pre-0.15 CLIs only — NOT usable today)`.
3. **Check other endpoints** before concluding anything is lost — if these vaults
   were created in April, confirm which endpoint was in use then; `dev.send…`
   today may not be where they were written.
4. **For survivors:** read-key clone gets the data out; then `sgit init` a fresh
   vault and push the content into it. Write access to the *original* vault_id is
   not possible with the current CLI (no raw-write-key import), and is not needed
   for recovery.
5. **Registry hygiene:** record `read_key` and `vault_id` per entry — those are
   the durable recovery credentials. The token itself is only an input to the
   derivation, and is precisely the ~30-bit weakness the scheme was retired for,
   so treat any file containing these tokens as secret material.
