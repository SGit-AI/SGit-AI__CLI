# Design — New Fixtures Catalog (D2)

**Status:** Captured. Drives brief B02.

Five new fixtures to fill gaps the current F1–F6 + `Vault__Test_Env`
don't cover. All scoped session/module, all use snapshot + per-test
`shutil.copytree` for isolation. No shared mutable state.

---

## NF1 — `two_clones_pushed`

**Scope:** module
**Pre-builds:** Alice init+commit+push, Bob clone of the same vault.
Both directories present in the snapshot. The in-memory API store
contains the post-push state.

**Signature:**
```python
@pytest.fixture(scope='module')
def two_clones_pushed():
    # Returns dict with: snapshot_dir, alice_sub, bob_sub,
    #                    vault_key, head_commit_id, snapshot_store
    ...
```

**Per-test consumer:**
```python
@pytest.fixture
def two_clones_workspace(two_clones_pushed):
    # copytree both clones; deepcopy snapshot_store; return ready Vaults
    ...
```

**Replaces:** ~16 of the 18 raw setups in `test_Vault__Sync__Multi_Clone.py`
plus several in `test_Vault__Branch_Switch.py`, `test_Vault__Merge.py`.

**Estimated savings:** ~10 s suite-wide.

---

## NF2 — `vault_with_N_commits` (factory)

**Scope:** module (snapshot per N), function (workspace factory)
**Pre-builds:** Linear commit history of N commits, with deterministic
content per commit so diff/log/blame tests have predictable results.

**Signature:**
```python
@pytest.fixture(scope='module')
def vault_with_N_commits_snapshots():
    return {
        1  : _build_with_n(1),
        5  : _build_with_n(5),
        20 : _build_with_n(20),
    }

@pytest.fixture
def vault_with_N_commits(vault_with_N_commits_snapshots):
    def make(n: int):
        if n not in vault_with_N_commits_snapshots:
            raise KeyError(f'No snapshot for n={n}')
        # copytree the snapshot, return ready Vault
        ...
    return make
```

**Replaces:** Most of `test_Vault__Diff.py`, `test_Vault__Diff__Coverage.py`,
diff/log/inspect tests, and any "I need a vault with history" test.

**Estimated savings:** ~12 s suite-wide.

**Variant content schema:** each commit `i` writes `file_{i}.txt` with
content `commit-{i}-content`. Deterministic + searchable.

---

## NF3 — `vault_with_pending_changes`

**Scope:** module
**Pre-builds:** A vault past initial commit + push, with the working
copy modified (untracked file added; tracked file modified; tracked
file deleted). State is "ready for `sgit status` / `sgit add` / `sgit
reset` tests".

**Signature:**
```python
@pytest.fixture(scope='module')
def vault_with_pending_changes_snapshot():
    # Returns: snapshot_dir, vault_sub, vault_key,
    #          expected_status: {added: [...], modified: [...], deleted: [...]}
    ...

@pytest.fixture
def vault_with_pending_changes(vault_with_pending_changes_snapshot):
    # copytree, return ready vault + expected_status dict
    ...
```

**Replaces:** Most of `test_Vault__Sync__Helpers.py` (status-related),
parts of `test_Vault__Stash.py`, parts of `test_Vault__Ignore.py`.

**Estimated savings:** ~3 s suite-wide.

---

## NF4 — `vault_with_branches`

**Scope:** module
**Pre-builds:** Vault with two branches diverged from a common base
commit. Useful for branch switch, merge, and remote-ops tests.

**Signature:**
```python
@pytest.fixture(scope='module')
def vault_with_branches_snapshot():
    # Returns: snapshot_dir, vault_sub, vault_key,
    #          branches: {'main': head_id, 'feature': head_id, 'base': common_ancestor_id}
    ...

@pytest.fixture
def vault_with_branches(vault_with_branches_snapshot):
    ...
```

**Replaces:** Parts of `test_Vault__Branch_Switch.py`,
`test_Vault__Merge.py`, branch-related portions of CLI tests.

**Estimated savings:** ~2 s suite-wide.

---

## NF5 — `read_only_clone`

**Scope:** module
**Pre-builds:** A vault cloned in read-only mode (`clone_mode.json`
contains only `read_key`, no `write_key`). Useful for guard tests
(B13's `Vault__Read_Only_Error` path) and any future read-only flow.

**Signature:**
```python
@pytest.fixture(scope='module')
def read_only_clone_snapshot():
    # Returns: snapshot_dir, ro_clone_sub, read_key_hex,
    #          source_vault_key (the writable origin if a test needs it)
    ...

@pytest.fixture
def read_only_clone(read_only_clone_snapshot):
    ...
```

**Replaces:** Setup in `test_Vault__Sync__Write_File__Guard.py` (some)
and any future read-only test class.

**Estimated savings:** ~1 s suite-wide.

---

## Summed expected savings (session-wide on the slow runner)

NF1 (~10s) + NF2 (~12s) + NF3 (~3s) + NF4 (~2s) + NF5 (~1s) = **~28
seconds**. Combined with the B01 adoption refactor (~30–40s), total
expected runtime reduction is **~50–70 seconds** on the slow runner.

That's ~25% of the current 285s — the sprint goal.

---

## Where they live

After D4 lands (move `Vault__Test_Env` to `tests/_helpers/`), all five
new fixtures live in `tests/conftest.py` (root) so every test
sub-directory can consume them without cross-namespace import.

Until D4 lands, they live in `tests/unit/sync/conftest.py` alongside
F3–F6.

## Acceptance for this design

- Five fixture signatures + scopes locked.
- Each fixture follows the snapshot + copytree mutation contract from D1.
- Each fixture has at least one isolation test (round-trip + no
  shared-state pollution between consumers).
- Brief B02 implements all five.
