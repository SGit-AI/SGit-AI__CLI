---
name: sg-send-cli
description: >
  Use this skill whenever you need to interact with a zero-knowledge encrypted vault
  via sg-send-cli. Triggers include: creating a vault, committing changes, pushing files
  to a vault, pulling changes from a vault, checking vault status, or any mention of
  sg-send-cli, SG/Send, or encrypted vault sync. This skill enables persistent state
  and bidirectional communication between Claude sessions and human collaborators
  through a shared encrypted object store with git-like branching and merge.
---

# SKILL: sg-send-cli — Zero-Knowledge Encrypted Vault Operations

## Overview

`sg-send-cli` is a CLI tool for syncing files with zero-knowledge encrypted vaults on SG/Send.
It works like git for encrypted files — init, commit, push, pull, status, branch, merge.

This skill enables a Claude session to read from and write to shared vaults,
allowing persistent state and communication across isolated sessions.

---

## Setup

### Install
```bash
pip3 install sg-send-cli --break-system-packages
```

### Access Token
Write operations (init, push, pull) require a token. Pass it with `--token`:
```bash
sg-send-cli --token <token> <command>
```

The token is saved to `.sg_vault/token` after first use, so subsequent commands
in the same vault don't need `--token` again.

If you don't have a token, ask the user.

### Keys never leave the vault (rule for agents)

A vault key, read key, write key, signing key or token must never be printed, echoed,
logged or pasted into a message, a commit, a file in the working copy, or a tool call
other than the sgit command that needs it. An agent's transcript and its tool logs are
read by other tools and people (the insider-threat model's I4: secrets through reasoning
logs). So:

- never `cat .sg_vault/local/*`, never `sgit vault info` or `sgit vault show-key` unless
  the user asked for the key on screen; prefer `sgit vault show` (no key) and `sgit status`;
- pass a key on the command line only once (`init`, `clone`); afterwards the vault holds it;
  the clone family also reads the key from stdin, which keeps it out of shell history;
- never copy a key into a note, a brief, a vault file or a commit message; if a key must be
  handed over, hand over the vault path and let the human read it there;
- never run `sgit pki delete` or `sgit vault uninit` with a value you did not get from
  `sgit pki list` or from the user.

---

## Core Commands

### Create a new vault
```bash
sg-send-cli init <directory> --token <token>
```
- Creates a new empty vault both locally and on the server
- Outputs a vault key — **save it**, it's the only way to access this vault later
- Optionally pass `--vault-key <key>` to use a specific key instead of generating one

### Commit local changes
```bash
sg-send-cli commit [directory]
sg-send-cli commit -m "description of changes" [directory]
```
- Stages all file changes (added, modified, deleted) and creates a commit
- Like `git commit -a` — you must commit before pushing
- Auto-generates a commit message if `-m` is omitted

### Check status
```bash
sg-send-cli status [directory]
```
- Shows uncommitted changes: `+` added, `~` modified, `-` deleted

### Push to remote
```bash
sg-send-cli push [directory]
```
- Pushes committed changes to the remote vault
- Automatically pulls first to avoid conflicts
- Only uploads objects that changed (delta push)

### Pull remote changes
```bash
sg-send-cli pull [directory]
```
- Pulls remote changes and merges into your clone branch
- If conflicts occur, fix them and run `sg-send-cli commit`, or abort with `sg-send-cli merge-abort`

### List branches
```bash
sg-send-cli branches [directory]
```

### Abort a merge
```bash
sg-send-cli merge-abort [directory]
```

### View commit history
```bash
sg-send-cli log [directory]
sg-send-cli log --oneline [directory]
sg-send-cli log --graph [directory]
```

---

## Typical Workflow for a New Claude Session

1. **Install the CLI**
   ```bash
   pip3 install sg-send-cli --break-system-packages
   ```

2. **Create or receive a vault**
   ```bash
   # Create new:
   sg-send-cli init my-vault --token <token>

   # Or if given an existing vault key, init with it:
   sg-send-cli init my-vault --token <token> --vault-key <vault-key>
   ```

3. **Read existing content** — browse files normally with `cat`, `ls`, etc.

4. **Make changes** — create/edit/delete files in the vault directory

5. **Commit and push**
   ```bash
   cd <vault-dir>
   sg-send-cli commit -m "session update"
   sg-send-cli push
   ```

6. **Pull updates from others**
   ```bash
   cd <vault-dir>
   sg-send-cli pull
   ```

---

## Vault Key Format

```
xk8mp2vn9qrstu4567890abc:a1b2c3d4
└──────── passphrase ────────┘ └ vault_id ┘
```

- The passphrase derives encryption keys — the server never sees it
- The vault ID identifies the vault on the server
- **Save the vault key** — without it, the vault contents are unrecoverable

---

## Inspection Commands (Debugging)

```bash
sg-send-cli inspect [directory]              # Vault state overview
sg-send-cli inspect-tree [directory]         # Show file tree with blob IDs
sg-send-cli inspect-object <object-id>       # Show object metadata
sg-send-cli cat-object <object-id>           # Decrypt and display object
sg-send-cli inspect-stats [directory]        # Object store statistics
sg-send-cli derive-keys <vault-key>          # Show derived keys
```

---

## Remote Management

```bash
sg-send-cli remote add <name> <url> <vault-id>   # Add a remote
sg-send-cli remote remove <name>                  # Remove a remote
sg-send-cli remote list                           # List remotes
```

---

## Credential Store

Store vault keys locally so you don't have to remember them:

```bash
sg-send-cli vault add <alias>                # Store a vault key under a name
sg-send-cli vault list                       # List stored aliases
sg-send-cli vault show <alias>               # Show stored vault key
sg-send-cli vault remove <alias>             # Remove stored vault key
```

Protected by a passphrase (or `SG_SEND_PASSPHRASE` env var). Auto-locks after 30 minutes of inactivity.

---

## PKI (Sign & Encrypt Files)

```bash
sg-send-cli pki keygen --label "My Keys"     # Generate RSA-4096 + ECDSA P-256 key pair
sg-send-cli pki list                         # List local keys
sg-send-cli pki export <fingerprint>         # Export public key (JSON)
sg-send-cli pki import <file>                # Import contact's public key
sg-send-cli pki contacts                     # List imported contacts
sg-send-cli pki sign <file> --fingerprint <fp>                    # Sign a file
sg-send-cli pki verify <file> <signature-file>                    # Verify signature
sg-send-cli pki encrypt <file> --recipient <fp>                   # Encrypt for recipient
sg-send-cli pki decrypt <file> --fingerprint <fp>                 # Decrypt with local key
```

---

## Notes

- **Zero-knowledge**: the server never sees plaintext. All encryption/decryption is local (AES-256-GCM).
- **Commit before push**: like git, you must `commit` local changes before `push` will upload them.
- **Token is saved**: after the first `--token` use, the token is persisted in `.sg_vault/token`.
- **Delta push**: only changed objects are uploaded — efficient for large vaults.
- **Branch model**: each clone gets its own branch with an EC P-256 key pair for commit signing.
- **Cross-session communication**: commit + push at the end of a session; the next session pulls and continues.
