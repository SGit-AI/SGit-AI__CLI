# Finding 07 — Test Quality on Sprint-New Features

**Author:** Villager Dev
**Date:** 2026-05-01
**Severity:** major (coverage gaps), minor (assertion quality)
**Owners:** QA (coverage gaps), Villager Dev (assertion fixes)

---

## Per-feature checklist

Tested against the 7 newly-added test files. Each row covers one
sprint feature.

| Feature | Tests file | Test count | Real fixtures? | Mocks? | Round-trip? |
|---------|------------|-----------:|----------------|--------|-------------|
| probe_token | `test_Vault__Sync__Probe.py` | 11 | yes (Vault__Test_Env, in-memory API) | none | n/a |
| delete-on-remote + rekey | `test_Vault__Sync__Delete_Rekey.py` | 42 | yes | none | yes (rekey check via status==clean) |
| write_file | `test_Vault__Sync__Write_File.py` | 12 | yes | none | partial (no commit-id determinism) |
| CLI write/cat/ls | `test_CLI__Vault__Write.py` | 13 | yes | **4 × FakeArgs** | n/a |
| Vault__Storage clone_mode_path | `test_Vault__Storage__Clone_Mode.py` | 3 | yes (real tmp dir) | none | n/a |
| Vault__Crypto.import_read_key | `test_Vault__Crypto__Import_Read_Key.py` | 6 | yes (real crypto) | none | yes (compares to derive_keys) |
| Token_Store.load_clone_mode | `test_CLI__Token_Store__Clone_Mode.py` | 4 | yes | none | n/a |

The three sync-layer files (Probe, Delete_Rekey, Write_File) are
**exemplary** — real crypto, real in-memory API, real temp dirs, real
class instances throughout. Use these as the no-mocks template.

## Coverage gaps — high-impact misses

### probe_token — missing scenarios

`test_Vault__Sync__Probe.py` covers vault-token happy path and
two error branches. Missing:

- **Share-token probe path** — `result['type'] == 'share'` with a real
  SG/Send transfer in fixture. There is **no test that exercises the
  share-token branch of `probe_token`** (`Vault__Sync.py:1824–1830`).
  This is a code-path that is asserted nowhere.
- **API failure on first batch_read** — `probe_token` swallows
  `Exception` at line 1821 before falling through to share-token check.
  No test covers a transient API failure that should surface (it
  silently looks at SG/Send instead).
- **Empty `idx_data`** — `idx_data.get(...)` falsy path not exercised.
- **`vault://` prefix already covered** but no test for `share://`
  or unknown-scheme prefix.
- **Network-only probe** (no local files / not in vault dir) — covered
  implicitly but no positive test verifying probe works from arbitrary
  cwd.

### rekey + step methods — missing scenarios

`test_Vault__Sync__Delete_Rekey.py:106–366` is thorough (corner cases
for content/binary/subdir/empty/double-rekey/post-push). Missing:

- **Mid-step failure recovery** — what if `rekey_init` fails after
  `rekey_wipe`? The vault is now in a half-state (no .sg_vault, no key).
  `rekey_init` succeeds in tests but no test forces a failure between
  steps.
- **rekey_commit on a working tree with deleted files** — only
  `add` and `modify` paths are exercised, no "file removed since
  last commit" path.
- **rekey custom-key validation** — `test_rekey_custom_key` accepts
  `'aaaaaaaaaaaaaaaaaaaaaaaa:bbbbbbbb'` (a string with the right shape).
  No test asserts behaviour for malformed keys (`'short'`,
  `''`, `':'`, `'no_colon'`).
- **Concurrent rekey** — out of scope, but worth noting for
  `do-not-refactor-without-tests-first`.

### delete-on-remote — missing scenarios

`test_Vault__Sync__Delete_On_Remote` (5 tests). Missing:

- **API failure during delete** — what if the server returns a
  partial-delete? `Vault__API__In_Memory.delete_vault` always returns
  `{'status': 'deleted', ...}`. There is no test for a failure path.
- **Read-only-clone case is covered** at line 90 — good.
- **Delete on a vault with NO write_key configured locally** —
  the `RuntimeError` at `Vault__Sync.py:1733` is asserted, but only via
  the read-only-clone synthetic. No test for "wrote_key file is
  missing but clone_mode is full".

### write_file — missing scenarios

`test_Vault__Sync__Write_File.py` (12 tests). Missing:

- **`also` overlap with `path`** — what if `also` contains the same
  vault path as `path`? Behaviour is undefined; no test.
- **`also` with empty bytes** — write a 0-byte file. Not covered.
- **Concurrent writes** — out of scope.
- **Large blob threshold** — the `is_large` flag is set at line 284
  via `len(encrypted) > LARGE_BLOB_THRESHOLD`. No test exercises the
  large-blob path for `write_file`.
- **Write to a path that does NOT exist on disk + does NOT exist in
  vault** — covered.
- **Write to a path that exists in vault but not on disk** — partially
  covered by `test_write_file_does_not_scan_directory` but no
  assertion that the on-disk file is created.

### sparse_ls / sparse_fetch / sparse_cat (CLI ls/cat/fetch)

**Critical gap:** `test_CLI__Vault__Write.py` covers `cmd_cat` and
`cmd_ls` flag plumbing only. There is no dedicated test file for
`sparse_ls`, `sparse_cat`, `sparse_fetch` at the `Vault__Sync` level.
Coverage is implicit through `test_Vault__Sync__Write_File.py:49–53`
(one assertion that `sparse_ls` returns the new file). Suggested:
new file `tests/unit/sync/test_Vault__Sync__Sparse.py`.

### Resumable push (per-blob checkpoint) — missing tests

This was a major sprint feature (commit `ca50dfd` "Resumable push:
upload blobs first with per-blob checkpoint") but there is **no
dedicated test file** for `_load_push_state` /  `_save_push_state` /
`_clear_push_state`. The push-checkpoint mechanism has zero direct
tests. `tests/unit/sync/test_Vault__Sync__Push.py` may exercise it
indirectly through the existing push test (verify), but **no test
asserts what happens after a push is interrupted, the state file is
written, and a second push resumes from the checkpoint.**

This is the **single biggest coverage gap** of the sprint.

### CLI parser tests vs. behaviour tests

`Test_Vault__Sync__Probe__Parser` and similar classes only test
`parser.parse_args(...)` output (i.e., argparse plumbing). These tests
will pass even if the corresponding `cmd_*` method is not wired to
the parser. The plumbing tests should be paired with end-to-end tests
that exercise `CLI__Main().run()` with `sys.argv` set, asserting the
correct `cmd_*` method is invoked. Currently these are missing for
probe, write, fetch, cat, ls, delete-on-remote, rekey wizard, and the
4 rekey sub-commands.

## Test bugs / smells

### B1 — `test_rekey_commit_empty_directory_returns_zero` (Delete_Rekey:281–294)

```python
result = sync.rekey_commit(env.vault_dir)
assert result['file_count'] == 0
# commit_id may be set (empty tree commit) or None; vault must be in clean state
status = sync.status(env.vault_dir)
assert status['clean'] is True
```

The comment says "commit_id may be set or None" — the test does
not assert *which*. This means the test passes for either branch of
`rekey_commit`'s except-handler at `Vault__Sync.py:1784–1787`. A
behaviour-locking test should pick the expected branch.

### B2 — `test_double_rekey_produces_different_keys` (line 308)

Asserts `r1['vault_key'] != r2['vault_key']` and
`r1['vault_id'] != r2['vault_id']`. This passes by **probability** (the
generator is random). Should also assert structural validity of each
key (regex match, length).

### B3 — `test_probe_unknown_token_raises` matches `'not found'`

The pytest match pattern `'not found'` would also match
`"path not found in vault"` (an unrelated error from another method).
A more specific pattern like `'Token not found on SGit-AI or SG/Send'`
locks the actual error.

### B4 — `Test_CLI__Read_Only_Guard.setup_method` writes the
clone_mode.json with a **fake `read_key='aa'`**.

The test passes because `_check_read_only` only checks `mode ==
'read-only'` — but if the read-only guard ever starts validating the
read_key (e.g., format check), this test would silently break and
pretend to pass. Use a real derived `read_key` from
`Vault__Crypto.derive_keys(...)` so the fixture is closer to
production state.

### B5 — Class-level `_env = None` + `setup_class` + `restore`

Eight test classes use this pattern (Probe, Probe__JSON,
Delete_On_Remote, Rekey, Rekey__Steps, Cat_Extensions, Ls_Extensions,
Read_Only_Guard). Each subclass holds the env on the class object,
not the instance. Cross-test interference is theoretically possible
if `restore()` doesn't fully reset state. The
`Vault__Test_Env.restore()` helper is the load-bearing piece — its
correctness is assumed by 50+ tests but its own test file
(`tests/unit/sync/vault_test_env.py` is the helper itself, not a test
file). **Hidden order dependency risk.** Worth a defensive test that
asserts `restore()` produces an equal env on two consecutive calls.

## Suggested next-action

- **QA** — close the four "missing scenarios" sets above, especially
  the resumable push checkpoint area.
- **Villager Dev** — fix B1 (assert which branch), B3 (more specific
  match), and B4 (real read_key fixture). Replace 4 × `FakeArgs`
  with `argparse.Namespace`.
- **Architect** — sanity-check whether `Vault__Test_Env.restore()`
  needs its own contract tests; if so, scope a small test class.
