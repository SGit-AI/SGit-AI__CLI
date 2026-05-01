# Finding 01 — Type_Safe Compliance Delta (sprint v0.10.30)

**Author:** Villager Dev
**Date:** 2026-05-01
**Severity:** major
**Owners:** Villager Dev (fix), Architect (decision on `dict` return shapes)

---

## Summary

The seven new feature areas this sprint (probe, write, cat/ls extensions,
fetch, delete-on-remote, rekey + step subcommands, read-only clone mode)
were added without introducing any new schema classes. All new
public methods on `Vault__Sync` (`probe_token`, `write_file`,
`delete_on_remote`, `rekey`, `rekey_check`, `rekey_wipe`, `rekey_init`,
`rekey_commit`, `sparse_ls`, `sparse_cat`, `sparse_fetch`) take **raw
`str` / `bytes` / `dict`** parameters and return **raw `dict`s** instead of
Type_Safe schema instances.

This is consistent with the **pre-existing** style of `Vault__Sync`
(every public method already returned `dict`), so it is not a sprint-only
regression — but it widens the surface of un-typed contracts at exactly
the moment when those contracts (`{'mode': 'read-only', ...}`,
`{'blob_id': ..., 'unchanged': ...}`, `{'type': 'vault', ...}`) are being
serialised to JSON for stdout (`--json` flags) and to disk
(`clone_mode.json`, `push_state.json`). See finding 10.

## Evidence

| Method | File | Signature problem |
|--------|------|-------------------|
| `Vault__Sync.write_file` | `sgit_ai/sync/Vault__Sync.py:227–335` | `path: str`, `content: bytes`, `also: dict = None`, `-> dict` |
| `Vault__Sync.probe_token` | `sgit_ai/sync/Vault__Sync.py:1803–1837` | `token_str: str`, `-> dict`; returns `{'type': str, 'vault_id': str, 'token': str}` literal |
| `Vault__Sync.delete_on_remote` | `sgit_ai/sync/Vault__Sync.py:1724–1734` | `directory: str`, `-> dict` |
| `Vault__Sync.rekey*` (5 methods) | `sgit_ai/sync/Vault__Sync.py:1736–1801` | all return raw `dict`; values typed as plain `str`/`int` |
| `Vault__Sync._checkout_flat_map` | `sgit_ai/sync/Vault__Sync.py:1908–1924` | `flat_map: dict` |
| `Vault__Sync._generate_commit_message` | `sgit_ai/sync/Vault__Sync.py:1888–1906` | `old_entries: dict`, `new_file_map: dict` |
| `Vault__API__In_Memory.delete_vault` (call site at sync layer) | server-side store — out of scope but result `{'status': str, 'vault_id': str, 'files_deleted': int}` flows back unchecked |
| `clone_mode` literal | `sgit_ai/cli/CLI__Vault.py:1550, 1654; tests/.../test_CLI__Token_Store__Clone_Mode.py:26` | hand-built dict `{'mode': 'read-only', 'vault_id': ..., 'read_key': ...}` with no schema |

## Why it matters (rule reference)

- **CLAUDE.md §1 (Type_Safe Rules):** "Zero raw primitives in Type_Safe
  classes." This rule is violated for `Vault__Sync` if you treat its method
  parameters as part of the class contract — Type_Safe enforces fields,
  but the spirit of the rule is broken every time a public method takes
  `directory: str` instead of `Safe_Str__Vault_Path`.
- **CLAUDE.md §6:** "Round-trip invariant. Every schema must pass
  `assert cls.from_json(obj.json()).json() == obj.json()`." Cannot be
  enforced because the new return shapes are not schemas. The
  `clone_mode.json` and `push_state.json` files are written and read
  through hand-built dicts and `json.dump` / `json.load` — there is no
  `Schema__Clone_Mode` or `Schema__Push_State` to round-trip-test.

## Severity rationale

**major** — not a blocker, because Type_Safe class fields (the strict
reading of the rule) are not violated, and round-trip invariants on
existing `Schema__*` classes still pass. But the new state files
(`clone_mode.json`, `push_state.json`) are exactly the kind of artefact
the project introduced Schema classes for, and skipping them creates
silent drift. See finding 10.

## What changed vs v0.5.11 baseline

- v0.5.11 ended at "94% Type_Safe compliance, 3 files with raw primitives,
  2 semantic mismatches" (per `team/villager/CLAUDE.md`).
- This sprint did **not** add new `Schema__*` classes nor new
  `Safe_Str__*` / `Safe_UInt__*` types, but it **did** add:
  - 2 new persisted JSON state shapes (`clone_mode.json`,
    `push_state.json`) without schemas.
  - 9 new public `Vault__Sync` methods returning raw `dict`.
  - 8 new `cmd_*` methods on `CLI__Vault` that consume those raw dicts
    via `result.get(...)`, `result['key']`, `getattr(args, 'json', False)`.

Net direction: **regression** in spirit, even though strict rule
compliance is unchanged.

## Suggested next-action owner

- **Architect** must decide whether `Vault__Sync` public-API return
  shapes should become `Schema__*` instances. Villager Dev cannot
  unilaterally introduce Type_Safe types here because the choice
  changes the public Python contract for every consumer (CLI, tests,
  agent integrations). Treat as an open boundary question — do not
  refactor without that decision.
- **Villager Dev** can fix the two state-file shapes in isolation
  (`Schema__Clone_Mode`, `Schema__Push_State`) without touching public
  signatures. See finding 10 for that proposal.

## Do-not-refactor-without-tests-first markers

- `_generate_commit_message` reads `entry.get('content_hash', '')` and
  also `entry.get('size', -1)`. Replacing the dict with a Schema would
  require care to preserve the `-1`/`-2` sentinel branch (dict-only quirk).
- `write_file` `also: dict = None` (mutable-default trap avoided by None,
  but a Schema collection would have to allow empty by default).

## Out of scope for this finding

- Changes to existing schemas. Only new return shapes + new persisted
  files are flagged here.
- Suggested splits of `Vault__Sync` into smaller classes. See finding 06.
