# Native PKI vault mode — architecture map

**Date:** 2026-10-09 · **Status:** design for review, no code · **Follows:**
`design-analysis__read-write-keys-as-pki.md` (same folder), which covered adding a writer
signature to today's symmetric vaults. This document maps a second **vault mode** built on
key pairs from the start. Companion: `design__sealed-files-layer.md` (encryption on top of
either mode).

## 1. Your question, checked

> A vault where one key lets you read and a different key lets you write, and neither
> key can be computed from the other. Can one public/private pair do that, used either
> way round?

**One key pair cannot. Two key pairs can, and they give exactly what you describe.**

A key pair supports two operations, and in each the direction is fixed:

| Operation | Done with | Undone / checked with | What it gives |
|---|---|---|---|
| encrypt → decrypt | **public** key | **private** key | confidentiality *to the private-key holder* |
| sign → verify | **private** key | **public** key | proof that the private-key holder wrote it |

Two facts settle it:
- **The private half always yields the public half** (for Ed25519 / X25519 trivially, and
  for RSA the public key sits inside the private key). Only the reverse is infeasible.
  So whichever key goes to the *less trusted* party must be the public one.
- **"Decrypt with the public key" is not confidentiality.** With RSA you can run the math
  the other way, but that is signing: anyone with the public key can undo it. Keeping a
  "public" key secret to use it as a read key is not sound either. RSA public exponents
  are conventionally 65537, and EC public keys are derived from the private key.

With one pair, writers sign (private) and readers verify (public). That gives *who wrote
it*, but nothing for keeping content secret. Add a second pair for reading and every
property you asked for falls out:

```
 R  = read pair   (X25519, for encryption)    R.priv  decrypts      R.pub  encrypts
 W  = write pair  (Ed25519, for signatures)   W.priv  signs heads   W.pub  verifies
```

| Party | Holds | Can | Cannot |
|---|---|---|---|
| **Reader** | `R.priv`, `W.pub` | read everything; check that every head was signed by a writer | write: needs `W.priv`, not derivable from anything it holds |
| **Writer** (normal) | `R.priv`, `W.priv` | read and write | — |
| **Depositor** (write-only) | `R.pub`, `W.priv`* | add new content readers can open | read anything: needs `R.priv`, not derivable from `R.pub` |
| **Host** | ciphertext, `W.pub` | store, serve, refuse unsigned writes | read; forge a head (no `W.priv`); can still withhold or replay old signed states |

\* or a depositor-specific signing key the writers accept for an inbox branch (§5).

So: **two keys, neither derivable from the other, one for reading and one for writing.**
The read capability is `R.priv` (+ the public `W.pub`); the write capability is `W.priv`
(+ `R.priv` for writers who also read). A write-only depositor is the one case today's
design cannot express at all.

**Two vault modes side by side is fine.** The object store, content addressing, trees,
sync, merge, scoped clones, the path guard and the CLI stay shared. The mode decides only
three things: how keys come into being, how the data key reaches a reader, and what
authorises a write.

## 2. The architecture

```
                         owner master seed  M  (32 bytes; or PBKDF2(passphrase) for humans)
                                │ HKDF
            ┌───────────────────┴────────────────────┐
     W.priv (Ed25519)                          R.priv (X25519)
     W.pub ──────────► vault id = base32(SHA-256(W.pub))[:26]   (self-certifying, 128 bits)
                                                   R.pub
 write capability  = M                (derives everything)
 read capability   = R.priv + W.pub   (cannot derive W.priv or M)
 deposit capability= R.pub  + a signing key the vault accepts for its inbox

 vault data key  DK (random 32 bytes, generation g)
   bare/keys/dk-<g>  = HPKE-Seal(R.pub, DK)          ← readers unwrap with R.priv
   every object      = AES-256-GCM(DK, …)            ← exactly today's object format
   every ref / index = AES-256-GCM(DK, …) + Ed25519 signature by W.priv
                        over (vault_id, file_id, seq, ts, ciphertext hash)
```

**Why a data key, rather than encrypting every object to `R.pub`.** Public-key encryption
is randomised: the same tree encrypted twice gives different bytes. Today's design
depends on deterministic tree encryption in two places:
- tree ids repeat (dedup);
- a scoped clone rebuilds a spine whose ids match the whole-vault builder byte for byte.

With a symmetric data key wrapped once to `R.pub`, the object layer is **unchanged**:
`DK` simply plays the role today's read key plays. The PKI sits in two places only:
- **distribution:** `R.pub` wraps `DK`, so `DK` never travels as a passphrase;
- **authority:** `W.priv` signs heads, so no write is authorised by a bearer secret.

## 3. What each piece fixes (threat model rows)

| Row | Today | Native PKI mode |
|---|---|---|
| TM-R01 read-key holder + host forge history | by design | **closed**: heads must carry `W.priv`'s signature |
| TM-R03 refs not bound to their id | accepted | **closed**: the signature covers vault id + file id |
| TM-R29 host replays an old index (drops features) | accepted | **closed** for content (signed); freshness still needs `seq` pinning |
| TM-R13 bearer write key | by design | **gone**: the server checks a signature, so nothing replayable crosses the wire |
| TM-R14 keys in argv | H likelihood | reduced: capabilities can be handed over as wrapped envelopes (sealed-files doc §6), never typed |
| TM-R12 no read revocation | by design | **better**: rotate `R` and `DK`, re-wrap to remaining readers; old data stays readable to the removed reader (inherent) |
| Write-only contributors | impossible | **new**: depositor capability (§5) |
| Freshness for a fresh clone (SP-2) | open | partly: signed `seq` + `ts` lets a client flag a stale head; a host can still withhold |

## 4. Mapping to the code

| Area | Stays | Changes |
|---|---|---|
| `Vault__Crypto` | AES-GCM, deterministic metadata encryption, content ids | + `Vault__Crypto__PKI`: HKDF derivation from `M`; Ed25519 sign/verify; HPKE seal/open (X25519, HKDF-SHA256, AES-256-GCM: RFC 9180 base mode) |
| Key strings | `sgit_private_vault_…`, `sgit_public_read_…` | + `sgit_pki_write_…` (M), `sgit_pki_read_…` (R.priv ‖ W.pub), `sgit_pki_deposit_…`; `Enum__Key_Kind` gains them; the prefix *is* the mode, so a fresh clone knows signatures are mandatory (no strippable flag) |
| `Vault__Components` | object store, refs, index, branches | `read_key` ← `DK` (unwrapped); + `verify_key` (`W.pub`); + `signing_key` (`W.priv`, writers only) |
| Refs (`Vault__Ref_Manager`) | encrypted `{commit_id}` | `{commit_id, seq, ts}` + signature; verified on every read path (status, pull, clone, fetch) |
| Index (`Vault__Index_Sync`) | merge rules, tags, gate | signed on every write (all writers hold `W.priv`); verified on read; `seq` monotonic per clone |
| `Vault__API` | endpoints, batch, CAS | writes carry a request signature (method, path, body hash, time) instead of `x-sgraph-vault-write-key`: **server change** |
| Commits | per-clone ECDSA signatures | unchanged (attribution: *which* writer); the vault signature answers *a writer at all* |
| Format gate | format 1/2 | `format: 3` + mode `pki`; `min_client` set at creation |
| Migration | `vault move` rewrites everything already | `sgit vault move --to-pki` makes a PKI vault from a symmetric one |

## 5. Write-only (deposit) capability

A depositor can encrypt (it holds `R.pub`) but cannot read, so it cannot read the current
tree to modify it. Write-only therefore means **append**, not edit:
- each deposit is a commit on a per-depositor **inbox branch** (`inbox/<name>`), whose tree
  holds only what that depositor added;
- its objects use a per-deposit data key `DK_d`, sealed to `R.pub` and stored beside the
  commit;
- a writer merges inbox branches into the main branch, and from then on that content is
  ordinary data.

This fits agents handing work to a human, form-style submissions, and log or report drops.
The vault accepts the depositor's signing key for its inbox branch only: the writers add
it to the signed index.

## 6. Rotation and the owner key

The self-certifying vault id (`H(W.pub)`) means a new `W` is a new vault. That is fine
for "a writer left" today (it is what `vault move` does), but heavy for teams. The clean
fix, and the same design as the threat model's "owner-signed membership":
- **vault id = H(owner root key `O.pub`)**, with `O` kept offline or in a decryption service;
- the index carries an `O`-signed **writer set** (one `W.pub` per member, or one shared);
- removing a writer = `O` re-signs the set without them. Removing a reader = new `R` and
  `DK`, re-sealed to the remaining members. The sealed-files doc's per-member envelopes
  do exactly this.

Start with one shared `W` (simple, matches today's team model) and keep the writer-set
format ready for per-member keys.

## 7. Interop and algorithms

- **Ed25519, X25519, HKDF-SHA256, AES-256-GCM** are all in `cryptography` (installed:
  49.0.0) and in current browsers' Web Crypto.
- **Test vectors.** Byte-for-byte vectors (CLAUDE.md) work for derivation and Ed25519
  (deterministic). HPKE uses a fresh ephemeral key, so its vectors fix the ephemeral key,
  the same way RFC 9180's do.
- **Post-quantum:** AES-256 content is fine. The key exchange is the exposure
  (harvest-now-decrypt-later on `bare/keys/dk-*`); HPKE has hybrid X25519 + ML-KEM suites
  to adopt when the browser side has them (TM-R20).

## 8. Effort

| Phase | What | CLI estimate |
|---|---|---|
| 1 | `Vault__Crypto__PKI`, key strings, derivation, vectors shared with the web team | ~1 week |
| 2 | Signed refs and index + verification on every read path (also usable on symmetric vaults; = phase 1 of the earlier analysis) | 1–1.5 weeks |
| 3 | `DK` sealed to `R.pub`; read path via `DK`; `init --pki`, `clone` of a PKI vault | ~0.5 week |
| 4 | Server: store `W.pub`, accept signed writes (SG/Send team) | server side |
| 5 | Deposit capability + inbox branches | ~1 week |
| 6 | Owner root key + signed writer set + rotation | 2–3 weeks |

Phases 1–3 give a working native mode in which a reader cannot write and the host cannot
forge. The web UI needs the same verification and unwrap code to open PKI vaults.

## 9. Decisions for you

1. **Vault id:** self-certifying `H(W.pub)` now, or go straight to `H(O.pub)` with a writer set?
   My view: start with `W.pub`, and design the index field so `O` can be added later.
2. **Capability strings:** random 32-byte seeds only (agents and machines), or also a
   passphrase form for humans (PBKDF2 → `M`, as today)?
3. **Deposit / inbox:** in the first release or later?
4. **Server signed writes (phase 4):** ask the SG/Send team now? Until then the server
   keeps the bearer check, but clients reject anything unsigned, so forgery is closed
   either way.
