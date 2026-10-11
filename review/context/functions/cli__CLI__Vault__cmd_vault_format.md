## `cmd_vault_format` in sgit_ai/cli/CLI__Vault.py (L1828-L1852)

**Purpose:** `sgit vault format [--set N] [--min-client X.Y.Z] [--feature NAME] [--remove-feature NAME]`: show or raise the vault's format gate — the owner's write of `format`, `min_client` and `features` (including `signatures-required` and its `signed-since-` anchor) to the shared index on the server.

**Inputs & Assumptions:** `args.directory`, `args.token` (local `--token`, saved by `resolve_token` when given), `args.base_url`/`--remote` via `resolve_remote` (saves `--base-url`), the four change flags.

**Outputs & Effects:** delegates to `Vault__Sync.set_format` or `format_info` (`Vault__Sync.py:L246-L255`); prints format / min client / features. Prints a warning block when raising to format 2 (L1837-L1843).

**What `set_format` does (`sgit_ai/core/actions/format/Vault__Sync__Format.py:L17-L67`), in order:**
1. L25-L27: components (local gate applied), local index.
2. L28-L31: `read_remote` (server copy, `check_client` applied — a too-old client refuses here, `Vault__Index_Sync.read_remote` L53) and `merge(index, remote)` with the **server's** gate — "start from the gate the server holds, not this clone's copy" (`test_set_format_from_a_stale_clone_keeps_the_gate_the_server_has`).
3. L32-L33: an explicit `format` is always written (`test_an_owner_write_always_carries_an_explicit_format`).
4. L34-L40: `--set`: only 1 or 2; **never down** (L37-L39).
5. L41-L48: `--min-client`: must parse; refuses a value newer than this client ("you would lock yourself out"); normalised to `M.m.p`.
6. L49-L57: features: add/remove; if `signatures-required` is off after the change **or was off before**, every `signed-since-*` is stripped (L52-L53); if it is newly on, the anchor `signed-since-<24 hex of current head>` is added (L54-L57) where the head is the **server's** `current` ref, falling back to the local ref offline (`_current_head` L69-L80).
7. L58-L59: format 2 ⇒ `ids-128` feature.
8. L61: save locally; L63-L65: `merge(index, remote, gate='local')` — "the owner's decision wins" — then `upload` with compare-and-swap against the bytes read at step 2 (`Vault__Index_Sync.upload` L169-L198: up to 3 re-read/re-merge retries, `require_written`); L66: save the result locally.

**Assumes:**
- The caller holds the write key (`c.write_key` passed to `upload`, L64); a read-only clone has `''` and the server rejects (TM boundary). Nothing client-side checks `write_key` before trying.
- Anyone with the vault key (A4) can switch `signatures-required` off and on; the anchor then moves to the current head, so re-enabling re-anchors (L2 test `test_L2__re_enabling_the_policy_does_not_lock_out_a_clone_that_missed_the_off_period`; TM-R30).
- `--remove-feature signatures-required` is the remedy every refusal message names (`Vault__Incoming_Check` L51-L52).
- `features` strings pass `Safe_Str__Feature` (regex not read).

**Cross-Function Dependencies:**
- Callees: `CLI__Token_Store.resolve_token`, `resolve_remote`; `create_sync`; `Vault__Sync.set_format`/`format_info` → `Vault__Sync__Format`; `Vault__Index_Sync.read_remote`/`merge`/`upload`; `Vault__Format.*`.
- Callers: `vault format` parser (L560-L571).
- Readers of what it writes: `Vault__Incoming_Check.require_signatures` (feature + anchor), `Step__Clone__Verify_Signatures`, `Vault__Branch_Manager.load_branch_index` → `check_client` (min_client), `Vault__Format.id_hex_len` (format).
- Tests: `tests/unit/review/test_Signature_Policy_And_Rewind__Fixes.py::test_the_owner_can_switch_the_policy_off_for_a_stale_clone`, `tests/unit/review/test_Format_Gate_And_Integrity.py` (not read), `tests/security/test_Security__Fixed__Trust_And_Policy.py::test_TM_F10__history_from_before_the_policy_is_not_held_against_anyone`.

**Open Questions:**
- unclear; `set_format` with `--min-client` lower than the current server value is accepted (only "not newer than this client" is checked) — `min_client` can go **down**; `format` cannot. Consistent with TM-R29 ("`features` and `min_client` follow the server's copy").
- unclear; whether `upload`'s CAS loop with `gate='local'` can overwrite a *concurrent* owner's gate change by a teammate (each retry re-merges with `gate='local'`, so this clone's gate always wins the re-merge).
