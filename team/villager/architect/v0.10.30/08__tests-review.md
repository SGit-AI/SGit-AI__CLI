# Finding 08 — Tests review (intent, bugs, coverage gaps)

**Verdict:** `BOUNDARY DRIFT` — three significant test-quality issues, plus
two notable coverage gaps. **No SEND-BACK-TO-EXPLORER**, but the test layer
is materially weaker than the debrief claims.

This finding follows the additional directive to read tests as a lens for
intent and to identify bugs/gaps.

---

## 1. The HMAC-IV change shipped without tests (CRITICAL)

Already covered in finding 01. Restated here because it's the single biggest
test-quality issue of the sprint.

`git show 4d53f79 --stat` shows two production files changed and **zero test
files**. The follow-up commit `c249f91` only edits an existing test by 2 lines
to fix a regression. `grep -rn "encrypt_deterministic" tests/` returns
nothing.

The debrief 07 lists "3 determinism assertions". They do not exist.

## 2. `Test_Vault__Sync__Probe` has no `share` token coverage (HIGH)

`tests/unit/sync/test_Vault__Sync__Probe.py` covers:
- `vault` token returns `type='vault'` (4 assertions across 4 tests)
- unknown token raises (1 test)
- non-simple-token raises (1 test)
- prefix-strip (1 test)

Debrief 05 advertises 11 tests including
`test_probe_share_token_returns_share`. **That test does not exist.** The
share-token branch in `Vault__Sync.probe_token` (lines 1824–1832) is
**unexercised** in unit tests.

Implication: if `API__Transfer.info()` ever changes its return shape or
exception type, `probe_token`'s share path silently breaks and CI is green.

The branch is short (3 lines of meaningful logic), so the risk is small —
but the debrief is misleading. Recommend QA add the share-token test using
the in-memory transfer stub.

## 3. `test_rekey_empty_vault_no_files` test passes for the wrong reason

Lines 267–279:

```python
def test_rekey_empty_vault_no_files(self):
    """rekey on a vault with no working files succeeds — empty tree commit."""
    env_holder = Vault__Test_Env()
    env_holder.setup_single_vault()        # no files
    env  = env_holder.restore()
    sync = env.sync
    result = sync.rekey(env.vault_dir)
    assert result['vault_key']
    assert result['vault_id']
    # empty vault gets an empty-tree commit (valid state, not an error)
    status = sync.status(env.vault_dir)
    assert status['clean'] is True
    env.cleanup()
```

The test name says "empty vault no files succeeds with empty tree commit".
But `rekey_commit` (line 1778) catches `RuntimeError` matching "nothing to
commit" and returns `commit_id=None`. So the rekey of an empty vault
silently swallows the "nothing to commit" error.

The test asserts `vault_key`, `vault_id`, and `status.clean`. **It does NOT
assert that a commit was created.** It would pass equally well if rekey
returned `commit_id=None`. The companion test
`test_rekey_commit_empty_directory_returns_zero` (281–294) confirms this
behaviour explicitly: `assert result['file_count'] == 0`. The
"empty-tree commit" mentioned in the docstring of the first test is
misleading — there isn't one.

**Severity:** the test isn't wrong, it's mis-described. Future readers
will think rekey on an empty vault produces a commit; it doesn't.
Recommend rewriting the docstring or adding `assert result['commit_id']
is None` to make the actual contract explicit.

## 4. `test_delete_on_remote_idempotent` is verifying a stub, not the contract

Lines 85–88:
```python
def test_delete_on_remote_idempotent(self):
    self.sync.delete_on_remote(self.env.vault_dir)
    result = self.sync.delete_on_remote(self.env.vault_dir)
    assert result['files_deleted'] == 0
```

This relies on `Vault__API__In_Memory.delete_vault` returning
`files_deleted=0` when no keys match. The real server might return a 404,
or might return a count of zero, or might raise. The test passes against
the stub but tells us nothing about the real-server contract.

Mitigation: this is a unit test, not an integration test. The integration
suite (in `tests/integration/`) is the place to confirm real-server
behaviour. As long as the integration suite has equivalent coverage we're
fine. **QA should confirm.**

## 5. `test_cmd_write_blocked_in_read_only` — the read-only guard test
**only verifies the CLI guard, not the domain guard**

Line 216-236:
```python
def test_cmd_write_blocked_in_read_only(self):
    ...
    with pytest.raises(RuntimeError, match='read-only'):
        vault.cmd_write(FakeArgs())
```

The test routes through `cmd_write` → `_check_read_only`. It does NOT call
`Vault__Sync.write_file` directly with a read-only clone configured.

Looking at `Vault__Sync.write_file` (lines 227–335): there is **no
read-only guard at the domain layer**. A programmatic caller bypassing the
CLI can call `write_file` on a read-only clone and (presumably) succeed if
the underlying primitives don't notice the missing write_key.

This is consistent with finding 02 (defence-in-depth missing on the domain
side). The test reflects the implementation accurately, but the
implementation is weaker than the test name suggests. The test is misleading
to a reader who assumes "if `cmd_write` is blocked, `write_file` is also
blocked".

Recommend Dev add a domain-level guard, then a domain-level test.

## 6. Coverage gaps (no test exercises X)

Specific scenarios I searched for and could not find tests for:

| Scenario | Tested? |
|---|---|
| Two unchanged commits produce identical tree IDs (the headline HMAC-IV claim) | NO |
| `encrypt_deterministic(k1, p) != encrypt_deterministic(k2, p)` (key-dependence of IV) | NO |
| `probe_token` returns `type='share'` | NO |
| Sparse pull leaves working copy stale for a remote-changed cached file | NO |
| `delete_on_remote` followed by `push` (no rekey in between) — what happens to push_state.json? | NO (see finding 06.2d) |
| `sgit reset` followed by `push` — orphan push_state.json | NO |
| `--also` with content-hash-matching but `path` content changing — does the `unchanged` path skip the also-files? | NO |
| `write_file` called with `also` containing a path that already matches HEAD content | PARTIAL (one combined test, but no isolated dedup-via-also test) |
| Sparse-clone → `pull` → BFS encounters a tree object whose IV is HMAC-derived AND another whose IV is random (mixed-vintage vault) | NO |

Item 9 is the most worrying long-tail issue: vaults that pre-date the HMAC
change have random-IV tree objects on the server. The new code reads them
fine (decrypt is IV-agnostic) but no test exercises the mix.

## 7. Tests that would still pass if the implementation were stubbed

Spot-checked a handful:

- `test_probe_vault_token_includes_vault_id` (line 32): asserts
  `result['vault_id']` is truthy. A stub returning
  `{'type': 'vault', 'vault_id': 'x'}` passes. The test doesn't verify the
  vault_id matches the derivation from the input token.
- `test_write_file_creates_new_file` (line 29): checks that result keys
  start with `obj-cas-imm-`. A stub returning `{'blob_id': 'obj-cas-imm-stub',
  'commit_id': 'obj-cas-imm-stub', ...}` passes. The test doesn't
  decrypt the blob and verify content matches.
- `test_delete_on_remote_returns_deleted` (line 68): just checks
  `result['status'] == 'deleted'`. The actual server-side state isn't
  asserted (the next test does, separately).

These aren't bugs — they're individually scoped tests, and other tests in
the same class cover the missing bits. But they show the testing style
favours field-shape over outcome-correctness, which is a long-term
maintenance risk.

## 8. Hand-off

- **QA (highest priority):** add the missing HMAC-IV determinism tests.
  The headline architectural claim of the sprint is unprotected.
- **QA:** add the missing `probe_token` share-token test.
- **QA:** add coverage for the orphan-push_state scenarios listed in
  finding 06.
- **Dev:** add a domain-level read-only guard to `write_file`, then update
  the test (finding 5 above and finding 02.2c).
- **Architect (next sprint):** add a "tests must follow debrief claims"
  check to the debrief template — three of the seven debriefs in this
  sprint over-stated their test coverage.
