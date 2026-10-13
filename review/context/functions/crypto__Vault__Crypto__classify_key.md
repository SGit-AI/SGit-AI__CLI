## `classify_key` in sgit_ai/crypto/Vault__Crypto.py (L86-L103)

```python
# L95-L103
from sgit_ai.safe_types.Enum__Key_Kind import Enum__Key_Kind
key = (key or '').strip()
if key.startswith(READ_KEY_PUBLIC_PREFIX):
    return Enum__Key_Kind.READ_PUBLIC
if key.startswith(READ_KEY_PREFIX) or key.startswith(LEGACY_READ_KEY_PREFIX):
    return Enum__Key_Kind.READ_PRIVATE
if key.startswith(VAULT_KEY_PREFIX) or key.startswith(LEGACY_VAULT_KEY_PREFIX):
    return Enum__Key_Kind.VAULT
return Enum__Key_Kind.UNKNOWN
```

**Purpose:** Reads what a credential *declares* itself to be, by prefix only, never by shape (docstring L87-L93). It is the primitive that lets a read-only surface refuse a vault key, and that lets `read_key_from_credential` decide whether a 64-hex head is a read key or a passphrase.

**Inputs & Assumptions:**
- `key` (str or None): Trust: **untrusted**.
- Precondition: none.

**Outputs & Effects:**
- Returns one of four `Enum__Key_Kind` values (`sgit_ai/safe_types/Enum__Key_Kind.py:L11-L14`). Pure.
- Postcondition: `UNKNOWN` for every bare / legacy-bare / non-key string. Nothing here inspects the material after the prefix; a string `sgit_private_vault_` followed by garbage is `VAULT`.

**Block-by-Block:** one chain of `startswith` checks, L97-L103. Order matters only in that `READ_KEY_PUBLIC_PREFIX` (`sgit_public_read_`) and `READ_KEY_PREFIX` (`sgit_private_read_`) are disjoint, so no ordering ambiguity exists.

**Cross-Function Dependencies:**
- No external calls (local import of the enum, L95).
- Callers: `CLI__Vault._warn_private_key_over_plain_http` (L150: exempts `READ_PUBLIC` from the http:// warning), `CLI__Vault._resolve_clone_credential` (L180-L182: `VAULT` suppresses the 64-hex shorthand heuristic), `CLI__Token_Store.read_key_from_credential` (L232).
- Invariant coupling: the design rule "an explicit declaration beats the heuristic" (`CLI__Vault.py:L163-L176` docstring) rests on this function being the only classifier. Tests: `test_Vault__Crypto__Key_Prefixes.py::Test_Key_Classification` (vault, private read, public read, bare→UNKNOWN), `::Test_Legacy_Prefixes_Still_Accepted::test_legacy_classifies_correctly`.

**Open Questions:** none.
