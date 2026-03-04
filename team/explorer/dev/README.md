# Dev — Explorer Team

## Scope

- Implementation of core services: Vault__Crypto, Vault__Client, Vault__Sync
- Safe_* domain types with validation
- Type_Safe schemas for all data structures
- CLI commands via Typer__Routes pattern

## Implementation Order

1. Safe_* types (domain primitives)
2. Schemas (pure data classes)
3. Vault__Crypto (encrypt/decrypt/derive_key)
4. API client (Transfer API wrapper)
5. Sync engine (local ↔ remote state)
6. CLI commands (clone, push, pull, status)
