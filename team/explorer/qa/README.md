# QA — Explorer Team

## Scope

- Crypto interop testing (Python ↔ Web Crypto API byte-for-byte match)
- Test vector management (known input → known output)
- Schema round-trip validation (json → from_json → json)
- Safe_* type edge case testing
- Full workflow integration tests

## Testing Rules

- No mocks. Test against real objects.
- Every Safe_* type gets boundary tests (empty, max length, invalid chars)
- Every schema gets round-trip tests
- Every crypto operation gets interop test vectors
