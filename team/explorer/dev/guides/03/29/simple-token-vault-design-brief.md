# Simple Token Vault — Design Brief
## Date: 2026-03-29

> **Status:** Design approved, pending implementation
>
> This brief covers the full design for human-readable "Simple Token" vaults,
> the two-token (edit / share) model, `sgit clone vault://token` resolution,
> `sgit share`, and `sgit init [token]`. It is the authoritative reference for
> the implementation sprint that follows.

---

## 1. The Hallucination That Got It Right

A slide deck for SG/Send hallucinated this:

```
> pip install sgit-ai
> sgit clone vault://oral-equal-1234
> sgit status
> sgit push origin main
```

The slide was wrong about the implementation — but right about the UX.
`sgit` already exists as an entry point. `oral-equal-1234` is already a valid
Simple_Token in the codebase. The only missing piece is the wiring between them.

This brief specifies that wiring.

---

## 2. Core Concepts

### 2.1 Simple_Token

A human-readable string of the form `{word}-{word}-{4-digit-number}`:

```
oral-equal-1234
dawn-haven-1234
amber-fox-1234
```

From the token string alone, two things are deterministically derived — no
server required:

```
Simple_Token("oral-equal-1234")
  ├── transfer_id  = SHA256("oral-equal-1234")[:12]    # 12-char hex
  └── aes_key      = PBKDF2-HMAC-SHA256(token, salt, 600k iterations, 32 bytes)
```

The `aes_key` is then used as the root secret for everything else.

### 2.2 The Two-Token Model

Every Simple Token vault has **two separate tokens** with distinct roles:

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   EDIT TOKEN          oral-equal-1234                          │
│   ──────────────────────────────────────────────────────────    │
│   • Identifies the vault  (vault_id = edit_token)               │
│   • Derives all crypto keys (read, write, EC signing)           │
│   • Shared only with collaborators who should PUSH              │
│   • Lives on: SGit-AI vault server                              │
│                                                                  │
│   SHARE TOKEN         dawn-haven-1234                           │
│   ──────────────────────────────────────────────────────────    │
│   • Read-only published snapshot                                │
│   • Used in SG/Send browser URL                                 │
│   • Safe to share publicly / embed in emails                    │
│   • Lives on: SG/Send transfer API                              │
│                                                                  │
│   RULE: Edit token ≠ Share token  (always different)            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Why separate?** Anyone who sees the browser URL gets the share token.
If edit == share, they could push to the vault. The separation enforces
read-only for viewers and write access only for collaborators.

### 2.3 vault_id = edit_token

The vault's identity IS the edit token string. This means:

- `oral-equal-1234` is both the human name AND the vault_id
- `Safe_Str__Vault_Id` regex already permits it (`[a-zA-Z0-9\-]`, max 64)
- No separate UUID needed
- The edit token is the only credential a collaborator needs to remember

---

## 3. Scenario Diagrams

### Scenario A: SG/Send Folder First

*Someone shared files via the SG/Send browser. You want to edit them locally.*

```
  SG/Send Browser                    Your Terminal
  ───────────────                    ─────────────

  [User uploads files]
  URL: send.sgraph.ai/#dawn-haven-1234
         │
         │  "here's the link"
         │─────────────────────────────►
                                        $ sgit clone dawn-haven-1234
                                                │
                                        ① Check SGit-AI for vault
                                          vault_id = "dawn-haven-1234"
                                          → NOT FOUND
                                                │
                                        ② Check SG/Send for transfer
                                          transfer_id = SHA256(token)[:12]
                                          → FOUND ✓
                                                │
                                        ③ Download + decrypt archive
                                          (AES key from token)
                                                │
                                        ④ Generate NEW edit token
                                          → oral-equal-1234
                                                │
                                        ⑤ Init vault
                                          vault_id = oral-equal-1234
                                          keys derived from edit token
                                                │
                                        ⑥ Extract files, commit
                                                │
                                        Cloned into oral-equal-1234/
                                          Edit token:  oral-equal-1234
                                          Share token: dawn-haven-1234
                                          Files: 4 committed

  Now the user can:
  • Edit files locally
  • sgit push  →  syncs to SGit-AI vault (using oral-equal-1234)
  • sgit share →  refreshes same SG/Send URL (dawn-haven-1234 unchanged)
  • Share "oral-equal-1234" with a collaborator for edit access
```

---

### Scenario B: SGit Vault First → Then Publish

*You created a vault to edit files. Now you want to share a read-only view.*

```
  Your Terminal                       SG/Send Browser
  ─────────────                       ───────────────

  $ sgit init oral-equal-1234
    (or: sgit init  ←  auto-generates token)
            │
    vault_id = oral-equal-1234
    Keys derived from token
    local/config.json:
      { mode: simple_token,
        edit_token: oral-equal-1234 }
            │
  $ sgit commit -m "first draft"
  $ sgit push
    → vault synced to SGit-AI server
            │
  $ sgit share
            │
    ① Generate NEW share token
      → dawn-haven-1234
            │
    ② Package HEAD files
    ③ Encrypt with share token AES key
    ④ Upload to SG/Send
            │
    local/config.json updated:
      { share_token: dawn-haven-1234,
        share_transfer_id: d4e3f2a1b9c8 }
            │
    Published: https://send.sgraph.ai/#dawn-haven-1234
                                                │
                        ◄───────────────────────┘
                        Anyone with the URL sees
                        the decrypted files in browser
                        (READ ONLY — no edit access)


  Later, after more edits:

  $ sgit commit -m "revised slides"
  $ sgit push
  $ sgit share          ← reuses dawn-haven-1234, same URL
    → Browser URL stays the same, content updated ✓
```

---

### Scenario C: Fresh Vault, Auto Token

*Starting a new project from scratch. Let sgit name it.*

```
  $ sgit init
          │
  Generate Simple_Token → amber-fox-1234
          │
  vault_id = amber-fox-1234
  Directory: ./amber-fox-1234/
          │
  Initialized vault 'amber-fox-1234'
    Edit token: amber-fox-1234
    (Run 'sgit share' to get a read-only share URL)

  $ cd amber-fox-1234
  $ sgit commit -m "init"
  $ sgit push

  Share edit access with a colleague:
    "Clone with: sgit clone amber-fox-1234"
```

---

### Scenario D: Collaborative Editing

*Two people editing the same vault.*

```
  Alice                           Bob
  ─────                           ───

  $ sgit init oral-equal-1234
  $ sgit commit -m "draft v1"
  $ sgit push

  "Here's the token: oral-equal-1234"
  ──────────────────────────────────►
                                    $ sgit clone oral-equal-1234
                                      → Check SGit-AI: vault found ✓
                                      → Clone vault (edit access)
                                      → Cloned into oral-equal-1234/

                                    [Bob edits files]
                                    $ sgit commit -m "Bob's changes"
                                    $ sgit push

  $ sgit pull
  → Bob's changes synced ✓

  $ sgit share
  → Published: https://send.sgraph.ai/#dawn-haven-1234

  "Here's the read-only view:"
  ─────────────────────────────────►
  "send.sgraph.ai/#dawn-haven-1234"
                                    [Bob opens in browser — read only]
```

---

### Scenario E: Clone Resolution Flow

*How `sgit clone <token>` decides what to do.*

```
  sgit clone <token>
         │
         ▼
  Is it a Simple_Token?
  (matches word-word-NNNN pattern)
         │
    YES  │                    NO
         │                    └──► existing vault_key flow
         ▼
  ┌──────────────────────────────────────────────────────┐
  │  Derive:                                              │
  │    transfer_id = SHA256(token)[:12]                   │
  │    aes_key     = PBKDF2(token, ...)                   │
  └──────────────────────────────────────────────────────┘
         │
         ▼
  ① Check SGit-AI
     GET /vault/{token}  →  exists?
         │
    YES  │                    NO
         │                    │
         ▼                    ▼
  Clone vault           ② Check SG/Send
  (edit access)            GET /transfers/info/{transfer_id}
  vault_id = token                │
  keys from token            YES  │            NO
                                  │            │
                                  ▼            ▼
                          Download &       Error:
                          import           "No vault or transfer
                          (Scenario A)     found for '{token}'"
                          generate new
                          edit token
```

---

## 4. Key Derivation from Simple_Token

All vault keys are derived deterministically from the edit token. No EC key
generation at init time — the token IS the secret.

```
edit_token = "oral-equal-1234"
        │
        ├── aes_key = PBKDF2-HMAC-SHA256(token, salt='sgraph-send-v1', 600k, 32B)
        │       │
        │       ├── read_key   = HKDF(aes_key, info=b'vault-read-key',   32B)
        │       ├── write_key  = HKDF(aes_key, info=b'vault-write-key',  32B)
        │       └── ec_seed    = HKDF(aes_key, info=b'vault-ec-seed',    32B)
        │               └── EC P-256 private key (deterministic from seed)
        │
        └── transfer_id = SHA256(token)[:12]   (for SGit-AI vault lookup)
```

This means:
- **Losing the token = losing the vault.** No recovery without the token.
- **Sharing the token = sharing full access.** Treat it like a password.
- **Reconstructible anywhere.** No stored key files needed — just the token.

---

## 5. Config Schema

`local/config.json` additions for Simple Token vaults:

```json
{
  "mode": "simple_token",
  "edit_token": "oral-equal-1234",
  "share_token": "dawn-haven-1234",
  "share_transfer_id": "d4e3f2a1b9c8"
}
```

| Field | When present | Notes |
|-------|-------------|-------|
| `mode` | Always (simple_token vaults) | Gates new behaviour in push/pull/share |
| `edit_token` | Always | The vault's cryptographic identity |
| `share_token` | After first `sgit share` | Used to refresh the same SG/Send URL |
| `share_transfer_id` | After first `sgit share` | Redundant (derivable from share_token) but cached |

Vaults without `mode: simple_token` continue to use the existing EC key flow unchanged.

---

## 6. New and Modified Commands

### `sgit init [token]`

```
sgit init                        # auto-generate simple token, use as vault_id
sgit init oral-equal-1234       # explicit simple token
sgit init my-project             # existing flow (not a simple token pattern)
```

When a simple token is used:
- vault_id = token string
- All keys derived from token (no EC key generation at startup)
- Directory named after token if no path given
- Config written with `mode: simple_token`

### `sgit clone <token|vault://token|vault_key>`

```
sgit clone oral-equal-1234           # bare simple token
sgit clone vault://oral-equal-1234   # explicit vault:// prefix — same flow
sgit clone abc123:def456...           # existing vault_key — unchanged flow
```

Resolution: pattern-detect → SGit-AI lookup → SG/Send lookup → error.

### `sgit share`

```
sgit share                       # publish/refresh read-only SG/Send snapshot
sgit share --rotate              # generate new share token (new URL)
sgit share --token dawn-...      # use specific share token
```

Behaviour:
1. Package files at HEAD (same as `Vault__Transfer.share()`)
2. If `share_token` in config → reuse token → update transfer (same URL)
3. If no `share_token` → generate new Simple_Token → first upload
4. Save share_token + share_transfer_id to config
5. Print share URL: `https://send.sgraph.ai/#dawn-haven-1234`

### `sgit push` (modified)

If `mode == simple_token` and `share_token` is set:
- After successful vault push → optionally refresh SG/Send transfer
- Controlled by config flag `auto_share: true/false` (default: false)
- If `auto_share: true`, push always refreshes the share URL silently

---

## 7. Use Case Gallery

### 7.1 "The Newsletter"

```
Editor creates vault:  sgit init
                       → amber-fox-1234/

Writes content, commits, pushes.

Publishes:  sgit share
            → https://send.sgraph.ai/#pearl-wild-5512

Readers open URL in browser — decrypted, readable.
Next issue: edit, push, share → same URL, updated content.
```

### 7.2 "The Collaboration"

```
Alice:  sgit init oral-equal-1234
        sgit push
        → "Clone with: sgit clone oral-equal-1234"

Bob:    sgit clone oral-equal-1234   # full edit access
        [edits]
        sgit push

Alice:  sgit pull   # gets Bob's changes

Both:   sgit share  # Alice or Bob can publish a snapshot
```

### 7.3 "The Airdrop"

```
Someone sends you a link: send.sgraph.ai/#dawn-haven-1234

You:    sgit clone dawn-haven-1234
        → Downloads files from SG/Send
        → Creates new vault with auto-generated edit token
        → Committed into your local vault

        Files are now in your vault — you own the edit access.
        Original sharer has no access to your vault copy.
```

### 7.4 "The Archive"

```
Project ends. You want a permanent read-only record.

$ sgit share --rotate          # new share URL
$ cat local/config.json        # note the share_token
→ https://send.sgraph.ai/#final-token-9999

Post the URL. Content is encrypted, self-contained.
No server account needed to view — just the URL.
```

---

## 8. Implementation Checklist

Items to implement (separate sprint):

- [ ] `Simple_Token` → vault key derivation (`HKDF` paths for read/write/ec_seed)
- [ ] `Vault__Crypto.derive_keys_from_simple_token(token_str)` method
- [ ] `Vault__Sync.init()` — accept simple token, derive keys, set `mode: simple_token` in config
- [ ] `Vault__Sync.clone()` — pattern-detect simple token, two-path resolution
- [ ] `Vault__Transfer.receive(token_str)` — download + decrypt transfer → `{path: bytes}`
- [ ] `Vault__Sync.clone_from_transfer(token_str, directory)` — Scenario A flow
- [ ] `CLI__Vault.cmd_share()` — new command, `sgit share`
- [ ] `CLI__Vault.cmd_init()` — accept optional token arg
- [ ] `CLI__Vault.cmd_clone()` — detect `vault://` prefix + bare simple token
- [ ] Config schema: `mode`, `edit_token`, `share_token`, `share_transfer_id`
- [ ] `sgit share --rotate` flag
- [ ] Tests for all five scenarios (A–E above)

---

## 9. Open Questions (resolved)

| Question | Resolution |
|----------|-----------|
| Same token for edit and share? | **No.** Always different. Share token is publicly distributable; edit token is not. |
| vault_id = edit_token or UUID? | **Edit token.** Human-readable, memorable, reconstructible. |
| What if SG/Send transfer AND vault both exist for same token? | **Vault takes priority** in clone resolution (Step 1 before Step 2). |
| Can you `sgit clone` with a share token? | **Yes** — it hits SG/Send path, creates new vault with fresh edit token. |
| Does `sgit push` auto-refresh SG/Send? | **Optional.** `auto_share: true` in config enables it. Off by default. |
| What if user loses the edit token? | **Vault is inaccessible.** No recovery. Token is the key. Document clearly. |

---

*Brief written 2026-03-29. Implementation sprint to follow.*
