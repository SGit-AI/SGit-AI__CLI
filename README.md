# sgit-ai

**Git-like encrypted vault management for the command line.**

sgit-ai syncs encrypted vaults between your local filesystem and SGit-AI's Transfer API. Every file is encrypted client-side with AES-256-GCM before it leaves your machine — the server never sees plaintext.

[![PyPI](https://img.shields.io/pypi/v/sgit-ai)](https://pypi.org/project/sgit-ai/)
[![Python](https://img.shields.io/pypi/pyversions/sgit-ai)](https://pypi.org/project/sgit-ai/)
[![License](https://img.shields.io/pypi/l/sgit-ai)](https://github.com/SGit-AI/SGit-AI__CLI/blob/dev/LICENSE)

## Install

```bash
pip install sgit-ai
```

This gives you two CLI commands: `sgit-ai` and the shorthand `sgit`.

## Quick Start

```bash
# Create a new encrypted vault
sgit init my-vault

# Add files to the working directory
cp important-doc.pdf my-vault/

# Commit and push
sgit commit "initial upload" -d my-vault
sgit push my-vault

# Clone an existing vault on another machine
sgit clone <vault-key>
```

## Features

### Encrypted Vault Sync

Clone, commit, push, and pull encrypted vaults — just like git, but every object is AES-256-GCM encrypted before upload.

```bash
sgit clone <vault-key>          # Download and decrypt a vault
sgit status                     # Show uncommitted changes
sgit commit "my changes"        # Snapshot local changes
sgit pull                       # Fetch and merge remote changes
sgit push                       # Upload to remote
sgit branches                   # List all branches
```

### Client-Side Encryption

All crypto runs locally. The server stores only ciphertext.

- **AES-256-GCM** for file encryption with per-file HKDF-derived keys
- **PBKDF2-SHA256** (600k iterations) for vault key derivation
- **Content-addressable storage** — encrypted objects stored by hash
- **Web Crypto API compatible** — byte-for-byte interop with browser implementations

### PKI and Digital Signatures

Built-in public key infrastructure for signing and encrypting files between users.

```bash
sgit pki keygen                             # Generate RSA-4096 + ECDSA P-256 key pair
sgit pki sign doc.pdf --fingerprint <fp>    # Create detached signature
sgit pki verify doc.pdf sig.json            # Verify signature
sgit pki encrypt doc.pdf --recipient <fp>   # Hybrid RSA-OAEP + AES-256-GCM encryption
sgit pki decrypt doc.pdf.enc --fingerprint <fp>
```

### Vault Inspection

Debug and inspect the internals of any vault.

```bash
sgit inspect                    # Vault state overview
sgit log --oneline --graph      # Commit history
sgit inspect-tree               # Current tree entries
sgit inspect-stats              # Object store statistics
sgit cat-object <id>            # Decrypt and display an object
sgit fsck --repair              # Verify integrity and repair
```

### Credential and Remote Management

```bash
# Store vault keys under friendly aliases
sgit vault add my-project --vault-key <key>
sgit vault list

# Configure multiple remotes
sgit remote add origin <url> <vault-id>
sgit remote list
```

## Architecture

```
sgit_ai/
├── cli/           # CLI commands (sgit-ai / sgit)
├── crypto/        # AES-256-GCM, PBKDF2, HKDF, RSA-OAEP, ECDSA
├── sync/          # Clone, commit, push, pull, merge, branching
├── api/           # SGit-AI Transfer API client
├── pki/           # Key store and contact keyring
├── objects/       # Content-addressable encrypted object store
├── schemas/       # Type_Safe data models
├── safe_types/    # Domain-specific validated types (zero raw primitives)
└── secrets/       # Local encrypted secrets store
```

Built on [osbot-utils](https://pypi.org/project/osbot-utils/) Type_Safe framework — all data fields use validated domain types, never raw primitives.

## Development

```bash
# Install in dev mode
pip install -e ".[dev]"

# Run tests
pytest tests/unit/

# Run with coverage
pytest --cov=sgit_ai --cov-report=term-missing
```

## License

Apache-2.0
