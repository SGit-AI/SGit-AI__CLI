# Finding 03 — Vault format and CLI contract

**Verdict:** `BOUNDARY OK` for the on-disk vault format (no `bare/` change).
**Verdict:** `BOUNDARY DRIFT` between the **debrief** and the **implementation**
for `clone_mode.json` — debrief 01 mis-states the file's contents. The actual
on-disk shape is *different* from what the debrief says, but consistent with
the existing `clone_mode.json` semantics (it predates this sprint).
**Verdict:** Two new files in `.sg_vault/local/` are *implementation details*
per Dinis's directive — in scope for code-quality commentary, not for
"frozen contract" violations.

---

## 1. On-disk format — what's in `bare/`

The vault format proper is `.sg_vault/bare/{data,refs,keys,indexes,pending,branches}/`.
**Nothing in this directory layout changed in v0.10.30.** Object IDs still
follow `obj-cas-imm-{12 hex}`; ref IDs still follow `ref-pid-muw-{12 hex}`;
branch index file IDs still follow `idx-pid-muw-{12 hex}`. Confirmed by
reading `Vault__Storage.SG_VAULT_DIR` constants (unchanged) and
`Vault__Crypto.compute_object_id` (unchanged).

The HMAC-IV change (finding 01) **does not change the format** — IV is still
the first 12 bytes of an AES-GCM ciphertext. Old objects are still readable.
This is the cleanest possible kind of "no contract change" for a crypto
behaviour change.

`Schema__Object_Tree_Entry` was not modified — same `name_enc`, `size_enc`,
`content_hash_enc`, `content_type_enc`, `blob_id`, `tree_id`, `large` fields.

## 2. Two new files under `.sg_vault/local/`

Per Dinis's directive these are sgit-specific implementation details, not part
of the vault contract. Captured for code-quality commentary only.

### 2a. `push_state.json`

Path: `.sg_vault/local/push_state.json` (via `Vault__Storage.push_state_path`).

Shape (from `Vault__Sync._load_push_state` and `_save_push_state`):
```json
{
  "vault_id"        : "<vault_id>",
  "clone_commit_id" : "obj-cas-imm-<12hex>",
  "blobs_uploaded"  : ["obj-cas-imm-<12hex>", "obj-cas-imm-<12hex>", ...]
}
```

**The debrief calls the keys `vault_id:commit_id` and `uploaded_blobs`. The
real keys are `clone_commit_id` and `blobs_uploaded`. Minor docs drift.**

The composite identity is `(vault_id, clone_commit_id)`: if either differs
from the in-flight push, `_load_push_state` returns a fresh empty state
(line 2740) — old checkpoints are silently ignored, not used.

**No `Schema__Push_State` class.** The dict is constructed inline. This is a
Type_Safe hygiene issue — see finding 05.

### 2b. `clone_mode.json`

Path: `.sg_vault/local/clone_mode.json` (via `Vault__Storage.clone_mode_path`).

Shape (from `Vault__Sync.clone_read_only` lines 1550–1552 and 1654–1656):
```json
{
  "mode"     : "read-only",
  "vault_id" : "<vault_id>",
  "read_key" : "<hex read key>"
}
```

**The debrief 01 says this file holds `{"mode": "sparse"}` or `{"mode": "full"}`.
THIS IS WRONG.** `clone_mode.json` is for *read-only* clones (clones initialised
from a read key only — no passphrase). It carries the read key so subsequent
commands can derive the structure key without a vault_key file.

The actual sparse/full state goes into `local_config.json` as a `sparse: true`
field (`Vault__Sync.clone_with_keys` line 1448). Sparse status is read back at
status time (line 458) and pull time (line 662).

**This is documentation drift, not a code bug** — the implementation is
internally consistent. But the inconsistency between debrief 01 and the
debrief 04 mention of `edit_token` lookup (which IS in `local_config.json`,
not `clone_mode.json`) suggests Sonnet was tracking two slightly different
mental models.

### 2c. `local_config.json` accumulates undeclared fields

`Schema__Local_Config` declares **only** `my_branch_id`. The implementation
writes (and reads) at least four undeclared fields:
- `mode` ('simple_token')
- `edit_token`
- `sparse` (bool)
- (Potentially more — would need a full grep across writers)

This is the worst boundary issue I found in the sprint. `Schema__Local_Config`
no longer tells the truth about the file. See finding 05 for full analysis.

## 3. Pre-existing CLI command output — drift?

Spot-checked the rendered output of pre-existing commands that the sprint
touched.

| Command | Drift? | Notes |
|---|---|---|
| `sgit log` | YES (intentional) | Now defaults to `--oneline` (debrief 06). Pre-existing wrappers that grepped for the old multi-line format will break. Per Dinis: this is a UX win, not a contract violation we should fight. |
| `sgit log` short ID | YES (bug fix) | `[:12]` was returning the literal `obj-cas-imm-`; now strips the prefix and returns the hash. Any wrapper script that consumed the broken output is silently broken/fixed. |
| `sgit pull` progress | YES (intentional) | Denominator changed from "all objects" to "blobs only". Per Dinis directive in this brief: noted briefly, no separate finding. |
| `sgit status` | NEW field | Returns `sparse`, `files_total`, `files_fetched` keys when in sparse mode. Pre-existing consumers don't see them unless sparse is set. **Forward-compatible** — new keys, no removal. |
| `sgit cat` | YES (additive) | New `--id`, `--json` flags. Default behaviour unchanged. Forward-compatible. |
| `sgit ls` | YES (additive) | New `--ids`, `--json` flags. Default output gained the `✓`/`·` indicator and footer summary line. The footer line is new — wrappers that count files via `wc -l` will be off by 2. |

The `✓`/`·` indicator deserves a separate call-out: it's now a visible piece
of the public output. Per Dinis it's a sgit implementation detail (sparse is
not part of the vault contract), so I'm not flagging it as a frozen-contract
break, but it IS a new piece of CLI surface area that downstream tooling now
sees.

## 4. Hand-off

- **Sherpa/Architect:** confirm that `Schema__Local_Config` should grow to
  cover the four (or more) undeclared fields. This is a Type_Safe rule
  enforcement decision. (See finding 05.)
- **Designer/QA:** verify the debrief-vs-code drift on `clone_mode.json` and
  push_state schema names is benign — no other docs depend on the wrong
  shape.
- **Dev:** add `Schema__Push_State` and a proper `Schema__Local_Config__V2`
  (or grow the existing one) once the boundary call is made.
