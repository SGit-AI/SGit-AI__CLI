# DevOps — Villager Team

## Scope

- Test infrastructure: local send server instance bootable in CI
- Coverage reporting integrated into CI pipeline (every commit)
- Test data generators (create vaults, files, users programmatically)
- Test harnesses (spin up local server for integration tests)
- Performance benchmarking infrastructure for test suite execution time

## Test Infrastructure Requirements

| Component | Purpose | Status |
|-----------|---------|--------|
| Local send server | Integration/QA tests need real API | Exists (test_Vault__Local_Server.py) |
| CI server bootstrap | Boot full stack in GitHub Actions | Needed |
| Coverage reporting | Report on every commit/PR | Needed |
| Test data generators | Programmatic vault/file creation | Partial (helpers in tests) |
| Performance tracking | Track test suite execution time over sprints | Needed |

## CI Pipeline Targets

- All unit tests run on every push/PR
- Integration tests run with local server in CI
- Coverage report generated and compared against baseline
- Coverage decrease blocks PR merge
- Test execution time tracked and alerted if degrading

## Deliverables

- CI workflow that boots local send server for integration tests
- Coverage reporting in CI (term-missing + HTML artifact)
- Test infrastructure audit: what exists, what's missing, what needs improvement
- Performance baseline for test suite execution
