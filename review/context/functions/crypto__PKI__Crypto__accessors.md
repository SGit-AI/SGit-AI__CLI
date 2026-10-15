# `PKI__Crypto` one-expression helpers in sgit_ai/crypto/PKI__Crypto.py

All wrap `cryptography` calls with no branches. Pure except key generation (randomness).

---

## `generate_encryption_key_pair` (L18-L22)
RSA-4096, e=65537; returns `(private, public)`. Caller: `PKI__Key_Store.generate_and_store` L14. Classical PKI noted at TM-R20.

## `generate_signing_key_pair` (L24-L26)
ECDSA on SECP256R1 (P-256). Callers: `PKI__Key_Store.generate_and_store` L15, `Vault__Key_Manager.generate_branch_key_pair` L22. Every commit/tag signing key in a vault comes from here.

## `export_public_key_pem` (L30-L34)
SubjectPublicKeyInfo PEM as str. Callers: `Vault__Key_Manager.store_public_key` L25, `PKI__Key_Store.generate_and_store` L26, L29.

## `import_public_key_pem` (L48-L49)
`load_pem_public_key(pem_str.encode())`. Raises on malformed input (`test_PKI__Crypto__Hardening.py::test_pem_import__*`). Callers: `Vault__Key_Manager.load_public_key` L38 (PEM from a read-key-encrypted file the host served), `PKI__Key_Store.load_key_pair` L62,L66, `hybrid_decrypt` L148 (PEM from a keyring contact file), `CLI__PKI.py:L80,L86,L143,L169`.

## `compute_fingerprint` (L57-L62)
`sha256(DER SubjectPublicKeyInfo)` hex, first 16 chars, prefixed `sha256:` (64 bits). Must match browser and server (comment L55; `test_PKI__Crypto.py::test_fingerprint_matches_server_implementation`). Callers: `PKI__Key_Store.generate_and_store` L17-L18 (becomes the key DIRECTORY name via `_key_dir`), `CLI__PKI.py:L81,L87` (import computes the fingerprint from the PEM itself rather than trusting the bundle's claim).
