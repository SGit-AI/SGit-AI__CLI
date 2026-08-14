# sgit-ai — git for encrypted vaults

**Clone, commit, branch and merge files that are encrypted before they leave your machine.**

sgit is a git-shaped command-line tool for version-controlling files the storage provider
cannot read. Every object is encrypted client-side with AES-256-GCM and stored under an
opaque, content-addressed id — the server never receives a key, and never sees a filename,
a file's contents, or a commit message.

**📖 Documentation: [sgit.ai](https://sgit.ai)** — quickstart, the git-to-sgit command
mapping, the security model, and the honest page about when *not* to use this.
**🤖 Reading this as an AI agent?** [sgit.ai/llms.txt](https://sgit.ai/llms.txt) is an
annotated map of the whole site; [sgit.ai/llms-full.txt](https://sgit.ai/llms-full.txt) is
every page in one document. Every page is also available as markdown at the same path.

[![PyPI](https://img.shields.io/pypi/v/sgit-ai)](https://pypi.org/project/sgit-ai/)
[![Python](https://img.shields.io/pypi/pyversions/sgit-ai)](https://pypi.org/project/sgit-ai/)
[![License](https://img.shields.io/pypi/l/sgit-ai)](https://github.com/SGit-AI/SGit-AI__CLI/blob/dev/LICENSE)
[![Docs](https://img.shields.io/badge/docs-sgit.ai-0f766e)](https://sgit.ai)

> **Not to be confused with** SGit, the Android Git client, or SGIT, the engineering college.
> This is `sgit-ai` on PyPI — the encrypted-vault CLI, documented at <https://sgit.ai>.

## Why this exists

You have files that need version control and collaboration, and the place they are stored
must not be able to read them. git gives you the workflow and hands the host your content;
encrypted sync tools give you privacy and no history worth the name. sgit is the two
together — see [sgit.ai/why.html](https://sgit.ai/why.html), including a straight comparison
of [where git is still better](https://sgit.ai/why.html) (performance at scale, ecosystem,
bisect/blame/rebase) and where the vault model changes what is possible.

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

---

## Documentation

Full documentation lives at **[sgit.ai](https://sgit.ai)** — which is itself served from an
encrypted vault, deployed by pushing that vault.

| | |
|---|---|
| [Quickstart](https://sgit.ai/docs/quickstart.html) | create, commit, push, clone in five minutes |
| [sgit for git users](https://sgit.ai/docs/sgit-for-git-users.html) | every git command mapped to its sgit equivalent |
| [The two-branch model](https://sgit.ai/docs/two-branch-model.html) | private clone branches, shared named branches |
| [Working with AI agents](https://sgit.ai/docs/agents.html) | `sgit write`, `--json` everywhere, the session pattern |
| [Security model](https://sgit.ai/security.html) | the crypto stack, and what the server can still see |
| [When NOT to use sgit](https://sgit.ai/docs/limitations.html) | the honest page |
| [Use cases](https://sgit.ai/use-cases/) | recipes with an evidence status and an agent brief each |
| [llms.txt](https://sgit.ai/llms.txt) · [llms-full.txt](https://sgit.ai/llms-full.txt) | machine-readable index for agents |
