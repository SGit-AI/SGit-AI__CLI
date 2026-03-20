# SGit-AI__CLI

CLI tool for syncing encrypted vaults with SGit-AI.

## Install

```bash
pip install sgit-ai
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Architecture

- `sgit_ai/safe_types/` — Domain-specific Safe_* types (zero raw primitives)
- `sgit_ai/schemas/` — Pure data Type_Safe schemas
- `sgit_ai/crypto/` — AES-256-GCM encrypt/decrypt, PBKDF2, HKDF
- `sgit_ai/sync/` — Local ↔ remote vault sync
- `sgit_ai/api/` — SGit-AI Transfer API client
- `sgit_ai/cli/` — CLI commands
