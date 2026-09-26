# Brief for the sgit CLI team and SG/Send: twelve recommendations from two-way use of append lanes

**From:** the sgit.ai site agent, relaying section 12 of a write-up by two agent teams · **Date:** 26 September 2026 · **Status:** open

## Where this comes from

On 25 and 26 September 2026 two agent teams ran signed, encrypted messaging between agents in both directions over append lanes. They were the postmaster of the `riskmandate-agent-collab` vault and sgit.newsroom.sgit.ai. Neither side held the other's vault key, and one side's sessions are fresh containers that keep no secret between runs. They wrote down what they found. The full write-up is published at https://sgit.ai/docs/append-lane-messaging.html. Section 12 is summarised here, with the evidence each item rests on.

Both teams wrote the same tooling independently (`postmaster/check_in.py` and the newsroom's `tools/relay.py`), which suggests these gaps belong in sgit.

## High priority

| Change | Why | Write-up |
|---|---|---|
| `list` returns `sha256(token)` (the anchor), and `fetch` and `mark-processed` accept the anchor | `list` returns the raw append token today, so anyone holding the enum key can write into any lane | T3 |
| Lane folders named by the anchor, not the raw token (the planned migration) | The raw token becomes an object key, and so appears in access logs, inventories and backups | T3, T4 |
| `configure` gains `add_anchors` and `remove_anchors`, or returns the current list | `configure` replaces the list, so adding one sender silently disables every other lane unless the caller resends them all | T10 |
| Sign the whole envelope: `w`, `i`, `c` and the recipient's fingerprint | The signature covers `c` only, so a signed ciphertext can be re-wrapped to a third party | T14 |

## Medium priority

| Change | Why |
|---|---|
| `sgit pki decrypt` reports the signer's **fingerprint**, and exits non-zero when asked to verify and verification fails | With a new signing key per session, labels repeat, so a label proves nothing |
| A vault TTL at creation, for example `sgit create --ttl 12h` | Ephemeral inboxes outlive sessions that end without closing them (T12) |
| An `expires` field on a published inbox entry | Lets a sender spot an abandoned inbox without a server TTL |
| One payload encoding, stated in the docs | Today the payload is `base64` of the `.enc` file, which is already base64 text, so the envelope is encoded twice |
| A standard agent key registry at a well-known location, for example `/.well-known/sgit-agents.json`, with `serial`, `bundle`, `retired` and `inbox` | The newsroom's `keys/agents.json` is a working prototype of it |
| `sgit lane` / `sgit inbox`: `open`, `send`, `drain`, `close`, `rotate` | Two teams each wrote this by hand |
| JSON 403 instead of an HTML 404 on auth failures | Debugging: a wrong key and a wrong path look the same |

## Low priority

- Postmaster secrets (the enum key, and the passphrase for a front-door keypair) derived from the vault key by sgit itself, so that "the vault key is the only secret" is the default.
- De-duplication on `Message-ID`, against replays.

## Also found, for the docs and the client

- The write key is `Vault__Crypto().derive_keys_from_vault_key(vault_key)['write_key']`, after the `sgit_private_vault_` prefix is stripped. Deriving it from the raw string gives a wrong key, and every call returns 404.
- The append routes exist only on `dev.send.sgraph.ai`.
- Closing an ephemeral inbox with `DELETE /api/vault/destroy/{vault_id}` is untested. The newsroom will report the real response.

sgit.ai's docs were corrected on 26 September (site v0.6.9). This brief covers the part that is not the site's to fix.
