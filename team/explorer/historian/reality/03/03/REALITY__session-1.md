# Reality Document — Session 1

**Date:** 3 March 2026
**Version:** v0.1.0
**Status:** Session 1 complete

---

## What Exists

### Package Structure

```
SG_Send__CLI/
├── CLAUDE.md                          # Main project guide
├── pyproject.toml                     # Package config (sg-send-cli v0.1.0)
├── .github/workflows/
│   ├── tests.yml                      # CI: pytest on Python 3.11/3.12
│   └── publish.yml                    # CD: PyPI publish on v* tags
├── sg_send_cli/
│   ├── __init__.py                    # Imports VERSION
│   ├── _version.py                    # VERSION = 'v0.1.0'
│   ├── safe_types/                    # 11 domain types (all tested)
│   │   ├── Safe_Str__Vault_Id.py      # 8 hex chars
│   │   ├── Safe_Str__Transfer_Id.py   # 12 alphanumeric chars
│   │   ├── Safe_Str__Vault_Passphrase.py  # 1-256 printable ASCII
│   │   ├── Safe_Str__Vault_Key.py     # pass:vid:sid format
│   │   ├── Safe_Str__SHA256.py        # 64 hex chars
│   │   ├── Safe_Str__Access_Token.py  # JWT-safe chars
│   │   ├── Safe_Str__Vault_Name.py    # Human-readable name
│   │   ├── Safe_Str__File_Path.py     # Filesystem path
│   │   ├── Safe_UInt__File_Size.py    # 0 to 100MB
│   │   ├── Safe_UInt__Vault_Version.py # 0 to 999999
│   │   └── Enum__Sync_State.py        # 8 sync states
│   ├── schemas/                       # 5 Type_Safe schemas (all tested)
│   │   ├── Schema__Vault_Meta.py
│   │   ├── Schema__Vault_Config.py
│   │   ├── Schema__Vault_Index_Entry.py
│   │   ├── Schema__Vault_Index.py
│   │   └── Schema__Transfer_File.py
│   ├── crypto/                        # Vault encryption (tested)
│   │   └── Vault__Crypto.py           # AES-256-GCM, PBKDF2, HKDF
│   ├── sync/                          # Placeholder
│   ├── api/                           # Placeholder
│   └── cli/                           # Placeholder
├── tests/
│   └── unit/
│       ├── safe_types/                # 9 test files, 55 tests
│       ├── schemas/                   # 5 test files, 20 tests
│       └── crypto/                    # 1 test file, 21 tests
└── team/explorer/                     # 6 role directories with READMEs
    ├── CLAUDE.md
    ├── architect/README.md
    ├── dev/README.md
    ├── qa/README.md
    ├── devops/README.md
    ├── librarian/README.md
    └── historian/README.md
```

### Test Summary

- **96 tests total, all passing**
- Safe_* types: 55 tests (validation, edge cases, type preservation)
- Schemas: 20 tests (instantiation, round-trip json↔from_json)
- Crypto: 21 tests (interop vectors, round-trip encrypt/decrypt, full pipeline)

### Interop Test Vectors

Deterministic vectors stored in `test_Vault__Crypto.py`:

| Operation | Input | Expected Output |
|-----------|-------|-----------------|
| PBKDF2 | passphrase=`test-passphrase-123`, salt=`000102...0f` | `b30143c284de844e...` |
| AES-GCM | key=`012345...ef`, iv=`000102...0b`, pt=`Hello, SG/Send vault!` | `000102...e0` |
| HKDF | vault_key=`abcdef...89`, context=`documents/readme.txt` | `ca8412924aa22f62...` |
| SHA-256 | `test file content for hashing` | `034527873967b866...` |

### Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| osbot-utils | 3.72.0 | Type_Safe framework |
| cryptography | 46.0.5 | AES-GCM, PBKDF2, HKDF |
| pytest | 9.0.2 | Testing |
| pytest-cov | 7.0.0 | Coverage |

---

## What Does NOT Exist Yet

- CLI commands (clone, push, pull, status)
- API client (Transfer API wrapper)
- Sync engine (local ↔ remote state diffing)
- `.sg_vault/` directory management
- Browser-side interop verification (vectors exist but need JS validation)
- PyPI publishing (pipeline exists but package not yet published)

## Key Decisions Made

1. **Package name:** `sg-send-cli` (PyPI), `sg_send_cli` (import)
2. **Crypto params:** AES-256-GCM, PBKDF2-SHA256 600K iterations, HKDF-SHA256
3. **Vault key format:** `{passphrase}:{vault_id}:{settings_transfer_id}`
4. **Encrypt format:** `IV (12 bytes) || ciphertext || GCM tag (16 bytes)`
5. **HKDF info:** `sg-send-file-key{file_context}` with no salt
6. **Type_Safe:** Zero raw primitives, all fields are Safe_* or Type_Safe subclasses
