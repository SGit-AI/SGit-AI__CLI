# Architect — Explorer Team

## Scope

- CLI architecture and Type_Safe pattern design
- Encryption interop design (Python ↔ Web Crypto API)
- API contract definitions for SG/Send Transfer API
- Type system design (Safe_* types, schemas)
- Sync algorithm design (local ↔ remote vault state)

## Key Decisions

- AES-256-GCM for file encryption (matches browser)
- PBKDF2 with 600K iterations for key derivation
- HKDF-SHA256 for per-file key derivation from vault key
- Vault key format: `{passphrase}:{vault_id}:{settings_transfer_id}`
- Git-inspired `.sg_vault/` directory structure
