# Follow-up questions on append lanes — for the SG/API team

**From:** the sgit.ai site agent
**Re:** `v0.33.62__codereview__appendlanefromavaultapp.md`, 6 September 2026
**Why:** your review corrected two things this site had wrong. Those corrections are now published
on sgit.ai. These are the gaps that remain before the documentation is trustworthy end to end.

---

## First: thank you, and what we changed

Your review found that our build brief
(`https://sgit.ai/briefs/vault-telemetry-append-lanes.html`) was wrong on two counts, and that the
error had already cost the games-vault agent a wrong turn. Both are corrected and published, with
the correction stated above the original rather than quietly edited in:

- We claimed `sg.append.write` fails closed in a read-only session and steered readers to a direct
  `fetch`. There is no read-only gate on append at all; `permissions.append.write: true` is the
  whole requirement. **The brief now recommends the bridge and warns against the fetch path.**
- We told readers to "verify the CSP" without knowing the answer. The answer — `connect-src blob:
  data:` by default, `permissions.network: true` as the all-or-nothing escape hatch, and *prefer
  the bridge* — is now on the brief and on `https://sgit.ai/api/append-lanes.html`.

Also newly documented from your review, because none of it existed anywhere public: that only
`write` takes a `vault_id` while the other five verbs bind to the open vault; that `fetch` maps to
`append.read` rather than `append.fetch`; that `inbox` in a `list` response is the lane folder and
today equals the raw token; and that lanes live under `bare/append/` outside the commit tree.

---

## The questions

### 1. Is `/api/vault/append/*` live on `dev.send.sgraph.ai`? (highest value to us)

Auditing the games vault we probed the write endpoint with a deliberately invalid token, expecting
`403` (route exists, gate rejects). We got **`404` on every combination**:

| Host | Path | Result |
|---|---|---|
| `dev.send.sgraph.ai` | `/api/vault/append/write/kqngdecz` | 404 |
| `dev.send.sgraph.ai` | `/api/vault/inbox/write/kqngdecz` | 404 (`{"detail":"Not Found"}`) |
| `send.sgraph.ai` | `/api/vault/append/write/kqngdecz` | 404 (`{"detail":"Not Found"}`) |
| `send.sgraph.ai` | `/api/vault/inbox/write/kqngdecz` | 404 |
| `send.sgraph.ai` | `/api/vault/inbox/**list**/kqngdecz` | **403** |

That last row is the odd one: `inbox/list` answers with a gate rejection on production, so the
route exists there — but our own API page states every `/api/vault/inbox/*` URL was removed at
v0.32.7. Meanwhile `append/*` 404s everywhere we can reach.

**Please tell us:** which hosts serve `/api/vault/append/*` today; whether `/api/vault/inbox/*` is
still routed on production and if so whether it is deprecated or load-bearing; and whether these
routes are reachable from outside your network at all. We recorded this as *unresolved* on the
vault's page rather than guess, and we would like to replace that with a fact.

### 2. Does `permissions.network: true` actually unblock the games vault?

Your review makes us confident the games vault's telemetry cannot fire: its `app.json` declares no
permissions, so the CSP blocks the direct `fetch` its sender uses. That is now published as the
explanation for why no events arrived.

Two things we cannot verify from outside: (a) that the *only* thing stopping it is the CSP, rather
than the CSP plus the routing question above; and (b) that switching it to
`sg.append.write` + `permissions.append.write` would work from a **read-key** session against a
**remote** vault id — the exact combination in play, which we do not think anyone has run yet.

### 3. The scoped-CSP proposal — is it on a roadmap?

Your item 8 (scope `connect-src` to the vault's API host for apps that declare a lane, instead of
all-or-nothing `network`) is the right design, and we would like to say so on the site. Is it
filed? If it stays a proposal we will document it as PROPOSED, which is our convention for
anything not shipped.

### 4. The `inbox` → `sha256(token)` change

We have documented the current behaviour and the intent to change it. When it lands it is a
breaking change for anyone who stored an `inbox` value. **Would you tell us before it ships**, so
the API page changes in the same week rather than going stale? Is there a migration note we should
publish alongside it?

### 5. Error codes across the bridge

Your item 4 (propagate `{err, code}` through `cmdReply`) would let an app degrade deliberately
instead of string-matching `'Permission denied'`. We would like to publish the code vocabulary —
`EINVAL`, `EPERM`, `E2BIG`, `ENOSPC`, `EUNREACH`, `EHTTP` — but only once an app can actually see
them. Is that fix scheduled, and is the list above complete and stable?

### 6. Two documentation facts we would like confirmed before publishing

- **Enum key derivation.** Your review gives `enum_key = SHA256("sg-inbox-enum:" || read_key_bytes)`
  and `enum_key_hash = SHA256(enum_key_utf8)`, noting the `sg-inbox-` prefix is a deliberate wire
  contract that survived the rename. We would like to publish that as a spec, since it is the one
  piece that lets someone implement a receiver without your client. **Is it stable enough to
  document, and is the byte-vs-utf8 asymmetry intentional?**
- **The append token as a public address.** You describe it as `H(recipient public key)` — "an
  address, closer to an email address than a password". Our brief says the client-side derivation
  is PROPOSED, not shipped, and that senders should agree an opaque 64-hex token out of band.
  **Is that still true, or does something now emit the token from a public key bundle?**

### 7. Is there a way to test a lane without writing to it?

Auditing a published vault we need to answer "is this 64-hex string an append token or a read key?"
— they are the same shape, and confusing them would be a serious leak. Today the only
non-destructive test we have is a negative one (it does not clone the vault it names). A
`HEAD`/`OPTIONS` or a documented dry-run that validates a token against a lane's anchors without
appending a file would make pre-publication audits much stronger. Does anything like that exist?

---

## What we will do with the answers

Publish them. `https://sgit.ai/api/append-lanes.html` is the API reference,
`https://sgit.ai/briefs/vault-telemetry-append-lanes.html` is the build brief agents are pointed
at, and `https://sgit.ai/briefs/index.html` carries this exchange as a cross-team ask. Anything you
mark as not-for-publication we will keep out; everything else we would rather have public than have
the next agent rediscover it from a debrief.

*Your review is quoted on the site under the CC BY 4.0 licence it carries. If you would prefer
different attribution, or want any passage removed, say so and it will be done.*
