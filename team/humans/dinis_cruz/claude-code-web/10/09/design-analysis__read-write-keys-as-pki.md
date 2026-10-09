# Read and write keys as PKI — design analysis

**Date:** 2026-10-09 · **Context:** the 0.21.0 security review (threat model
`team/explorer/appsec/threat-model/v0.21.0__threat-model.md`, TM-R01) · **Status:** analysis,
no code changed.

**Question.** sgit went symmetric because there was no good place to publish public keys
and no good way to move secrets. Both now exist. So: aren't the read key and the write key
really a public key and a private key? And since only the encrypt/decrypt part would change,
how hard would supporting that be?

## Short answer

**Half right, and the half that's right matters a lot.**

- **The write key should be a private key.** Today it's a password the server compares,
  and nobody else can check it (TM-R01). If writing meant *signing with a private key*,
  every reader could verify every head, and a host or a read-key holder could no longer
  forge history.
- **The read key cannot become a public key.** Reading means decrypting, and decrypting
  needs a secret shared by every reader. Public-key encryption works the other way round:
  anyone can encrypt *to* a key, and only the private-key holder can read. So content
  encryption stays symmetric. What the read capability gains is the writer's **public
  verification key**. It isn't secret, but it has to travel with the read key so nobody
  can substitute it.

So the right mapping is:

```
write capability  =  content key  +  writer's PRIVATE signing key
read capability   =  content key  +  writer's PUBLIC verification key
host              =  ciphertext only; can no longer forge, only withhold or replay
```

This is a known, proven shape: Tahoe-LAFS mutable files (write-cap = signing key; read-cap =
symmetric key + hash of the verifying key) and Hypercore/Dat (public key = identity and
verification; secret key = write).

**On "it's just the encrypt/decrypt bit":** the cryptography really is small. Content
encryption, objects, trees and commits don't change at all, and there's no re-encryption
or data migration. Only two mutable things need a signature: the branch **refs** and the
**branch index**. Everything else is content-addressed below them, so signing the roots
authenticates the whole Merkle tree. The real work is around the cryptography (§4). It's
about 1.5–2 weeks for the CLI, and the web UI needs the same change.

## 1. What a writer signature fixes, and what it doesn't

| Threat-model row | Today | With a writer signing key |
|---|---|---|
| **TM-R01** read-key holder + host forge history that verifies | open (by design) | **closed**: a forged ref or index fails verification on every client |
| TM-R03 ref/key ciphertext not bound to its file id | accepted | **closed**: the signature covers vault id + file id + content |
| TM-R27 legacy named private key readable | accepted | moot: that key stops mattering |
| `signatures-required` meaning "some key that decrypts" | weak | meaningful: the signed index lists the trusted clone keys, so a commit signer must be one of them |
| Tags, format gate, features (all in the index) | host/reader can rewrite | covered by the index signature, so stripping the gate is detected |
| SP-14 whole-site substitution on static mirrors | open | **closed** for browsers that get the verification key in the URL fragment |
| SP-2 / rollback for a *fresh* clone | open | **partly**: a signed timestamp lets a clone flag a stale head; the host can still serve an old signed state |
| Withholding (availability) | open | open: signatures can't force the host to serve data |
| Metadata to the host (TM-R08) | by design | unchanged |
| Revoking one writer | needs a new passphrase | still needs one: the signing key is shared by all writers (§3, phase 3 changes that) |

Per-clone commit signatures stay as they are. They answer *which* writer, while the
vault signature answers *a writer at all*.

## 2. The one design detail that must be right

**The signing key must not be derived from the write key.** The write key is sent to the
server as a header on every write, so the server knows it. A signing key derived from it
would be computable by the very party it must protect against. Deriving it from the read
key fails for the same reason (read-only shares hold that).

It has to come from the **passphrase**, along a third path:

```
passphrase ──PBKDF2(600k, salt "sgit-sign:<vault_id>")──► 32-byte seed ──► Ed25519 signing key
                                                                             └► verification key (public)
```

- Every teammate with the vault key derives the same signing key, so there's nothing to
  distribute among writers. The cost is one more PBKDF2 (~190 ms, cached like the others).
- **Ed25519, not ECDSA P-256.** Ed25519 signatures are deterministic, so the browser
  byte-for-byte test vectors that CLAUDE.md requires are possible. ECDSA in Web Crypto is
  randomised, so it can only be verified, never matched. Web Crypto in current
  Chrome/Firefox/Safari imports an Ed25519 key from a 32-byte seed (PKCS#8) natively.
  Deriving a P-256 key from a seed would need a JS library, since Web Crypto can't compute
  the public point. `cryptography` 49 (installed) supports Ed25519 from a seed; checked.

## 3. Phases

**Phase 1: vault writer signature (the TM-R01 fix).** CLI ~1.5–2 weeks.

1. **Derivation** of the signing key and verification key (§2), plus test vectors shared
   with the web team.
2. **Signed refs.** The encrypted ref JSON becomes
   `{commit_id, seq, ts, sig}`, with `sig` = Ed25519 over
   `(vault_id, file_id, commit_id, seq, ts)`. Clients older than this read
   `.get('commit_id')` and ignore the rest (checked). The signature is made in
   `Vault__Ref_Manager` / the push batch and verified wherever a remote ref is parsed:
   status, pull, clone, fetch.
3. **Signed index.** Add a `writer_sig` over the canonical (JCS) index minus the signature.
   `Schema__Branch_Index.from_json` already tolerates the extra field (checked). Verified
   in `Vault__Index_Sync.read_remote`; re-signed on every merge/upload (all writers can).
   Each branch's `public_key_id` gains a key **fingerprint**, so the signed index pins
   the clone keys and the key files can't be swapped.
4. **Downgrade resistance**, the part that's easy to get wrong:
   - Feature `writer-signed` plus `min_client`, so older clients can't write: they would
     re-save the index without the signature.
   - A clone that has seen the feature pins it locally, the way the format gate never
     goes down.
   - A **fresh** clone can't trust a feature flag the host could strip. So signed vaults
     get a new vault-key / share-token version (`sgit_private_vault_v2_…`), and a client
     that sees v2 requires signatures from the first byte.
5. **Read-only shares.** The read share carries the verification key (32 bytes) next to
   the read key. Existing read-only clones have no verification key: trust on first use,
   by pinning it from the first signed index and refusing any change after.
6. **Tests.** `Known_Gaps` TM-R01 and TM-R03 get inverted into `Fixed` tests (forgery and
   ref swapping refused). Add browser vectors and a real-server round trip.

Existing vaults opt in (`sgit vault format --feature writer-signed`, which signs the
current refs and index). No object is re-encrypted.

**Phase 1b: server enforcement (SG/Send team, optional).** The server stores the
verification key at vault creation and accepts ref/index writes only when they are
signed. The bearer write key then stops mattering (a stolen header is useless), and
garbage writes are refused at the door rather than by every client.

**Phase 2: move capabilities with PKI, not passphrases.** CLI ~1 week. The other half of
your question: now that public keys can be published, a vault key or a read capability
can be wrapped to a teammate's published public key. `PKI__Crypto.hybrid_encrypt`
(RSA-OAEP-4096 + AES-GCM, with an optional ECDSA signature) already exists, as do the
`sgit pki` keyring and contacts. For example, `sgit share --to <contact>` would write the
wrapped capability where the recipient can find it. This removes passphrases from chat,
argv and shell history (TM-R14), and onboarding never exposes the key to the host.

**Phase 3: per-member writers and owner-signed membership.** ~3–4 weeks, later. The
phase-1 key becomes the vault **owner** key. It signs a member list (each member's own
signing key) inside the index, and a head must be signed by a listed member. Removing a
writer becomes "owner drops them and re-wraps the content key to everyone else", with no
new passphrase. This is the full answer to revocation, and it needs phase 1b to be
enforceable against availability attacks.

## 4. Where the effort actually goes

| Piece | Why it isn't "just the encrypt bit" |
|---|---|
| Key derivation | must avoid the write key and the read key (§2); new interop vectors |
| Formats | refs and index carry a signature; old clients must read them (they do) but must not write them (format gate) |
| Downgrade | a host strips signatures or the feature flag unless fresh clones learn "signed" from the capability itself |
| Read shares | new token format; existing read-only clones need trust on first use |
| Every write path | push, index sync, tags, branch create/switch, move, rekey, history edit all write refs or the index and must sign |
| Web UI | same verification (and signing, if it writes); Ed25519 via Web Crypto |
| Tests | gap proofs become fixed tests; vectors; real server |

## 5. Recommendation

Do **phase 1** for the next release after 0.21.0. It closes the most serious row in the
threat model (TM-R01), makes `signatures-required` mean what people think it means, needs
no data migration, and is opt-in per vault. Do **phase 2** alongside it, since it's cheap
with the PKI code that's already there and fixes how keys get shared. Ask the SG/Send
team about **1b**. Keep **3** on the roadmap.

Decisions needed from you before starting:

1. **Ed25519** (my recommendation, for deterministic vectors) or P-256.
2. **A new vault-key version for signed vaults** (fresh-clone downgrade protection), or
   opt-in by feature flag only (simpler, weaker for fresh clones).
3. **Whether the web UI writes to signed vaults** in the first version, or reads and
   verifies only.
