# CLAUDE.md — Explorer Team

## Team Structure

The Explorer team has 6 roles, each with specific responsibilities for the SGit-AI__CLI project.

| Role       | Focus                                    |
|------------|------------------------------------------|
| Architect  | Type_Safe patterns, crypto design, API contracts |
| Dev        | Implementation of Safe_* types, schemas, Vault__Crypto |
| QA         | Tests, round-trip validation, interop test vectors |
| DevOps     | CI/CD pipeline, GitHub Actions, PyPI publishing |
| Librarian  | Dependency tracking, osbot-utils version management |
| Historian  | Decision log, session summaries, reality documents |

## Session 1 Priority Order

1. **Pipeline first** — CI/CD must be green before feature work
2. **Crypto second** — Vault__Crypto with interop test vectors
3. **Everything else** — Safe_* types, schemas, sync logic

## Working Agreements

- Every Type_Safe class gets a test class
- Every Safe_* type gets validation edge-case tests
- Every schema gets a round-trip (json → from_json → json) test
- Crypto operations get interop test vectors (known inputs → known outputs)
- No PR merges without green CI
