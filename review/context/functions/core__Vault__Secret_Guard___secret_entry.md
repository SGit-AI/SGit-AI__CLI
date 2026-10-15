## `_secret_entry` in sgit_ai/core/Vault__Secret_Guard.py (L75-L90)

```python
# L79-L90
try:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names  = [n.replace('\\', '/') for n in zf.namelist()]
        layout = any(n.startswith(('bare/', '.sg_vault/')) or n in ('manifest.json', 'VAULT-KEY') for n in names)
        for raw, name in zip(zf.namelist(), names):
            if SECRET_ENTRY.search(name) or (layout and TOKEN_ENTRY.search(name)):
                return name
            if PEM_ENTRY.search(name) and self._holds_private_key(zf, raw):
                return name
except (zipfile.BadZipFile, OSError, ValueError, RuntimeError):
    return ''
return ''
```

**Purpose:** Name the first zip member that is a vault secret, or `''`. A `.pem` counts only if it holds a private key; `local/token` only inside sgit's own layout (docstring L76-L78, review 0a0707d F4 — a public certificate bundle is ordinary content).

**Inputs & Assumptions:**
- `content`: bytes of a file that starts with `PK\x03\x04`. Trust: user's file — but the *regexes* decide, so what they match is what is protected: `SECRET_ENTRY` (L19) `VAULT-KEY` at any depth or `[.sg_vault/]local/vault_key`; `TOKEN_ENTRY` (L20) `[.sg_vault/]local/token`, gated on `layout`; `PEM_ENTRY` (L21) `[.sg_vault/]local/<leaf>.pem`.
- Backslashes normalised for matching (L81) — a Windows-built zip is seen the same way.
- Precondition: the archive parses. A malformed/encrypted/huge archive → `BadZipFile`/`RuntimeError`/`OSError`/`ValueError` → `''` i.e. **not a secret** (fail-open, L88-L89). A zip bomb: `_holds_private_key` streams in 64 KiB chunks (no full decompression into memory), but it reads the **whole** entry (F2, L92-L94) — a multi-GB decompressed `.pem` entry is read to the end; `nothing found` that bounds the decompressed size (`zipfile` has no ratio limit).

**Outputs & Effects:** Pure. Returns the matching name or `''`.

**Block-by-Block:**
- L82 `layout`: true when the archive looks like an sgit backup (has `bare/`, `.sg_vault/`, `manifest.json` or `VAULT-KEY`). Only the token rule depends on it.
- L84: `VAULT-KEY` anywhere, or `local/vault_key` under `.sg_vault/` or at the archive root. A key file under a different path (e.g. `backup/keys/vault_key`) is not matched — by regex design.
- L86: `.pem` directly under `local/`; content-checked.

**Cross-Function Dependencies:** Callee `_holds_private_key` L92-L103 (reads `zf.open(raw)` in 64 KiB chunks with a `len(PEM_MARKER)-1` byte overlap, L101-L103; `PEM_MARKER = b'PRIVATE KEY'` L24 — matches `-----BEGIN PRIVATE KEY-----`, `BEGIN EC PRIVATE KEY`, `BEGIN ENCRYPTED PRIVATE KEY`). Callers: `refuse_bytes` L67. Tests: `test_a_public_certificate_bundle_is_committed`, `test_a_private_key_pem_is_still_refused_and_the_override_names_the_file`, `test_a_private_key_after_64_kib_of_certificates_is_found`.

**Open Questions:**
- Fail-open on unparseable archives (L88-L89): a zip that `zipfile` rejects but another tool opens would carry its contents into the vault unexamined. Whether that is reachable with the backups sgit itself produces: no (they are standard zips).
