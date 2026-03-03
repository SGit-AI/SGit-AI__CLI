# SG_Send__CLI

CLI tool for syncing encrypted vaults with SG/Send Transfer API.

## Install

```bash
pip install sg-send-cli
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Architecture

- `sg_send_cli/safe_types/` — Domain-specific Safe_* types (zero raw primitives)
- `sg_send_cli/schemas/` — Pure data Type_Safe schemas
- `sg_send_cli/crypto/` — AES-256-GCM encrypt/decrypt, PBKDF2, HKDF
- `sg_send_cli/sync/` — Local ↔ remote vault sync (planned)
- `sg_send_cli/api/` — SG/Send Transfer API client (planned)
- `sg_send_cli/cli/` — CLI commands (planned)
