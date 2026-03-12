# QA — Villager Team

## Scope

- Identify gaps in test coverage across the codebase
- Add missing round-trip tests for all schemas
- Add missing boundary and edge-case tests for all Safe_* types
- Validate that refactorings preserve existing behavior
- Ensure crypto interop test vectors cover all code paths
- Add regression tests for any bugs found during refactoring

## Testing Strategy

1. **Coverage audit** — Map existing tests to source modules, identify untested code
2. **Gap filling** — Write tests for uncovered paths, prioritizing correctness-critical code
3. **Refactoring validation** — Run full test suite before and after each refactoring
4. **Regression protection** — Add targeted tests for any issues discovered during review

## Test Quality Rules

- No mocks — test against real objects
- Every Safe_* type gets boundary tests (empty, max length, invalid chars, whitespace)
- Every schema gets round-trip tests (`from_json(obj.json()).json() == obj.json()`)
- Every crypto operation gets interop test vectors (known inputs → known outputs)
- Tests must be deterministic — no random data without fixed seeds
- Test file naming: `test_<ClassName>.py` (no `__init__.py` in test directories)
