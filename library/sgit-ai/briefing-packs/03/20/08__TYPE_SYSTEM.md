# 08 — Type System

**Author:** Developer
**Audience:** Developers (MUST READ before writing code)

## Type_Safe Framework

All data modelling uses `osbot_utils.type_safe.Type_Safe`. This is NOT Pydantic,
NOT dataclasses, NOT attrs. It's a custom framework with specific rules.

## The Five Rules

### Rule 1: Zero Raw Primitives

**NEVER** use `str`, `int`, `float`, or `dict` as fields in Type_Safe classes.

```python
# BAD - will be flagged in review
class Schema__Vault(Type_Safe):
    vault_id : str             # raw str!
    version  : int             # raw int!

# GOOD - domain-specific types
class Schema__Vault(Type_Safe):
    vault_id : Safe_Str__Vault_Id     # validated, bounded
    version  : Safe_UInt__Vault_Version  # unsigned, bounded
```

### Rule 2: Classes for Everything

No module-level functions. No `@staticmethod`. All behavior in methods.

```python
# BAD
def derive_key(passphrase, salt):
    ...

# GOOD
class Vault__Crypto(Type_Safe):
    def derive_key(self, passphrase, salt):
        ...
```

### Rule 3: No Pydantic, No Mocks

- Use `Type_Safe` for all data modelling
- Use `cryptography` for crypto
- Write real tests against real objects
- Use `Vault__API__In_Memory` for API tests (not mock.patch)

### Rule 4: Immutable Defaults

Collections must use type annotation without a default value:

```python
# BAD - mutable default
class Schema__Commit(Type_Safe):
    parents : list = []                    # shared mutable default!

# GOOD - annotation only, framework initializes
class Schema__Commit(Type_Safe):
    parents : list[Safe_Str__Object_Id]    # framework creates new list per instance
```

### Rule 5: Naming Conventions

| Pattern             | Format                      | Example                       |
|---------------------|-----------------------------|-------------------------------|
| Type_Safe classes   | `Verb__Noun` or `Schema__X` | `Vault__Crypto`, `Schema__Object_Commit` |
| Safe types          | `Safe_{Type}__{Domain}`     | `Safe_Str__Vault_Id`          |
| Enums               | `Enum__{Domain}`            | `Enum__Branch_Type`           |
| Test classes        | `Test_{ClassName}`          | `Test_Vault__Crypto`          |
| Test files          | `test_{ClassName}.py`       | `test_Vault__Crypto.py`       |

## Creating a Safe_Str Type

```python
import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str

class Safe_Str__Vault_Id(Safe_Str):
    regex           = re.compile(r'[^a-zA-Z0-9\-]')    # chars to REJECT
    max_length      = 64
    allow_empty     = False
    trim_whitespace = True
```

The `regex` field is a **rejection pattern** — it matches characters that are NOT allowed.
If any character matches the regex, validation fails with a ValueError.

### Safe_Str Validation Flow

```
  Input string
       |
       v
  trim_whitespace?  -->  strip()
       |
       v
  allow_empty?  -->  reject "" if False
       |
       v
  max_length?  -->  reject if len > max_length
       |
       v
  regex?  -->  reject if regex.search(value) finds matches
       |
       v
  Valid Safe_Str__*
```

## Creating a Schema Class

```python
from osbot_utils.type_safe.Type_Safe import Type_Safe

class Schema__Object_Commit(Type_Safe):
    schema       : Safe_Str__Schema_Version  = None   # nullable with None
    tree_id      : Safe_Str__Object_Id       = None
    parents      : list[Safe_Str__Object_Id]           # list (no default!)
    timestamp_ms : Safe_UInt__Timestamp                 # required (no default)
    message_enc  : Safe_Str__Encrypted_Value = None    # nullable
```

### Nullable vs Required

- `field : SomeType = None` — nullable, can be omitted
- `field : SomeType` — required, must be provided (but framework may init to default)
- `field : list[SomeType]` — required list, framework creates empty list per instance

### Serialization

```python
# To JSON-compatible dict
data = obj.json()

# From JSON-compatible dict
obj = Schema__Object_Commit.from_json(data)

# Round-trip invariant (MUST hold for all schemas)
assert Schema__Object_Commit.from_json(obj.json()).json() == obj.json()
```

## Existing Safe_* Types Reference

### Safe_Str Types (35 types)

| Type                          | Regex/Validation                    | Max Length |
|-------------------------------|-------------------------------------|------------|
| Safe_Str__Vault_Id            | `[^a-zA-Z0-9\-]`                   | 64         |
| Safe_Str__Object_Id           | Must match `obj-cas-imm-[0-9a-f]+` | 64         |
| Safe_Str__Branch_Id           | Must match `branch-(named\|clone)-[0-9a-f]+` | 64 |
| Safe_Str__Ref_Id              | Must match `ref-pid-(muw\|snw)-[0-9a-f]+` | 64 |
| Safe_Str__Key_Id              | Must match `key-rnd-imm-[0-9a-f]+` | 64         |
| Safe_Str__Index_Id            | Must match `idx-pid-muw-[0-9a-f]+` | 64         |
| Safe_Str__Encrypted_Value     | Base64 data                         | 65536      |
| Safe_Str__Base64_Data         | Base64 characters                   | 1MB        |
| Safe_Str__Vault_Key           | Format: `{passphrase}:{vault_id}`   | 256        |
| Safe_Str__Access_Token        | Alphanumeric + special              | 256        |
| Safe_Str__Base_URL            | URL format                          | 512        |
| Safe_Str__SHA256              | Hex string                          | 64         |
| Safe_Str__Signature           | Base64 data                         | 1024       |
| Safe_Str__PEM_Key             | PEM format                          | 8192       |
| Safe_Str__ISO_Timestamp       | ISO 8601 format                     | 32         |
| Safe_Str__File_Path           | Path characters                     | 1024       |
| Safe_Str__Vault_Path          | Path characters                     | 1024       |
| Safe_Str__Content_Hash        | Hex string                          | 12         |
| Safe_Str__Content_Type        | MIME type                           | 256        |
| Safe_Str__Commit_Message      | Any text                            | 4096       |
| Safe_Str__Branch_Name         | Alphanumeric + dash                 | 64         |
| Safe_Str__Vault_Name          | Alphanumeric + dash/space           | 128        |
| Safe_Str__Vault_Passphrase    | Any printable                       | 256        |
| Safe_Str__Schema_Version      | Alphanumeric + underscore           | 32         |
| Safe_Str__Transfer_Id         | Alphanumeric                        | 64         |
| Safe_Str__File_Id             | Path characters                     | 256        |
| Safe_Str__Key_Fingerprint     | Hex string                          | 64         |
| Safe_Str__Author_Key_Id       | Key ID format                       | 64         |
| Safe_Str__Write_Key           | Hex string                          | 128        |
| Safe_Str__Secret_Key          | Alphanumeric                        | 256        |
| Safe_Str__Pending_Id          | UUID-like                           | 64         |

### Safe_UInt Types (5 types)

| Type                       | Range / Constraints          |
|----------------------------|------------------------------|
| Safe_UInt__Timestamp       | >= 0 (milliseconds)          |
| Safe_UInt__File_Size       | >= 0 (bytes)                 |
| Safe_UInt__Key_Size        | >= 0 (bits)                  |
| Safe_UInt__Vault_Version   | >= 0                         |
| Safe_UInt__Lock_Timeout    | >= 0 (seconds)               |

### Enum Types (4 types)

| Type                    | Values                            |
|-------------------------|-----------------------------------|
| Enum__Branch_Type       | NAMED, CLONE                      |
| Enum__Sync_State        | CLEAN, DIRTY, CONFLICT            |
| Enum__Batch_Op          | WRITE, WRITE_IF_MATCH, DELETE, READ |
| Enum__Provenance_Mode   | FULL, LIGHT, NONE                 |

## Adding a New Type

1. Create `sg_send_cli/safe_types/Safe_Str__My_New_Type.py`
2. Create `tests/unit/safe_types/test_Safe_Str__My_New_Type.py`
3. Test valid values, boundary values, and rejection cases
4. Use in schema classes

```python
# sg_send_cli/safe_types/Safe_Str__My_New_Type.py
import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str

class Safe_Str__My_New_Type(Safe_Str):
    regex           = re.compile(r'[^a-zA-Z0-9]')
    max_length      = 32
    allow_empty     = False
    trim_whitespace = True
```
