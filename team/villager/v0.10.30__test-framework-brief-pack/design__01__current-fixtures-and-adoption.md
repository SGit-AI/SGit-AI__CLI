# Design — Current Fixtures + Adoption Gap

**Status:** Captured. Drives brief B01.

## What's already in place

### `Vault__Test_Env` (snapshot + restore)

`tests/unit/sync/vault_test_env.py` — class-level shared environment:
- `setup_single_vault(files=None, vault_key=None)` — init + (optional) commit + push, snapshot result.
- `setup_two_clones(files=None)` — init + commit + push as Alice; clone as Bob; snapshot both.
- `restore()` returns a `Vault__Test_Env_Snapshot` with independent
  `shutil.copytree` copies and a deep-copied API store dict.

**Cost:** ~400 ms full vault init → **~3 ms `restore()`** per test.

### Sync conftest fixtures (F3–F6)

`tests/unit/sync/conftest.py` — five fixtures from the v0.10.30 design:

| Fixture | Scope | Covers | Consumers |
|---|---|---|---|
| F3 `bare_vault_snapshot` | module | `small_vault`, `read_list_vault` (bare layouts) | called via F4 |
| F4 `bare_vault_workspace` | function (factory) | per-test `copytree` of an F3 variant | bare-vault tests |
| F5 `probe_vault_env` | session | one shared probe-test vault | probe family (2 classes) |
| F6 `simple_token_origin_pushed` | module | post-push origin for simple-token tests | 2 share-safe tests |

### CLI conftest fixtures (F1–F2)

`tests/unit/cli/conftest.py` — `pki_keypair_snapshot` (F1, RSA-OAEP 4096 + ECDSA-P256) +
`pki_workdir` (F2, factory). Saves ~3.5s on `test_CLI__PKI.py`.

## Adoption gap

`grep` for `Vault__Crypto()` + `Vault__Sync(` in test files that do
NOT use any of F3–F6 or `Vault__Test_Env`:

| Test file | Raw setups | Fixture uses | Estimated savings if refactored |
|---|---:|---:|---:|
| `test_Vault__Sync__Multi_Clone.py` | 18 | 0 | ~7 s |
| `test_Vault__Diff__Coverage.py` | 15 | 0 | ~6 s |
| `test_Vault__Diff.py` | 9 | 0 | ~3.5 s |
| `test_Vault__Branch_Switch.py` | 8 | 0 | ~3 s |
| `test_Vault__Sync__Uninit.py` | 6 | 0 | ~2.5 s |
| `test_Vault__Sync__Remote_Failure.py` | 6 | 0 | ~2.5 s |
| `test_Vault__Sync__Helpers.py` | 5 | 0 | ~2 s |
| `test_Vault__Sync__Probe_Artefacts.py` | 4 | 0 | ~1.5 s |
| `test_Vault__Stash.py` | 4 | 0 | ~1.5 s |
| `test_Vault__Ignore.py` | 3 | 0 | ~1 s |
| 7+ more sync files (2 each) | ~14 | 0 | ~5 s |
| `test_CLI__Commands.py` | 9 | 0 (cli/ doesn't import sync fixtures) | ~3.5 s |
| `test_Vault__Inspector__Coverage.py` | 8 | 0 | ~3 s |

**Total: ~110 raw `Vault__Sync` setups across 18 files. Estimated
savings ~30–40 seconds suite-wide.**

## Why fixtures don't import cleanly across packages

`tests/unit/cli/test_CLI__Commands.py` would benefit from
`Vault__Test_Env` but importing across `tests/unit/sync/` is awkward
in test layout. **This is solved by D4** (move `Vault__Test_Env` to
`tests/_helpers/`).

## Mutation contract reminder (preserved)

All existing fixtures use **snapshot + per-test `shutil.copytree`**.
Mutations land in the per-test copy, never in the snapshot. New
fixtures (per D2) follow the same contract. **No shared mutable
state, ever** — that's the criterion that makes fixture sharing
correct rather than dangerous.

## What this design leaves to the briefs

- Brief B01 does the per-file refactor following the table above.
- Brief B03 relocates `Vault__Test_Env` to `tests/_helpers/` so cli/,
  api/, objects/, transfer/, appsec/ can all consume it.

## Acceptance for this design

- Inventory above is the canonical adoption-gap source for B01.
- `Vault__Test_Env` + F1–F6 are the existing-infrastructure baseline.
- Mutation contract (snapshot + copytree, no shared mutable state)
  applies to every fixture this pack adds.
