# 09 — Test Coverage & Quality

**Author:** QA
**Audience:** QA, Developers

## Test Statistics (as of v0.8.10)

| Metric              | Value                         |
|---------------------|-------------------------------|
| Total unit tests    | 971 passing                   |
| Expected failures   | 4 (xfail — known bugs)        |
| Skipped             | 87 (integration, need server)  |
| Code coverage       | ~83% (baseline)                |
| Test framework      | pytest >= 8.0                  |
| No mocks policy     | 18 violations remaining        |

## Test Structure

```
tests/
  |-- conftest.py                          # shared fixtures
  |-- unit/                                # runs with: pytest tests/unit/
  |     |-- test__unit.py                  # basic smoke test
  |     |-- safe_types/                    # 33 test files (one per Safe_* type)
  |     |-- schemas/                       # 16 test files (one per schema)
  |     |-- crypto/                        # 5 test files (crypto + PKI + hardening)
  |     |-- objects/                       # 6 test files (object store, commit, ref, inspector)
  |     |-- sync/                          # 16 test files (sync, merge, branch, fetch, etc.)
  |     |-- cli/                           # 7 test files (commands, error handler, debug, SSL)
  |     |-- pki/                           # 2 test files (keyring, key store)
  |     |-- secrets/                       # 2 test files (secrets store + edge cases)
  |     +-- appsec/                        # 1 test file (security audit tests)
  |
  |-- integration/                         # runs with Python 3.12 venv
  |     |-- conftest.py                    # in-memory server setup
  |     |-- test_Vault__Integration.py     # end-to-end vault workflows
  |     |-- test_Vault__Batch__Integration.py  # batch API tests
  |     +-- test_Vault__Local_Server.py    # local server tests
  |
  +-- qa/                                  # scenario tests (ignored by default)
        |-- helpers.py
        |-- test_QA__Scenario_1__Solo_Workflow.py
        |-- test_QA__Scenario_2__Two_User_Collab.py
        |-- test_QA__Vault_Init_Walkthrough.py
        +-- test_QA__Vault_Walkthrough.py
```

## Coverage by Package

| Package         | Source Files | Test Files | Coverage | Status        |
|-----------------|-------------|------------|----------|---------------|
| safe_types/     | 44          | 33         | ~95%     | Well covered  |
| schemas/        | 21          | 16         | ~90%     | Good          |
| crypto/         | 3           | 5          | ~90%     | Good + hardening |
| objects/        | 4           | 6          | ~85%     | Good          |
| sync/           | 12          | 16         | ~80%     | Good          |
| cli/            | 7           | 7          | ~60%     | Moderate      |
| api/            | 6           | 3          | ~35%     | LOW           |
| pki/            | 2           | 2          | ~75%     | Moderate      |
| secrets/        | 1           | 2          | ~80%     | Good          |

## Coverage Gaps (Priority Order)

### Critical Gaps

1. **API layer** — 26-36% coverage. `Vault__API`, `Vault__Backend__API` lack thorough
   testing. Error paths, retry logic, and edge cases untested.

2. **Schema__Vault_Policy** — 0% coverage. Schema exists but has no tests.

3. **Schema__Change_Pack** — minimal coverage. Schema round-trip tested but no
   operational tests.

### Moderate Gaps

4. **CLI commands** — Mostly tested via `test_CLI__Commands.py` but some commands
   have limited edge-case coverage (error paths, invalid inputs).

5. **Vault__Sync.push** — Happy path tested but error recovery paths (batch
   failure fallback, first-push edge cases) have limited coverage.

6. **Vault__GC** — Garbage collection/drain tested but not in complex multi-pack
   scenarios.

### Mock Violations

18 mock usages remain in 2 CLI test files. These should be replaced with
`Vault__API__In_Memory` or real object tests:

- `tests/unit/cli/test_CLI__Commands.py` — bulk of remaining mocks
- `tests/unit/cli/test_CLI__PKI.py` — some mocks

## Test Patterns

### Good Pattern: Real Objects, In-Memory Backend

```python
class Test_Vault__Sync__Push:
    def test_push_uploads_objects(self):
        api    = Vault__API__In_Memory()
        sync   = Vault__Sync(crypto=Vault__Crypto(), api=api)
        result = sync.init('/tmp/test-vault')
        # ... add files, commit, push
        assert result['status'] == 'pushed'
```

### Good Pattern: Schema Round-Trip

```python
class Test_Schema__Object_Commit:
    def test_round_trip(self):
        commit = Schema__Object_Commit(
            schema='commit_v1',
            tree_id='obj-cas-imm-a1b2c3d4e5f6',
            ...)
        assert Schema__Object_Commit.from_json(commit.json()).json() == commit.json()
```

### Good Pattern: Crypto Hardening

```python
class Test_Vault__Crypto__Hardening:
    def test_decrypt_tampered_ciphertext_raises(self):
        crypto = Vault__Crypto()
        key    = os.urandom(32)
        ct     = crypto.encrypt(key, b'secret')
        ct_bad = ct[:5] + bytes([ct[5] ^ 0xFF]) + ct[6:]  # tamper
        with pytest.raises(Exception):  # InvalidTag
            crypto.decrypt(key, ct_bad)
```

## Running Tests

```bash
# All unit tests (Python 3.11)
pytest tests/unit/ -v

# Specific test file
pytest tests/unit/sync/test_Vault__Sync__Push.py -v

# With coverage report
pytest tests/unit/ --cov=sg_send_cli --cov-report=term-missing

# Integration tests (Python 3.12 venv required)
/tmp/sg-send-venv-312/bin/python -m pytest tests/integration/ -v

# QA scenario tests (excluded by default)
pytest tests/qa/ -v
```

## xfail Tests (Known Bugs)

These 4 tests are marked `@pytest.mark.xfail` — they document known bugs:

1. **File deletion doesn't propagate** — deleted files reappear after pull
2. **False merge conflicts after pull** — editing a pulled file triggers false conflict
3. **Pull status after cross-clone merge** — reports "merged" instead of "up_to_date"
4. **Push silent failure on remote write error** — user thinks push succeeded

See `10__KNOWN_ISSUES.md` for full details.

## CI/CD Pipeline

```
.github/workflows/
  |-- ci-pipeline.yml          # pytest on push/PR
  |-- ci-pipeline__dev.yml     # dev branch CI
  +-- ci-pipeline__main.yml    # main branch + PyPI publish on version tags
```

Tests run on Python 3.11 (unit) and Python 3.12 (integration, where available).
