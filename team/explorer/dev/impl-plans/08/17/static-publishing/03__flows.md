# 03 — Flows

## 1. Publish → serve → read (the baseline, test cell 1)

```mermaid
sequenceDiagram
  actor Pub as Publisher
  participant CLI as sgit
  participant FS as ./site
  participant Srv as sgit vault serve
  participant B as Browser

  Pub->>CLI: sgit publish ./site --visibility public
  CLI->>CLI: confirm consequence (irreversible)
  CLI->>FS: ciphertext objects (byte-identical to the vault)
  CLI->>FS: index.html · cover.json · manifest.json · sgit_public_read_…
  Pub->>Srv: sgit vault serve ./site --open
  Srv-->>B: http://127.0.0.1:8420/
  B->>Srv: GET /index.html
  B->>Srv: GET /sgit_public_read_*        (glob → key found)
  B->>Srv: GET …/bare/refs/<derived from key>
  B->>Srv: GET …/bare/data/…              (tree walk, parallel)
  B-->>Pub: rendered vault — no server did any of the work
```

## 2. Static clone (proven working today)

```mermaid
sequenceDiagram
  actor R as Reader
  participant CLI as sgit clone
  participant T as Vault__API__Static
  participant H as any GET host / folder

  R->>CLI: sgit clone sgit_public_read_<hex>:<vault_id> ./work
  CLI->>T: classify_key → READ_PUBLIC → read-only clone
  T->>H: GET …/bare/refs/<HMAC(read_key)>       (layout sniffed once, then sticky)
  T->>H: GET …/bare/indexes/<HMAC(read_key)>
  T->>H: batch_read → parallel GETs (8)
  T-->>CLI: ciphertext
  CLI->>CLI: decrypt · verify sha256(ciphertext)==id · checkout
  CLI-->>R: working tree
```

Verified end to end against `https://sgit-ai.github.io/SGit-AI__API/` — GitHub Pages, no
server, no auth, read key only.

## 3. Custody without access (test cell 11)

```mermaid
sequenceDiagram
  actor A as Archivist (no key)
  participant CLI as sgit vault mirror
  participant H as published host

  A->>CLI: sgit vault mirror <url> ./mirror
  CLI->>H: GET manifest.json
  H-->>CLI: object list (the ONLY way to learn filenames without a key)
  loop every object
    CLI->>H: GET <file_id>
    CLI->>CLI: verify sha256(ciphertext) == id
  end
  CLI-->>A: complete, verifiable copy — unreadable
  Note over A: holding the objects grants nothing.<br/>Custody requires no trust.
```

Without a manifest **and** without a host listing this flow cannot start: no filename is
derivable without the read key. That is why the manifest is mandatory rather than an
optimisation.

## 4. Fork = clone + rekey + republish (test cell 14, the acceptance test)

```mermaid
sequenceDiagram
  actor U as Forker
  participant Src as published template
  participant CLI as sgit
  participant Dst as your target

  U->>CLI: sgit clone <published key>:<vault_id> ./fork
  CLI->>Src: GETs only
  U->>CLI: sgit vault rekey ./fork
  Note over CLI: re-encrypt under a NEW vault key<br/>vault_id changes · EVERY object id changes
  U->>CLI: sgit publish ./fork-site --visibility public
  CLI->>Dst: a fully independent vault
  Note over Dst,Src: shares ZERO object ids with the template —<br/>the fork is cryptographically unlinkable
```

**Measured facts this flow must document:**

- A rekey changes the vault_id and **100% of object ids** (0 of 8 preserved), so a fork is a
  new deployment, not a delta — do not expect delta-publishing a fork.
- Forks share **no** identifiers with their template, so derivation is undetectable. The
  corollary is a real loss: **template-diffing by identifier is impossible**, and a fork
  that wants to show its delta must diff plaintext, which needs both read keys.

## 5. Transport resolution (what happens on every command)

```mermaid
flowchart TD
  S([command with --base-url or a remote]) --> Shape{"http(s):// ?"}
  Shape -->|no| Local["local transport<br/>open() · unambiguous"]
  Shape -->|yes| Batch{"POST /api/vault/batch works?"}
  Batch -->|yes| Api["api transport<br/>batch · writes · auth"]
  Batch -->|"404 / 405 / 501 / CORS"| Static["static transport<br/>GET fan-out · READ ONLY"]
  Local --> Sniff
  Static --> Sniff{"first read: which layout?"}
  Sniff -->|"api/vault/read/{vid}/{fid}"| Sticky[remember]
  Sniff -->|"{fid}"| Sticky
  Sticky --> Report["report it: 'transport: static-http (GET fan-out, read-only)'"]
  Api --> Report
```

Auto-detected so it works transparently against anything; **reported** so a deployment
mistake is visible rather than silent. `--transport auto|api|static|local` forces it.
