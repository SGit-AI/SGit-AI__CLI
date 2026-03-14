# sg-send-cli User Guide

**Version:** v0.5.29
**Date:** 14 March 2026

---

## What is sg-send-cli?

A CLI tool for syncing encrypted vaults with SG/Send. Think of it as "git for encrypted file vaults" — your files are encrypted client-side before they ever leave your machine.

```
pip install sg-send-cli
```

---

## Quick Start

### 1. Create a vault

```bash
sg-send-cli init my-vault --token <your-access-token>
```

This creates a new vault and prints a **vault key** — save it, you'll need it to access the vault from other machines.

```
Initialized empty vault in my-vault/
  Vault ID:  a1b2c3d4
  Vault key: xk8mp2vn9qrstu4567890abc:a1b2c3d4
  Branch:    clone-7f3a

Save your vault key — you need it to clone this vault on another machine.
```

### 2. Add files and commit

```bash
cd my-vault
echo '{"env": "production"}' > config.json
sg-send-cli commit -m "add config"
```

### 3. Push to remote

```bash
sg-send-cli push
```

### 4. Pull updates

```bash
sg-send-cli pull
```

---

## Core Workflow

### `sg-send-cli init <directory>`

Create a new empty vault and register it on the server.

```bash
sg-send-cli init my-project --token <token>
sg-send-cli init my-project --token <token> --vault-key <key>   # use specific key
```

- `--token` is required (needed for server registration)
- `--vault-key` is optional (generated randomly if omitted)

### `sg-send-cli commit [directory]`

Commit local file changes to the clone branch (like `git commit`).

```bash
sg-send-cli commit                         # auto-generated message
sg-send-cli commit -m "update config"      # custom message
sg-send-cli commit ./my-vault              # specific directory
```

Output:
```
[clone-7f3a82b1c4d5] update config
  commit ab1234567890
```

### `sg-send-cli status [directory]`

Show what's changed locally compared to the last committed vault state.

```bash
sg-send-cli status
sg-send-cli status ./my-vault
```

Output uses git-style markers:
```
  + new-file.json         (added)
  ~ modified-file.json    (modified)
  - removed-file.json     (deleted)
```

### `sg-send-cli push [directory]`

Push committed changes to the remote vault.

```bash
sg-send-cli push                         # current directory
sg-send-cli push ./my-vault              # specific directory
sg-send-cli push --token <token>         # explicit token
sg-send-cli push --branch-only           # push clone branch without updating named branch
```

### `sg-send-cli pull [directory]`

Pull remote changes and merge into your clone branch.

```bash
sg-send-cli pull
sg-send-cli pull ./my-vault
```

If there are conflicts:
```
CONFLICT: 2 file(s) have merge conflicts.
  ! config.json
  ! deploy/EC2.json

Fix the conflicts and then run:
  sg-send-cli commit

Or abort the merge with:
  sg-send-cli merge-abort
```

### `sg-send-cli branches [directory]`

List all branches in the vault.

```bash
sg-send-cli branches
```

Output:
```
* clone-7f3a82b1c4d5 (clone) -> ab1234567890
  main (named) -> cd5678901234
```

### `sg-send-cli merge-abort [directory]`

Abort an in-progress merge and restore the vault to its pre-merge state.

```bash
sg-send-cli merge-abort
```

---

## Remote Management

### `sg-send-cli remote add <name> <url> <vault-id>`

Add a remote to the vault configuration.

```bash
sg-send-cli remote add origin https://send.sgraph.ai a1b2c3d4
sg-send-cli remote add origin https://send.sgraph.ai a1b2c3d4 -d ./my-vault
```

### `sg-send-cli remote remove <name>`

Remove a configured remote.

```bash
sg-send-cli remote remove origin
```

### `sg-send-cli remote list [directory]`

List all configured remotes.

```bash
sg-send-cli remote list
sg-send-cli remote list -d ./my-vault
```

Output:
```
  origin	https://send.sgraph.ai (a1b2c3d4)
```

---

## Bare Vaults

A bare vault contains only the encrypted object store — no plaintext files on disk, no VAULT-KEY. This is useful for servers, CI, and anywhere you don't need files extracted.

### Read files from a bare vault (without extracting)

```bash
# These require --vault-key since there's no VAULT-KEY file on disk
sg-send-cli inspect-tree ./my-vault --vault-key <key>
sg-send-cli cat-object <object-id> --vault-key <key> -d ./my-vault
```

### Extract working copy (like `git checkout`)

```bash
sg-send-cli checkout ./my-vault --vault-key <key>
```

### Remove working copy (reverse of checkout)

```bash
sg-send-cli clean ./my-vault
```

After `clean`, the vault is bare again — encrypted objects remain, plaintext files are removed.

---

## Vault Credential Store

Tired of typing vault keys? Store them in an encrypted keyring at `~/.sg-send/vaults.enc`.

### Store a vault key under an alias

```bash
sg-send-cli vault add my-deploy-vault
  Vault key: <paste key>
  Passphrase: ****
  Confirm passphrase: ****
```

Or non-interactively:

```bash
sg-send-cli vault add my-deploy-vault --vault-key <key>
```

### List stored vaults

```bash
sg-send-cli vault list
  my-deploy-vault
  staging-configs
  team-secrets
```

### Show a stored vault key

```bash
sg-send-cli vault show my-deploy-vault
  Passphrase: ****
  xk8mp2vn9qrstu4567890abc:a1b2c3d4
```

### Remove a stored vault

```bash
sg-send-cli vault remove my-deploy-vault
```

### Passphrase sources

The credential store passphrase is resolved in this order:

1. `SG_SEND_PASSPHRASE` environment variable (for automation/CI)
2. Interactive prompt via terminal (for humans)

### Auto-lock

The credential store auto-locks after 30 minutes of inactivity. This is passive — no daemon runs. Each CLI invocation checks the last activity timestamp and requires re-entering the passphrase if expired.

---

## Vault Key Format

A vault key looks like this:

```
xk8mp2vn9qrstu4567890abc:a1b2c3d4
└──────── passphrase ────────┘ └ vault_id ┘
        (24 chars)              (8 chars)
```

- The **passphrase** derives the encryption keys (read key and write key)
- The **vault ID** identifies the vault on the server
- The colon (`:`) separates the two parts
- The server never sees the passphrase — only the vault ID

---

## PKI (Public Key Infrastructure)

sg-send-cli includes PKI commands for key management, signing, and hybrid encryption.

### Generate a key pair

```bash
sg-send-cli pki keygen --label "My Work Keys"
```

Generates both an RSA-4096 encryption key and an ECDSA P-256 signing key.

### List local keys

```bash
sg-send-cli pki list
```

### Export public key bundle

```bash
sg-send-cli pki export <fingerprint>
sg-send-cli pki export <fingerprint> > my-public-key.json
```

### Import a contact's public key

```bash
sg-send-cli pki import colleague-key.json
sg-send-cli pki import -          # read from stdin
```

### List contacts

```bash
sg-send-cli pki contacts
```

### Sign a file

```bash
sg-send-cli pki sign document.pdf --fingerprint <signing-fingerprint>
# Creates document.pdf.sig
```

### Verify a signature

```bash
sg-send-cli pki verify document.pdf document.pdf.sig
```

### Encrypt a file for a recipient

```bash
sg-send-cli pki encrypt secret.json --recipient <their-fingerprint>
sg-send-cli pki encrypt secret.json --recipient <their-fp> --fingerprint <your-fp>  # sign + encrypt
# Creates secret.json.enc
```

### Decrypt a file

```bash
sg-send-cli pki decrypt secret.json.enc --fingerprint <your-fingerprint>
```

---

## Inspection & Debugging

### Vault overview

```bash
sg-send-cli inspect                     # summary of vault state
sg-send-cli inspect-stats               # object store statistics
```

### Commit history

```bash
sg-send-cli log                         # full commit log
sg-send-cli log --oneline               # compact format
sg-send-cli log --graph                 # with graph connectors
```

### Object inspection

```bash
sg-send-cli inspect-object <object-id>   # show object metadata
sg-send-cli inspect-tree                 # show current file tree
sg-send-cli cat-object <object-id>       # decrypt and display object contents
```

### Key derivation (debug)

```bash
sg-send-cli derive-keys <vault-key>
```

Shows the derived read key, write key, and file IDs for debugging.

---

## Global Options

These apply to all commands:

| Option | Description |
|--------|-------------|
| `--version` | Show sg-send-cli version |
| `--base-url <url>` | API base URL (default: `https://send.sgraph.ai`) |
| `--token <token>` | SG/Send access token (saved to `.sg_vault/token` on first use) |

---

## Vault Directory Structure

After init, your directory looks like this:

```
my-vault/
├── .sg_vault/                  # Vault metadata (always encrypted)
│   ├── objects/                # Encrypted blobs (content-addressed)
│   │   └── ab/ab1234567890    # Individual encrypted objects
│   ├── refs/
│   │   └── head               # Current commit ID
│   ├── tree.json              # File manifest (paths & sizes)
│   ├── settings.json          # Vault metadata (id, name)
│   ├── VAULT-KEY              # Vault key (not present in bare vaults)
│   └── token                  # Access token (not present in bare vaults)
├── config.json                # Your files (plaintext, not in bare vaults)
└── deploy/
    └── EC2.json               # Your files (plaintext, not in bare vaults)
```

**Bare vault** = only `.sg_vault/` exists, no plaintext files, no VAULT-KEY.

---

## Security Model

- All files are encrypted client-side with AES-256-GCM before upload
- The server only stores opaque encrypted blobs — it cannot read your files
- Vault keys never leave your machine (unless you share them)
- The credential store (`~/.sg-send/vaults.enc`) is encrypted with your passphrase
- PKI uses RSA-4096 for encryption and ECDSA P-256 for signing
- All crypto is interoperable with the browser (Web Crypto API) byte-for-byte

---

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `SG_SEND_PASSPHRASE` | Auto-supply credential store passphrase (CI/automation) |

---

## Command Reference

| Command | Description |
|---------|-------------|
| `init <dir>` | Create new vault |
| `commit [dir]` | Commit local changes to clone branch |
| `status [dir]` | Show uncommitted changes |
| `pull [dir]` | Pull and merge remote changes |
| `push [dir]` | Push committed changes to remote |
| `branches [dir]` | List vault branches |
| `merge-abort [dir]` | Abort in-progress merge |
| `remote add <name> <url> <id>` | Add a remote |
| `remote remove <name>` | Remove a remote |
| `remote list` | List configured remotes |
| `checkout [dir]` | Extract files from bare vault |
| `clean [dir]` | Remove working copy (make bare) |
| `vault add <alias>` | Store vault key in keyring |
| `vault list` | List stored vault aliases |
| `vault remove <alias>` | Remove stored vault key |
| `vault show <alias>` | Display stored vault key |
| `log` | Show commit history |
| `inspect` | Vault state overview |
| `inspect-tree` | Show file tree |
| `inspect-object <id>` | Show object details |
| `cat-object <id>` | Decrypt and display object |
| `inspect-stats` | Object store statistics |
| `derive-keys <key>` | Show derived keys (debug) |
| `pki keygen` | Generate key pair |
| `pki list` | List local keys |
| `pki export <fp>` | Export public key |
| `pki delete <fp>` | Delete key pair |
| `pki import <file>` | Import contact key |
| `pki contacts` | List contacts |
| `pki sign <file>` | Sign a file |
| `pki verify <file> <sig>` | Verify signature |
| `pki encrypt <file>` | Encrypt for recipient |
| `pki decrypt <file>` | Decrypt with local key |
