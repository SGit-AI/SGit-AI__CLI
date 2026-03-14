# CLAUDE.md — SG_Send__CLI

## Project Overview

**sg-send-cli** is a Python CLI tool that syncs encrypted vaults between a local filesystem and SG/Send's Transfer API. Think of it as "git for encrypted vaults."

- **Package name:** `sg-send-cli`
- **Import name:** `sg_send_cli`
- **Python:** >=3.11
- **Dependencies:** `osbot-utils` (Type_Safe framework), `cryptography` (AES-GCM, HKDF)

## Architecture

```
sg_send_cli/
├── _version.py        # VERSION = 'v0.1.0'
├── safe_types/        # Custom Safe_* domain types (no raw primitives)
├── schemas/           # Pure data Type_Safe schema classes
├── crypto/            # Vault__Crypto: encrypt/decrypt/derive_key
├── sync/              # Local filesystem vault sync logic
├── api/               # SG/Send Transfer API client
└── cli/               # CLI entry point
```

## Critical Rules

### Type_Safe Rules (MUST FOLLOW)

1. **Zero raw primitives in Type_Safe classes.** Never use `str`, `int`, `float`, or `dict` directly as fields. Always use `Safe_Str`, `Safe_Int`, `Safe_UInt`, `Safe_Float`, or a domain-specific subclass.

2. **Classes for everything.** No module-level functions. No `@staticmethod`. All behavior lives in methods on Type_Safe classes.

3. **No Pydantic. No boto3. No mocks.** Use `osbot_utils.type_safe` for all data modeling. Use `cryptography` for crypto. Write real tests against real objects.

4. **Immutable defaults only.** Type_Safe class fields must use immutable defaults. For collections, use type annotation without a value (e.g., `items : list[Item]`), never `items : list = []`.

5. **Naming conventions:**
   - Type_Safe classes: `Schema__Vault_Meta`, `Vault__Crypto`
   - Safe types: `Safe_Str__Vault_Id`, `Safe_UInt__Vault_Version`
   - Test classes: `Test_Schema__Vault_Meta`, `Test_Vault__Crypto`
   - Test files: `test_Schema__Vault_Meta.py`, `test_Vault__Crypto.py`

6. **Round-trip invariant.** Every schema must pass: `assert cls.from_json(obj.json()).json() == obj.json()`

### Safe_* Type Pattern

```python
import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str

class Safe_Str__Vault_Id(Safe_Str):
    regex           = re.compile(r'[^a-zA-Z0-9\-]')
    max_length      = 64
    allow_empty     = False
    trim_whitespace = True
```

### Schema Pattern

```python
from osbot_utils.type_safe.Type_Safe import Type_Safe

class Schema__Vault_Meta(Type_Safe):
    vault_id : Safe_Str__Vault_Id  = None
    version  : Safe_UInt__Version
    name     : Safe_Str__Vault_Name = None
```

### CLI Rules

7. **No code in `cli/__init__.py`.** The `cli/__init__.py` file must only contain imports and the `main()` entry point delegation. All command logic lives in dedicated `CLI__*` classes (e.g., `CLI__Vault`, `CLI__PKI`).

8. **No `__init__.py` files in tests.** Only the main source code (`sg_send_cli/`) should have `__init__.py` files. The `tests/` directory tree must not contain any `__init__.py` files.

### Crypto Interop Requirement

All crypto operations (AES-256-GCM, HKDF-SHA256, PBKDF2) must produce output that matches the browser (Web Crypto API) byte-for-byte given the same inputs. Test vectors are mandatory.

## Commands

```bash
# Run all unit tests (Python 3.11 default)
pytest tests/unit/

# Run specific test file
pytest tests/unit/safe_types/test_Safe_Str__Vault_Id.py

# Run with coverage
pytest --cov=sg_send_cli --cov-report=term-missing

# Install in dev mode
pip install -e ".[dev]"
```

## Integration Testing (Python 3.12 venv)

Integration tests run against a real in-memory SG/Send server provided by `sgraph-ai-app-send`, which requires Python >= 3.12. The default environment uses Python 3.11, so a separate venv is needed.

```bash
# Setup (one-time)
python3.12 -m venv /tmp/sg-send-venv-312
/tmp/sg-send-venv-312/bin/pip install -e ".[dev]"
/tmp/sg-send-venv-312/bin/pip install sgraph-ai-app-send

# Run integration tests
/tmp/sg-send-venv-312/bin/python -m pytest tests/integration/ -v
```

See `team/explorer/dev/python-3.12-venv-integration-testing.md` for full details.

## Team

This project uses the Explorer team pattern. See `team/explorer/` for role definitions.
