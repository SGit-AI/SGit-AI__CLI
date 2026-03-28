# 06 — CLI Reference

**Author:** Developer
**Audience:** Users, Developers

## Installation

```bash
pip install sgit-ai            # from PyPI (target name)
# or
pip install sg-send-cli        # current PyPI name
# or
pip install -e ".[dev]"        # from source
```

## Command Overview

```
sgit <command> [options]

Core Commands:
  init          Create a new encrypted vault
  clone         Clone a vault from the remote server
  commit        Commit local changes to the clone branch
  status        Show uncommitted changes
  pull          Fetch + merge remote changes
  push          Upload local commits to server
  branches      List all branches
  merge-abort   Abort an in-progress merge

Remote Management:
  remote add    Add a named remote
  remote remove Remove a remote
  remote list   List configured remotes

Credential Store:
  vault add     Store a vault key under an alias
  vault list    List stored vault aliases
  vault remove  Remove a stored vault key
  vault show    Show vault key for an alias

PKI Commands:
  pki keygen    Generate encryption + signing key pair
  pki list      List local key pairs
  pki export    Export public key bundle
  pki import    Import contact public key
  pki contacts  List imported contacts
  pki sign      Sign a file (detached signature)
  pki verify    Verify a detached signature
  pki encrypt   Encrypt a file for a recipient
  pki decrypt   Decrypt a file

Inspection (dev tools):
  inspect       Show vault state overview
  inspect-tree  Show current tree entries
  inspect-object Show object details
  inspect-stats Show object store statistics
  log           Show commit history
  cat-object    Decrypt and display object contents
  derive-keys   Show derived keys for a vault key
  checkout      Extract working copy from bare vault
  clean         Remove working copy, keep bare vault
  fsck          Verify vault integrity + repair

Utility:
  version       Show CLI version
  update        Update CLI to latest version
  debug on/off/status  Toggle debug mode
```

## Global Options

| Option       | Description                                  |
|--------------|----------------------------------------------|
| `--version`  | Show CLI version                             |
| `--base-url` | API base URL (default: https://dev.send.sgraph.ai) |
| `--token`    | SG/Send access token                         |
| `--debug`    | Enable debug mode (show network traffic)     |

## Detailed Command Reference

### `sgit init <directory>`

Create a new empty encrypted vault.

```bash
sgit init my-vault
sgit init my-vault --vault-key "my-passphrase:my-vault-id"
```

| Argument     | Required | Description                              |
|--------------|----------|------------------------------------------|
| `directory`  | Yes      | Directory to create (must be empty)      |
| `--vault-key`| No       | Custom vault key (auto-generated if omitted) |

**Output:** Vault key, vault ID, branch ID. **Save your vault key!**

### `sgit clone <vault_key> [directory]`

Clone a vault from the remote server.

```bash
sgit clone "my-passphrase:abc12345"              # clones into abc12345/
sgit clone "my-passphrase:abc12345" my-vault      # clones into my-vault/
sgit clone "my-passphrase:abc12345" --token xxx   # with access token
```

| Argument    | Required | Description                                |
|-------------|----------|--------------------------------------------|
| `vault_key` | Yes      | Vault key in `{passphrase}:{vault_id}` format |
| `directory` | No       | Target directory (default: vault_id)       |

### `sgit commit [message]`

Commit working directory changes to the clone branch.

```bash
sgit commit                        # auto-generated message
sgit commit "add readme"           # custom message
sgit commit -d /path/to/vault      # specify vault directory
```

| Argument    | Required | Description                        |
|-------------|----------|------------------------------------|
| `message`   | No       | Commit message (auto if omitted)   |
| `-d, --directory` | No | Vault directory (default: .)       |

### `sgit status [directory]`

Show uncommitted changes in the working directory.

```bash
sgit status
sgit status /path/to/vault
```

Output format:
```
  + new-file.txt        # added
  ~ modified-file.txt   # modified
  - deleted-file.txt    # deleted
```

### `sgit pull [directory]`

Fetch remote changes and merge into local clone branch.

```bash
sgit pull
sgit pull /path/to/vault
```

Possible outcomes:
- `Already up to date.` — nothing to do
- `Merged: X added, Y modified, Z deleted` — clean merge
- `CONFLICT: N file(s) have merge conflicts.` — manual resolution needed

### `sgit push [directory]`

Push local commits to the remote server.

```bash
sgit push
sgit push /path/to/vault
sgit push --branch-only           # push clone branch only (WIP sharing)
```

| Argument       | Required | Description                          |
|----------------|----------|--------------------------------------|
| `directory`    | No       | Vault directory (default: .)         |
| `--branch-only`| No       | Push clone branch without updating named branch |

On first push, the CLI prompts for remote URL and access token.

### `sgit log [directory]`

Show commit history.

```bash
sgit log
sgit log --oneline                 # compact format
sgit log --graph                   # show merge graph
sgit log --oneline --graph         # combined
```

### `sgit fsck [directory]`

Verify vault integrity. With `--repair`, downloads missing objects from remote.

```bash
sgit fsck
sgit fsck --repair
```

### `sgit pki keygen`

Generate an encryption + signing key pair.

```bash
sgit pki keygen
sgit pki keygen --label "work laptop"
```

### `sgit pki encrypt <file> --recipient <fingerprint>`

Encrypt a file for a recipient.

```bash
sgit pki encrypt secret.txt --recipient abc123...
sgit pki encrypt secret.txt --recipient abc123... --fingerprint def456...  # sign too
```

### `sgit pki sign <file> --fingerprint <fingerprint>`

Create a detached signature.

```bash
sgit pki sign document.pdf --fingerprint abc123...
# creates document.pdf.sig
```

## Environment Variables

| Variable              | Description                          |
|-----------------------|--------------------------------------|
| `SG_SEND_TOKEN`       | Default access token                 |
| `SG_SEND_BASE_URL`    | Default API base URL                 |

## Debug Mode

Debug mode logs all network traffic with timing:

```bash
sgit --debug push                  # one-time debug
sgit debug on                      # persist debug mode for this vault
sgit debug off                     # disable
sgit debug status                  # check current state
```
