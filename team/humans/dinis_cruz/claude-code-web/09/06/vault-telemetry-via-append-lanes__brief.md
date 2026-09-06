# Telemetry from a published vault, via append lanes

**For:** the agent that will build the grants/permissions/mandates game vault
**Question it answers:** how does one vault send messages (events, logs) to another vault, and
how do we get anonymous real-time usage data out of a vault whose read key is public?

---

## 1. The documentation that already exists

All of it is live on sgit.ai. Read in this order:

| Page | What it gives you |
|---|---|
| [`/docs/vault-messaging.html`](https://sgit.ai/docs/vault-messaging.html) | The worked example: two vaults exchanging encrypted messages, end to end, with curl |
| [`/api/append-lanes.html`](https://sgit.ai/api/append-lanes.html) | The six endpoints, the gates, the limits and the status codes |
| [`/vault/sg-bridge.html`](https://sgit.ai/vault/sg-bridge.html) | `sg.append.*` from inside a vault app, and the `sg.on` event push |
| [`/docs/pki.html`](https://sgit.ai/docs/pki.html) | Keypair lifecycle — `sgit pki keygen / export / encrypt / decrypt` |
| [`/vault/sub-vaults.html`](https://sgit.ai/vault/sub-vaults.html) | The *other* cross-vault mechanism — `*.link.json`, for reading across, not writing |

Ground truth in the docs bundle: `01-vault-html-app-authoring/AUTHORING.md`, section
**"Receiving messages (`sg.append.*` + `sg.on`)"** (~line 788).

**On the doctor/patient case study:** what is published is
[`/demos/vaults/health-score/`](https://sgit.ai/demos/vaults/health-score/) (`zc6abngv`) — and it is
**one vault with three audiences**, `patient/`, `doctor/` and `shared/`, split by *who is reading*
rather than by copying. Sharing with the clinician is handing over a derived read key; there is no
second vault and no message passing in it. The two-vault messaging mechanism is real and documented,
but that vault is not its worked example.

---

## 2. The mechanism: an append lane

A write-only channel attached to a vault, addressed by a token. Four capabilities, deliberately split:

| Capability | Holder | Can | Cannot |
|---|---|---|---|
| `append_token` | the sender | **write** | list, fetch, read anything |
| `enum_key` | the vault owner | list, fetch, mark-processed | write, purge |
| `write_key` | the vault owner | configure, purge | — |
| private key | the vault owner | **decrypt** | *never sent to the server* |

The server stores SHA-256 of the first three and compares hashes. It never holds a raw capability
key and never holds a private key at all.

Two properties that decide this whole design:

- **The write response is blind** — exactly `{"ok": true}`. No file ID, no count, no metadata. A
  sender cannot learn what else is in the lane or whether theirs was the first write.
- **No account is needed to send.** `POST /api/vault/append/write/{vault_id}` requires no access
  token; the `append_token` in the body is the entire gate.

---

## 3. The architecture for the game vault

```
   GAME VAULT (published, read key public)        TELEMETRY VAULT (private, yours)
   ─────────────────────────────────────          ───────────────────────────────
   holds: append_token + telemetry vault_id       holds: enum_key, write_key, private key
          + your PUBLIC key

   player clicks something
        │  encrypt(event, your_public_key)
        │  POST /api/vault/append/write/{telemetry_vault_id}
        ├──────────────────────────────────────▶  gate: H(append_token) ∈ append_anchors?
        ◀──────────────────────────────────────   {"ok": true}   ← blind
                                                        │
                                                  you: list (free) → fetch → decrypt locally
```

Setup, once:

```bash
sgit pki keygen --label "Game telemetry"
sgit pki export sha256:<fingerprint> > telemetry-identity.json

curl -X POST https://send.sgraph.ai/api/vault/append/configure/$TELEMETRY_VAULT_ID \
  -H "x-sgraph-vault-write-key: $WRITE_KEY" -H "Content-Type: application/json" \
  -d '{"append_anchors":["<sha256 of the append_token>"],
       "enum_key_hash":"<sha256 of your enum_key>"}'
```

Reading, cheaply — a metadata-only listing reads **zero** payloads:

```bash
curl -X POST https://send.sgraph.ai/api/vault/append/list/$TELEMETRY_VAULT_ID \
  -H "x-sgraph-vault-enum-key: $ENUM_KEY" -d '{"include_content": false}'
```

---

## 4. Why publishing the append_token is acceptable — and where it stops being

Every visitor holds the game vault's read key, so **every visitor can read the `append_token` out of
the vault.** That is not avoidable and it is not the mistake it looks like: an append token grants
*write only*. A visitor who extracts it cannot list the lane, cannot fetch anything, cannot read
another player's events, and — because the write response is blind — cannot even tell whether the
lane has anything in it.

This is the one credential shape that survives being published inside a public vault. A vault key
would not; a read key to a private vault would not. (Cf. the `bite-coil` audit: a read key decrypts
*everything* in a vault, so anything embedded in a published vault is public.)

**What you do not get is authenticity.** Anything the browser holds, the visitor holds:

- Events can be **forged**. Treat every row as an untrusted claim about what happened, never as fact.
- The lane can be **flooded**. The cap is **1000 pending files per token → 507**, at which point your
  real telemetry stops arriving. This is the failure mode to design against, not the confidentiality one.

Mitigations: register **several `append_anchors`** so one flooded lane does not bury the others and
revoking one sender is removing one anchor; drain aggressively (`list` → `fetch` → `mark-processed`,
then `purge` `folder:"processed"`); rotate the token by re-`configure`-ing and shipping a new vault
release; and put a client-side rate limit in the app so honest players do not trip the cap.

---

## 5. Three things to verify BEFORE building on this

Do not assume any of them. In order of how badly they break the design:

1. **Does `sg.append.write` work from a read-only session?** Your entire audience opens the game with
   a *read* key. `AUTHORING.md` says "Read-only sessions fail closed", and the static-hosting doc
   lists `sg.append.*` as rejected with **`EREADONLY`** in read-only contexts. If that applies to the
   hosted viewer, **the bridge path is unavailable to your players.**
   **The fallback is better anyway:** a direct `fetch()` POST to
   `/api/vault/append/write/{vault_id}`. That endpoint is account-less by design, needs no bridge, no
   permission grant, and no writable session. `AUTHORING.md` is explicit that `fetch()` may be used
   for absolute `https://` URLs — those leave the vault and behave like any web request.
2. **Does the vault frame's CSP allow `connect-src` to `send.sgraph.ai`?** If the host's sandbox
   blocks the origin, neither path works and the answer is a host change, not an app change.
3. **Token format.** `^[0-9a-f]{16,128}$` — **hex only**. A prefixed token returns **400**, not 403,
   because it fails input validation before reaching any gate. Do not paste a `sha256:` CLI
   fingerprint in as a token; that is the most likely way to hit it.

Also note the derivation gap: the intended model is `append_token = H(recipient public key)`, but
**no shipped command emits the append token** — the client-side derivation is PROPOSED, not shipped.
Until it lands, treat the token as an opaque 64-hex secret you generate and register yourself.

---

## 6. "Real time", precisely

- **On the receiving side** the kernel pushes `sg.on('append.new-messages', …)` on **tab focus and
  app open** — your dashboard app does not poll. Declare `"host_events": ["append.new-messages",
  "append.error"]` in `app.json`.
- That means "real time *while you are looking at it*", not a live stream. For anything closer, poll
  `list` with `include_content: false`; it is free and paginates with `after_file_id`, and filenames
  are `{epoch_ms}_{24-hex}.enc` so they sort chronologically.

---

## 7. What you can and cannot learn

**Can:** that the vault was opened, which screens were reached, how far a player got, event ordering
and timing, session-scoped journeys via a random per-session id the app mints.

**Cannot:** who. There is no identity in this system and no login. Every player is anonymous by
construction — which is what you asked for, but it also means "who opens the vault" is not answerable,
only "how many opens".

**Two disclosure points**, and I would not skip either:

- The platform's own privacy default is that **opening a vault never phones home** — external embeds
  are click-to-load specifically so that it does not. A telemetry beacon breaks that expectation, so
  the vault should say so **visibly, in the vault**, not in a footnote. It is also the house rule on
  every published vault page: publish the work, then say exactly what it is worth and what it does.
- The **server sees lane activity, size and timing** regardless of encryption, and it sees the
  requesting IP. "The server cannot read the content" is true; "the traffic is invisible" is not.

---

## 8. The prompt to hand the builder agent

> Build a vault app for the grants/permissions/mandates game. It will be published with a **read
> key**, so assume every visitor can read every file in it, including any credential it carries.
>
> Emit anonymous usage events to a separate telemetry vault over an **append lane**. Read
> `https://sgit.ai/docs/vault-messaging.html` and `https://sgit.ai/api/append-lanes.html` first.
>
> Constraints:
> - Events go to `POST /api/vault/append/write/{TELEMETRY_VAULT_ID}` with the `append_token` in the
>   body. **Verify first** whether `sg.append.write` is available in a read-only session; if it
>   returns `EREADONLY`, use a direct `fetch()` to the account-less endpoint instead.
> - Encrypt each payload to the telemetry vault's public key before sending. The public key ships in
>   the game vault; that is fine, public keys are publishable.
> - Never put a vault key, a read key to any other vault, or any other credential in this vault. The
>   append token is the only credential that may appear, and only because it is write-only.
> - Mint a random per-session id in memory. No names, no emails, no fingerprinting, nothing that
>   identifies a person. Anonymous is the design, not a setting.
> - Rate-limit client-side. The lane caps at 1000 pending files per token and returns 507 after that.
> - Fail silently and never block the game on telemetry — if the POST fails, the player must not
>   notice.
> - Put a visible, plain-English notice in the vault saying that anonymous usage events are sent and
>   what they contain. Opening a vault does not normally phone home; this one does, so say so.
> - Treat every received event as an untrusted claim. Anyone holding the read key can forge or flood
>   the lane; the data is directional, not evidential.
>
> Deliverables: the game app, the event schema, the telemetry vault's `configure` call, and a
> dashboard app in the telemetry vault that subscribes to `sg.on('append.new-messages')` and renders
> the funnel.

---

*Sources: sgit.ai `/docs/vault-messaging.html`, `/api/append-lanes.html`, `/vault/sg-bridge.html`,
`/vault/sub-vaults.html`, `/demos/vaults/health-score/`; docs bundle
`01-vault-html-app-authoring/AUTHORING.md` and `02-hosting-and-git/HOSTING-ON-STATIC-STORAGE.md`.
Verified against the shipped CLI: `sgit pki` has keygen/export/encrypt/decrypt/sign/verify; there is
**no** append-lane command in the CLI, so the transport is HTTP or the browser bridge only.*
