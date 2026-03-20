# 11 — Developer Guide

**Author:** Developer + Librarian
**Audience:** New developers, LLM sessions working on this codebase

## Prerequisites

- Python >= 3.11 (3.12 for integration tests)
- Git
- `pip` or `poetry`

## Setup

```bash
# Clone the repo
git clone https://github.com/the-cyber-boardroom/SG_Send__CLI.git
cd SG_Send__CLI

# Install in dev mode
pip install -e ".[dev]"

# Verify
pytest tests/unit/ -v --tb=short
# Expected: 971 passed, 4 xfailed, 87 skipped
```

## Project Structure

```
SG_Send__CLI/
  |-- sg_send_cli/              <-- source code (9 packages, 93 classes)
  |     |-- safe_types/         <-- Safe_Str/Safe_UInt domain types (44 types)
  |     |-- schemas/            <-- Type_Safe schema classes (21 schemas)
  |     |-- crypto/             <-- AES-GCM, PBKDF2, HKDF, PKI (3 classes)
  |     |-- objects/            <-- CAS object store, refs, commits (4 classes)
  |     |-- sync/               <-- Sync engine: init/commit/push/pull/merge (12 classes)
  |     |-- api/                <-- HTTP client + backends (6 classes)
  |     |-- pki/                <-- Key ring + key store (2 classes)
  |     |-- secrets/            <-- Credential store (1 class)
  |     +-- cli/                <-- CLI commands + arg parsing (7 classes)
  |
  |-- tests/                    <-- test suite (NO __init__.py files!)
  |     |-- unit/               <-- unit tests (971 tests)
  |     |-- integration/        <-- integration tests (need Python 3.12 venv)
  |     +-- qa/                 <-- scenario tests (excluded by default)
  |
  |-- team/                     <-- team docs, briefs, guides, roles
  |     |-- explorer/           <-- Explorer team (feature development)
  |     |-- villager/           <-- Villager team (refactoring, quality)
  |     +-- humans/             <-- Human briefs (READ-ONLY!)
  |
  |-- CLAUDE.md                 <-- AI assistant instructions (READ THIS FIRST)
  |-- pyproject.toml            <-- package config
  +-- README.md                 <-- quick start
```

## Development Workflow

### Adding a New Feature

```
1. Read CLAUDE.md                    <-- understand the rules
2. Read this briefing pack           <-- understand the architecture
3. Create Safe_* types if needed     <-- validation at the boundary
4. Create Schema if needed           <-- data model
5. Implement in the right layer      <-- crypto/objects/sync/api/cli
6. Write tests                       <-- real objects, no mocks
7. Run full test suite               <-- pytest tests/unit/ -v
8. Commit and push
```

### Adding a New CLI Command

1. Add argument parser in `CLI__Main.build_parser()`
2. Add handler method in `CLI__Vault` (or `CLI__PKI` for PKI commands)
3. Wire parser to handler with `set_defaults(func=self.vault.cmd_xxx)`
4. Add test in `tests/unit/cli/`

### Adding a New Schema

```python
# 1. Create schema file
# sg_send_cli/schemas/Schema__My_Thing.py

from osbot_utils.type_safe.Type_Safe import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Vault_Id import Safe_Str__Vault_Id

class Schema__My_Thing(Type_Safe):
    vault_id : Safe_Str__Vault_Id = None
    # ... fields with Safe_* types only ...

# 2. Create test file
# tests/unit/schemas/test_Schema__My_Thing.py

class Test_Schema__My_Thing:
    def test_round_trip(self):
        obj = Schema__My_Thing(vault_id='abc12345')
        assert Schema__My_Thing.from_json(obj.json()).json() == obj.json()

    def test_invalid_vault_id_rejected(self):
        with pytest.raises(ValueError):
            Schema__My_Thing(vault_id='has spaces!!!')
```

### Adding a New Safe_* Type

```python
# 1. Create type file
# sg_send_cli/safe_types/Safe_Str__My_Type.py

import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str

class Safe_Str__My_Type(Safe_Str):
    regex           = re.compile(r'[^a-zA-Z0-9\-]')
    max_length      = 64
    allow_empty     = False
    trim_whitespace = True

# 2. Create test file
# tests/unit/safe_types/test_Safe_Str__My_Type.py

class Test_Safe_Str__My_Type:
    def test_valid_value(self):
        t = Safe_Str__My_Type('hello-world')
        assert str(t) == 'hello-world'

    def test_rejects_spaces(self):
        with pytest.raises(ValueError):
            Safe_Str__My_Type('has spaces')

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            Safe_Str__My_Type('')
```

## Key Files to Read

When starting work on this project, read these files in order:

```
1. CLAUDE.md                          <-- rules and constraints
2. 00__INDEX.md (this pack)           <-- navigation
3. 01__PROJECT_OVERVIEW.md            <-- what is this?
4. 08__TYPE_SYSTEM.md                 <-- how to write code
5. 02__ARCHITECTURE.md                <-- system map
6. The specific layer doc for your task (03-07)
7. 10__KNOWN_ISSUES.md                <-- don't duplicate bugs
```

## Common Tasks

### Running tests

```bash
pytest tests/unit/ -v                    # all unit tests
pytest tests/unit/sync/ -v               # one package
pytest tests/unit/sync/test_Vault__Sync__Push.py -v  # one file
pytest tests/unit/ --cov=sg_send_cli --cov-report=term-missing  # with coverage
```

### Integration tests (requires Python 3.12)

```bash
# One-time setup
python3.12 -m venv /tmp/sg-send-venv-312
/tmp/sg-send-venv-312/bin/pip install -e ".[dev]"
/tmp/sg-send-venv-312/bin/pip install sgraph-ai-app-send

# Run
/tmp/sg-send-venv-312/bin/python -m pytest tests/integration/ -v
```

### Manual end-to-end test

```bash
# Init a vault
sgit init /tmp/test-vault

# Add files
echo "hello" > /tmp/test-vault/hello.txt

# Check status
sgit status /tmp/test-vault

# Commit
sgit commit "first commit" -d /tmp/test-vault

# View log
sgit log /tmp/test-vault --oneline

# Inspect tree
sgit inspect-tree /tmp/test-vault

# Push (needs token)
sgit push /tmp/test-vault --token YOUR_TOKEN
```

## Architecture Decision Records

Key decisions are documented in:
- `team/decisions/2026-03-14__vault_v2_architecture_decisions.md`
- `team/explorer/architect/reviews/03/17/v0.8.6__architect-review__architecture-deep-review.md`
- `team/explorer/historian/reality/03/11/REALITY__current-capabilities.md`

## Don'ts

- **Don't add `__init__.py` to test directories** — only source code has them
- **Don't use raw str/int/dict in Type_Safe classes** — always use Safe_* types
- **Don't use mock.patch** — use Vault__API__In_Memory or real objects
- **Don't use Pydantic or dataclasses** — Type_Safe only
- **Don't put code in `cli/__init__.py`** — only imports and main() delegation
- **Don't use @staticmethod** — all behavior in instance methods
- **Don't modify files in `team/humans/dinis_cruz/briefs/`** — those are READ-ONLY

## Naming Cheatsheet

```
Source file:  Vault__Crypto.py        -> Class: Vault__Crypto
Schema file:  Schema__Object_Commit.py -> Class: Schema__Object_Commit
Safe type:    Safe_Str__Vault_Id.py   -> Class: Safe_Str__Vault_Id
Test file:    test_Vault__Crypto.py   -> Class: Test_Vault__Crypto
Test method:  test_encrypt_decrypt_round_trip
```

## Upcoming Rename: sg-send-cli -> sgit-ai

The project is being renamed:
- PyPI package: `sg-send-cli` -> `sgit-ai`
- CLI command: `sgit` (already works, will become primary)
- Domain: `sgit.ai`
- Python import: `sg_send_cli` -> TBD (requires coordinated rename)
- Repository: `SG_Send__CLI` -> TBD

When the rename happens, it will need:
1. Update `pyproject.toml` (name, scripts, packages)
2. Rename `sg_send_cli/` directory
3. Update all imports
4. Update `CLAUDE.md`
5. Update CI/CD workflows
6. PyPI redirect or new package
