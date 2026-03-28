# Simple Tokens — Technical Brief

## Overview

Simple Tokens are the CLI's mechanism for generating and resolving short-lived transfer
identifiers and symmetric encryption keys for use with the SGit-AI Transfer API.
They are **client-side only** — no server API involved. The server only sees a
`transfer_id` derived from the token; it never sees the token itself.

---

## Token Format

```
word-word-NNNN
```

- Two lowercase words separated by hyphens, followed by a 4-digit number
- Regex: `^[a-z]+-[a-z]+-\d{4}$`
- Examples: `maple-river-7291`, `echo-flame-0042`

**Wordlist note:** The CLI uses a **different 320-word wordlist** from the browser.
This adds entropy. Any token matching `word-word-NNNN` resolves in both browser and CLI
regardless of which wordlist was used to generate it.

---

## Key Derivation

### Transfer ID

```
transfer_id = SHA-256(token.encode('utf-8')).hexdigest()[:12]
```

- 12-character hex prefix of the SHA-256 digest of the UTF-8 token string
- Used as the server-side transfer key

### AES-256-GCM Decryption Key

```
key = PBKDF2-HMAC-SHA256(
    password  = token.encode('utf-8'),
    salt      = b'sgraph-send-v1',
    iterations = 600_000,
    dklen     = 32
)
```

- 32-byte symmetric key for AES-256-GCM decryption
- Fixed salt `b'sgraph-send-v1'`
- 600,000 PBKDF2 iterations

---

## Python Reference Implementation

```python
import hashlib
import os
import re

SALT       = b'sgraph-send-v1'
ITERATIONS = 600_000
TOKEN_PATTERN = r'^[a-z]+-[a-z]+-\d{4}$'

def is_friendly_token(s: str) -> bool:
    return bool(re.match(TOKEN_PATTERN, s))

def derive_transfer_id(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()[:12]

def derive_key(token: str) -> bytes:
    return hashlib.pbkdf2_hmac(
        'sha256',
        token.encode('utf-8'),
        SALT,
        ITERATIONS,
        dklen=32
    )
```

---

## Encryption Scheme

Payload encrypted with AES-256-GCM using the derived key.

---

## Interoperability

- Any `word-word-NNNN` pattern resolves in both browser (Web Crypto API) and CLI
- The derivation algorithm is identical in both; only the generation wordlist differs
- Browser PBKDF2 uses `SubtleCrypto.deriveBits` with `PBKDF2` + `SHA-256`
- CLI uses `hashlib.pbkdf2_hmac`

---

## Planned CLI Implementation

- New safe type: `Safe_Str__Simple_Token` with regex `^[a-z]+-[a-z]+-\d{4}$`
- New safe type: `Safe_Str__Transfer_Id` (already exists — 12-char hex)
- New class: `Simple_Token` (Type_Safe) — wraps `derive_transfer_id()` and `derive_key()`
- CLI wordlist: 320 words, different from browser wordlist, stored as a Python constant
- CLI command: `sgit-ai share` — generates token, encrypts vault, uploads to Transfer API
- CLI command: `sgit-ai publish` — same multi-level zip structure (see feature brief)

---

*Date: 2026-03-27*
