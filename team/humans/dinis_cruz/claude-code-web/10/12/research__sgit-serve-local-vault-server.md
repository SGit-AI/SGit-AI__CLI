# `sgit serve`: running a vault locally — research and plan

**Date:** 2026-10-12 · **Status:** research and design, no code yet · **Asked:** "how can I run a
vault locally … just clone a vault and run it from there … `sgit serve` … SSL if needed … how
much plumbing do we need to add to sgit".

## 1. Short answer

It is very doable, mostly with what we already have.
- **Server side:** a vault server is a small API (§3): read, write, delete, batch with
  compare-and-swap, list, health and destroy, all over a key-value store. sgit already has a
  stdlib HTTP server (`sgit vault serve`, read-only) and an in-memory model of the API. A
  native, stdlib-only `sgit serve` that adds the write side and a disk store is about
  **600–900 lines plus tests**. It needs **no new dependencies** and runs on Python 3.11.
- **The web UI:** the SG/Send team already builds a static copy of it that talks to its own
  origin. The docker image `diniscruz/sg-send-vault` uses that build (`VAULT_DEFAULT_ENDPOINT=""`
  → relative `/api/...` paths). sgit can ship or fetch that build and serve it beside the API.
- **TLS:** **not needed for the default setup.** Serve the UI and the API from one origin,
  `http://localhost:<port>`. Browsers treat `localhost` as a secure context, so Web Crypto
  works, and nothing is cross-origin. TLS (or the CORS mode, §5) matters for two cases only:
  using the **hosted** UI (vault.sgraph.ai) against a local API from Safari, and reaching the
  server from another machine. For those we add `--tls` (§6).

**Estimate:**
- an MVP (local API, the UI, serving a clone) in about **3 days**;
- the full version (CORS mode for the hosted UI, TLS, docs, threat model) in about **5 days**.

## 2. What exists today

| Piece | Where | What it gives us |
|---|---|---|
| `sgit vault serve` | `sgit_ai/cli/CLI__Serve.py`, `sgit_ai/core/serve/Vault__Static_Server.py` | A stdlib `ThreadingHTTPServer`, read-only (GET/HEAD; anything else is 405), bound to 127.0.0.1, with a Host-header check against DNS rebinding and a path guard. It serves the published static loader and maps `/api/vault/read/<id>/bare/*` onto `.sg_vault/bare/`. |
| `Vault__API__In_Memory` | `sgit_ai/network/api/` | The API semantics the CLI relies on (batch, `write-if-match` conflicts, list, tombstones), in process. It does not check write keys. |
| Real SG/Send server | `sgraph-ai-app-send` (PyPI, **Python ≥ 3.12**; fastapi, uvicorn, osbot-aws, mcp …) | Our integration suite already runs it in-process with in-memory storage. It also has **disk** storage. |
| SG/Send container | `diniscruz/sg-send-vault` (~250 MB; source `sgraph_ai_app_send__docker/`) | **The whole local stack already exists as an image:** the vault UI at `/` plus the API on one port. Disk storage goes to `/data` (layout in §3.4). It has an optional access token, can terminate TLS itself if given a cert/key, and its README covers the secure-context and Web Crypto issue. |
| Vault UI | `sgraph_ai_app_send__ui__vault` (inside the server package; v0.2.3 is 2.6 MB unbuilt) | The endpoint comes from `window.SG_ENDPOINT`, then `sessionStorage['sg-vault-endpoint']` (there is an **endpoint field** on the entry form), then `https://dev.send.sgraph.ai`. A `/#<key>` hash opens a vault directly. It calls only vault endpoints, plus the transfer and presigned endpoints for other features. |

So "run a vault locally" works **today** with docker:

```bash
docker run --rm -p 8080:8080 -v "$PWD/_sg-send_data:/data" diniscruz/sg-send-vault:latest
sgit clone <vault-key> my-vault --base-url http://localhost:8080   # or push an existing clone there
```

What is missing:
- the one-command experience;
- no docker requirement;
- starting from a clone you already have.

## 3. The API a local server must speak

This is from the code of `sgraph-ai-app-send` 0.33.0, the user lambda:
`lambda__user/fast_api/routes/Routes__Vault__Pointer.py` and
`service/Service__Vault__Pointer.py`.

### 3.1 Routes

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/vault/read/{vault_id}/{file_id:path}` | public | raw bytes; 404 if missing |
| PUT | `/api/vault/write/{vault_id}/{file_id:path}` | write key | an empty body gives 400; returns `{file_id, vault_id, status:"completed"}` |
| DELETE | `/api/vault/delete/{vault_id}/{file_id:path}` | write key | 403 for a key mismatch **and** for a missing file |
| POST | `/api/vault/batch/{vault_id}` | public if every op is `read`, otherwise write key | 1–100 ops; **always HTTP 200** (§3.3) |
| GET | `/api/vault/list/{vault_id}?prefix=` | public | `{vault_id, prefix, files:[…]}`, sorted |
| GET | `/api/vault/health/{vault_id}` | public | 200 if `manifest.json` exists, otherwise 404 |
| DELETE | `/api/vault/destroy/{vault_id}` | write key | body `{vault_id, purge?}`; writes a tombstone |
| GET | `/api/info/health` | public | `{"status":"ok"}` |

`vault_id` must match `^[a-z0-9]{8,24}$`.

Extras the local server does not need for vaults:
- **Presigned upload/download:** S3 only. Other modes answer 400 "Presigned URLs not
  available", and sgit and the UI already fall back to direct writes.
- `read-base64`, zip, inbox, public-info.
- The `/api/transfers/*` family, which is Send's file transfer and not vaults.

### 3.2 Auth

- **Write key, trusted on first write:**
  - The server stores `sha256(<write-key header string>)` in `manifest.json` on the first
    write or batch. After that, the hashes must match, or the server answers 403.
  - A `deleted.json` tombstone refuses every write.
- **Access token** (`x-sgraph-access-token`):
  - It is checked only when configured; empty means open, which is what local dev uses.
  - The container can gate every route, reads included.

### 3.3 Batch

Ops are `read`, `write` (b64), `write-if-match` (`match` b64, or null for "must not exist")
and `delete`.

- A conflict returns `{op, file_id, status:"conflict", current:b64|null}` and **stops** the
  batch.
- The batch is ordered and best-effort: ops before a conflict stay applied.
- The comparison is on whole bytes.

This is exactly what sgit's CAS code already handles; it is the live server's behaviour.

### 3.4 Disk layout (container and lambda disk mode)

```
<root>/vault/<vault_id[:2]>/<vault_id>/manifest.json          {vault_id, write_key_hash, created_at}
<root>/vault/<vault_id[:2]>/<vault_id>/deleted.json           tombstone
<root>/vault/<vault_id[:2]>/<vault_id>/<file_id>/payload      e.g. bare/data/obj-cas-imm-…/payload
```

If the native server uses **the same layout**, a data folder works with both `sgit serve` and
`docker run -v <folder>:/data diniscruz/sg-send-vault`. That gives an exact-parity fallback
for free.

Note that this is **not** the clone's own layout: `.sg_vault/bare/data/<id>` is a file, not
`<id>/payload`. Section 4 explains why the server keeps its own store anyway.

### 3.5 CORS

- The lambda sends `allow_origins=["*"]` with `allow_credentials=False`, the usual methods,
  and the headers `x-sgraph-access-token` and `x-sgraph-vault-write-key`, among others.
- **No `Access-Control-Allow-Private-Network` handling exists anywhere** (relevant to §5).

## 4. "Clone a vault and run it from there": the model

Recommendation: **the server has its own store, seeded from the clone; the clone talks to it
as a remote.** The server should not read and write the clone's `.sg_vault/bare/` directly.

Why not serve the clone's `bare/` directly:
- A clone's `bare/refs/<named-ref>` is the clone's *accepted* copy of the server ref. Since
  0.21 only a pull that passed verification moves it, and the rewind baselines depend on it.
- A web UI writing into that same file would move the clone's named ref behind its back.
  `status` would say "in sync" while nothing was pulled, the signature policy would be
  bypassed, and the next pull would see a "rewind".
- That is the exact class of bug the last five review rounds closed.

So:

```
my-vault/                      the clone (unchanged behaviour)
my-vault/.sg_vault/serve/      the local server's store, in SG/Send disk layout (§3.4)
                               (inside .sg_vault, so it is never committed; excluded from uninit backups)
```

`sgit serve`, run inside a clone:
1. **Seeds the store** if it is empty:
   - every object in `.sg_vault/bare/data/` is **hard-linked**. Objects are content-addressed
     and immutable, so this costs no space or time; it falls back to copying across
     filesystems;
   - refs, indexes and keys are *copied*, because they are mutable;
   - it writes `manifest.json` with `sha256(write_key)`. The clone holds the vault key, so the
     write key is known, and the CLI and the UI can write.
   - The named ref the server starts from is the one the clone last **accepted**, so the
     local server is "the remote as this clone last verified it".
2. **Starts the server** on `http://localhost:8420`, with both the API and the UI.
3. **Prints:**
   - the UI URL;
   - how to open this vault in it: `--open` launches the browser with the vault key in the
     URL hash, which the UI reads; the hash never reaches the server;
   - the remote line: `sgit remote add local http://localhost:8420`, or a flag that adds it.

Then:
- `sgit pull --remote local` brings edits made in the browser into the clone, with full
  verify-then-accept.
- `sgit push --remote local` shows clone commits in the browser.
- `sgit push` (origin) publishes everything to the real server.

Outside a clone, `sgit serve --data <dir>` is a **general local SG/Send-compatible server**:
- any vault can be created, cloned (`--base-url http://localhost:8420`), pushed or pulled;
- its folder is interchangeable with the docker image's `/data`.

## 5. Browser access: three ways, and what each needs

| Mode | URL the user opens | Cross-origin? | Needs |
|---|---|---|---|
| **A. Same origin (default)** | `http://localhost:8420/` (UI served by sgit) | no | nothing. `localhost` is a secure context, so Web Crypto works in Chrome, Firefox and Safari. |
| **B. Hosted UI → local API** | `https://vault.sgraph.ai`, endpoint field set to `http://localhost:8420` | yes | CORS on the local server (`*` or an allow-list, as production does).<br>Chrome 141/142+: a one-time **Local Network Access** permission prompt per site.<br>Safari: blocks https→`http://localhost` as mixed content (WebKit bug 279249), so it needs `https://localhost` (§6). |
| **C. Another machine / LAN** | `https://<host>:8443` | – | TLS (Web Crypto refuses plain http on non-localhost hosts) **and** an access token |

- **Mode A** is the product: it works offline, does not depend on the hosted UI version, and
  needs no permissions or certs.
- **Mode B** is useful for testing the hosted UI against local data, and it is what "it has
  CORS enabled so you can load it from the other side" refers to.
- **Mode C** is opt-in, with warnings.

For B, the local server should also answer preflights with
`Access-Control-Allow-Private-Network: true`. Older Chrome Private Network Access preflights
need it, and it is harmless otherwise.

## 6. TLS

- **Default: none** (modes A and B in Chrome/Firefox).
- **`sgit serve --tls`:**
  - sgit generates a local CA and a `localhost`/`127.0.0.1` leaf cert with `cryptography`,
    already a dependency, under `~/.sgit/tls/`, and serves https on 8443 through stdlib `ssl`.
  - If `mkcert` is installed it uses mkcert's CA instead, which is already trusted.
  - `--cert/--key` use the user's own pair.
- **Trust:** a browser *page* can click through an untrusted cert, but a cross-origin `fetch`
  (mode B) cannot. So mode B over https needs the CA trusted.
  - `sgit serve trust` prints the exact per-OS command (macOS `security add-trusted-cert`,
    Windows `certutil -addstore`, Linux `update-ca-certificates`, plus `certutil -d sql:…`
    for the Chrome/Firefox NSS store).
  - It runs that command only on explicit confirmation, because changing the trust store is
    a system change.

## 7. The UI: where its files come from

| Option | Wheel size | Network at runtime | Risk |
|---|---|---|---|
| **Vendor a pinned, flattened build into the sgit wheel** (recommended) | +~1 MB zipped | none, works offline | must be refreshed per UI release; covered by a script, a pinned version and a SHA-256 manifest |
| Download on first `serve` into `~/.sgit/ui/<version>/`, hash-pinned | none | once | supply chain (mitigated by the pinned hash); fails offline the first time |
| Use the docker image for the UI | – | docker | not "just sgit" |

- The flattening is what `scripts/build-vault-static.sh` in SG/Send does, with
  `VAULT_DEFAULT_ENDPOINT=""`.
- sgit would add a `scripts/vendor-vault-ui.sh` that takes a pinned UI version and writes
  `sgit_ai/serve/ui/` plus `ui-version.json`.
- `--ui-dir PATH` lets UI developers serve a working tree instead.
- The server injects nothing; with `VAULT_DEFAULT_ENDPOINT=""` the UI uses its own origin.

**Ask of the SG/Send team:** publish the flattened vault UI as a versioned release asset
(zip + SHA-256). Then sgit vendors from it rather than rebuilding from their source tree.

## 8. Implementation plan

### Components

| Component | Layer | Size |
|---|---|---|
| `Vault__Local_Store`: the §3.4 layout; atomic writes (temp + rename); a per-vault lock for batch and CAS; list by prefix; manifest, write-key hash, tombstone | storage | ~200 lines |
| `Vault__Local_Server`: stdlib `ThreadingHTTPServer`; the §3.1 routes with matching status codes and JSON; batch semantics (§3.3); access-token option; Host check (from `Vault__Static_Server`); Origin allow-list on writes in mode A; CORS and PNA preflight; static UI; optional `ssl` wrap | core/serve | ~350 lines |
| `Vault__Serve__Seed`: hard-link objects, copy refs/indexes/keys, write the manifest | core/serve | ~100 lines |
| `Vault__Local_TLS`: CA and leaf generation, mkcert detection, trust instructions | crypto | ~120 lines |
| `CLI__Serve`: `sgit serve [--data DIR] [--port] [--bind] [--open] [--tls] [--cert/--key] [--cors-origin …] [--token] [--no-ui] [--ui-dir] [--add-remote]`; `sgit serve trust`; keep `vault serve` as the static-publish server | cli | ~200 lines |

Command placement (rule 9):
- `serve` is a daily-use verb, so it goes at the **top level**. That is a deliberate edit to
  `TOP_LEVEL_COMMANDS`.
- `sgit vault serve` stays, because it serves a *published* folder; its help points to
  `sgit serve`.

### Tests

- **Unit:** store, routes, status codes, batch CAS, the write-key first-write rule, tombstones,
  the Host check, the Origin check, CORS and PNA preflights, TLS against a generated cert,
  seeding (hard links, mutable files copied).
- **Contract:** one API test module that runs against **both** the native server and the real
  `sgraph-ai-app-send` test server, in the 3.12 integration job. That is how the native server
  stays in step with production.
- **End to end:**
  - `sgit clone/push/pull --base-url http://localhost:<port>` against `sgit serve`;
  - a Playwright smoke test in the preinstalled Chromium: the UI opens a vault served by
    `sgit serve` and lists its files; mode B fetch with CORS.

### Phases

| Phase | Work | Estimate |
|---|---|---|
| 0 | Spike: vendored UI v0.2.3 + the real server on `localhost`, driven by Playwright; confirm modes A and B in Chromium | ½ day |
| 1 | Store + API server + seeding + `sgit serve` (API only); CLI interop; contract tests | 1½–2 days |
| 2 | UI vendoring + serving; `--open` | 1 day |
| 3 | Mode B: CORS allow-list, PNA header, Origin checks | ½ day |
| 4 | TLS: generated CA/leaf, mkcert, `--cert/--key`, `serve trust` | 1 day |
| 5 | Docs, threat model rows, CHANGELOG | ½ day |

**MVP = phases 0–2 (~3 days). Full = ~5 days.**

## 9. Security notes (to become threat-model rows)

- **Binding:** 127.0.0.1 by default. `--bind 0.0.0.0` requires `--token` and warns loudly;
  over plain http it also warns that the token travels in clear.
- **DNS rebinding:** keep the Host-header check (already in `Vault__Static_Server`).
- **Writes from other websites (mode A):**
  - Writes need the write key, which only someone holding the vault key can derive.
  - On top of that, refuse writes whose `Origin` is neither the server's own nor on the
    `--cors-origin` list.
  - Reads expose ciphertext only, which is the same as the public read API in production.
- **The vault key in the `--open` URL hash:** the hash is never sent to the server. The UI
  stores the key in `localStorage`, which is the UI's existing behaviour; the docs should
  say so.
- **The server store lives in `.sg_vault/serve/`:** never committed, excluded from uninit
  backups, so a backup does not double in size.
- **Nothing changes for the clone:** it reaches the local server only as a remote, through
  the same verify-then-accept path as any server.

## 10. Decisions for you

1. **UI files:** vendor into the wheel (recommended), download on first run, or rely on docker?
2. **Store location:** per clone in `.sg_vault/serve/` (recommended for "serve this clone"),
   with `--data DIR` for a shared multi-vault store?
3. **`local` remote:** should `sgit serve` add it automatically, or only print the command?
4. **Default port:** 8420, the same as today's `vault serve`, or 8080 like the container?
5. **Asks of SG/Send:**
   - a versioned UI release asset;
   - `Access-Control-Allow-Private-Network: true` on preflights;
   - optionally a `?endpoint=` URL parameter in the UI, so mode B links can be shared.

## Sources

- Chrome Local Network Access: <https://developer.chrome.com/blog/local-network-access>;
  rollout notes <https://piunikaweb.com/2026/02/09/chrome-local-network-permission-explained/>,
  <https://support.beyondidentity.com/hc/en-us/articles/34457691192215-Managing-the-Chrome-v142Local-Network-Access-Prompt>
- Safari blocking https→`http://localhost`: <https://bugs.webkit.org/show_bug.cgi?id=279249>,
  <https://developer.apple.com/forums/thread/736105>
- The SG/Send code and container README: from the installed `sgraph-ai-app-send` 0.33.0 package.
