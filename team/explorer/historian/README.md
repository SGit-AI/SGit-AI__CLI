# Historian — Explorer Team

## Scope

- Decision log maintenance
- Session summaries
- Cross-referencing between sessions
- Reality document authoring

## Key Decisions (Session 1)

| # | Decision                          | Rationale                                      |
|---|-----------------------------------|-------------------------------------------------|
| 1 | Separate repo (SG_Send__CLI)      | Independent release cycle, clean dependency tree |
| 2 | Transfer API (not Vault Admin)    | CLI reads/writes files, doesn't manage vault settings |
| 3 | Zero raw primitives               | Type safety across all domain boundaries        |
| 4 | Pipeline before features          | Green CI is prerequisite for all feature work    |
| 5 | Crypto interop is the gate        | Python must match Web Crypto API byte-for-byte  |
| 6 | No mocks                          | Test real objects against real crypto operations |
