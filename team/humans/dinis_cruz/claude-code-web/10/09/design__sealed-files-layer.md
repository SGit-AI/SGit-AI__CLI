# Sealed files — a second encryption layer on top of a vault

**Date:** 2026-10-09 · **Status:** design for review, no code · **Companion:**
`design__native-pki-vault-mode.md` (same folder). This layer works on **either** vault
mode, symmetric (today) or native PKI.

> **Revised 2026-10-10 after the sgit.ai agent's review (dev at 0a0707d).** Three corrections,
> applied below:
> 1. **No "compare by re-sealing".** Sealing is randomised (a fresh file key and ephemeral key
>    every time), so re-sealing never reproduces the stored bytes. The tree entry instead
>    carries a **keyed hash of the plaintext**: HMAC-SHA256 under a key derived from the vault
>    read key, stored under the read key. A recipient compares plaintext to that HMAC. A
>    non-recipient compares the sealed bytes. Unlike the unkeyed `content_hash`, the keyed
>    hash does not let a vault reader confirm a guess of the content.
> 2. **Seal-policy changes need an authorised signer.** Otherwise any writer can "unseal by
>    policy": drop a rule or a recipient, and the next commit of that path is sealed to fewer
>    people, or not at all. `.sgit/seal` names its `admins` (public keys). A commit that
>    changes the policy must be signed by one of them, or pull refuses it, as
>    `signatures-required` does. The first policy is pinned by the clone that adds it (trust
>    on first use, like the PKI mode's writer set).
> 3. **The construction is Web-Crypto-native: ECDH P-256 + HKDF-SHA256 + AES-256-GCM.** That
>    is the HPKE base mode with the P-256 KEM (RFC 9180, DHKEM(P-256, HKDF-SHA256)). Browsers
>    open sealed files with no WASM dependency, and CLAUDE.md's byte-for-byte parity rule holds
>    with test vectors. age is kept as an **interop path only**:
>    - `sgit seal export --age` re-seals a file for the stock `age` tool;
>    - hardware and KMS keys are reached through a provider bridge that speaks the
>      `age-plugin` protocol for the unwrap step only (only the file key crosses it).
>    §3 and §9 below are updated accordingly.

> **Revised again 2026-10-10 after the release-gate review (dev at eed8084).** Two more
> corrections:
> 1. **The comparison value moves inside the sealed envelope.** A keyed hash under a key
>    derived from the *vault read key* (correction 1 above) does not stop guessing: every
>    reader holds that key, so a reader who is not a recipient can still compute the HMAC of
>    a guess and compare. The comparison value is now `HMAC-SHA256(K_cmp, plaintext)` with
>    `K_cmp = HKDF(FK, info="sgit seal compare v1")`, where `FK` is the per-file key that only
>    recipients unwrap. It is stored **inside** the envelope, as the first 32 bytes of the
>    encrypted payload, never in the tree entry. A recipient's clone caches it per sealed blob
>    id in a 0600 local file, so `status` does not call the identity provider on every run.
>    The tree entry holds only the hash of the sealed bytes.
> 2. **The chunked AES-GCM payload has defined framing** (§3.1): a per-file payload key, a
>    counter nonce, and the chunk index and a final-chunk flag in the AAD. A reader refuses
>    truncation, reordering, extension and a final flag in the wrong place.

## 1. The idea, in your words and in mechanism

> As the author I can say: "here is my public key, encrypt this data with it; if you need
> to decrypt it, point over there". The files still exist in the vault as before, but
> only someone with the private key can read them. The service holding the private key
> can be local, remote, or anything else.

Mechanically, this is **envelope encryption to recipients' public keys, with decryption
delegated to an identity provider**. git-crypt (GPG), SOPS (KMS/age/PGP) and age
(X25519, ssh keys, hardware plugins) all use this pattern. The vault keeps doing its job,
and selected files get an inner envelope:

```
 plaintext ──► [ inner: sealed to recipients' public keys ]  ──► [ outer: vault encryption ] ──► host
               file key FK (random) encrypts the content          read key / DK, exactly as today
               FK is wrapped once per recipient public key
```

| Who | Sees |
|---|---|
| The host | ciphertext only (outer layer), as today |
| A **vault reader** (read key) | that the file exists: its name, path, history, approximate size, who changed it when. **Not its content.** |
| A **recipient** (holds, or can ask for, a matching private key) | the content |

Two levels, two key systems:
- **Outer layer** (vault key): hides everything from the host.
- **Inner layer** (recipient keys): hides content from everyone who is not a recipient,
  including the host, other vault members, and anyone who later obtains the vault's
  read key.

## 2. What each party can do, precisely

| Party | Create a sealed file | Read it | Edit it | Replace / delete it |
|---|---|---|---|---|
| Recipient (with its provider) | yes | yes | yes | yes |
| Vault writer, not a recipient | **yes**: only the recipients' *public* keys are needed | no | no (editing needs reading first) | **yes, blindly**: it can write new sealed bytes over the file, or delete it |
| Vault reader | no | no | no | no |
| Host | no | no | no | withhold or replay, as today |

One correction to "you could only edit or modify a file if you have that key". **Editing**
needs the key, because you must read before you change. **Replacing** does not. Any
vault writer can put new sealed bytes at the same path, because sealing needs only
public keys. Stopping that is an integrity question, not a confidentiality one, and has
two answers that can be combined:
1. **Signed envelopes:** the sealer signs the inner envelope with its own key. Readers
   (recipients) check that the signer is on the path's allowed-author list (§4).
2. **Path rules enforced on commit/pull:** a commit that changes a sealed path must be
   signed by an allowed author. Otherwise pull refuses it, as `signatures-required` does
   today. With the native PKI mode's writer set, this becomes a hard rule.

## 3. Format

**Recommendation (revised 10-10): an HPKE envelope, DHKEM(P-256, HKDF-SHA256) + AES-256-GCM,
all native to Web Crypto; age v1 as an export and plugin-bridge format only.** The original
reasoning for age follows, kept for the record.
- It is specified, small and audited. Recipient types include X25519, ssh-ed25519 /
  ssh-rsa and scrypt (passphrase), plus a **plugin protocol** (`age-plugin-*`).
- The plugin protocol is precisely "the private key lives elsewhere": YubiKey/PIV, TPM,
  Secure Enclave and cloud KMS plugins already exist.
- **A sealed file can be opened with the stock `age` tool, without sgit**, which is good
  for longevity and audit.
- The pieces it needs (X25519, HKDF-SHA256, ChaCha20-Poly1305, HMAC-SHA256, scrypt) are
  all in `cryptography`. A minimal reader/writer for the X25519 and plugin stanzas is
  a few hundred lines.

**Trade-off to decide.** age's payload cipher is ChaCha20-Poly1305, which **Web Crypto
does not provide**, while CLAUDE.md asks for Web Crypto byte-for-byte parity. The browser
would use `typage` (the reference TypeScript age implementation). The alternative is a
custom HPKE envelope (X25519 + HKDF + AES-256-GCM, all in Web Crypto), at the cost of the
tool ecosystem and the plugins. My view: age. The plugin ecosystem *is* the "decryption
service elsewhere" feature, and the parity rule can name `typage` as the browser
implementation for this layer.

```
sealed file   = "age-encryption.org/v1\n"
                "-> X25519 <ephemeral>\n<wrapped FK>\n"        one stanza per recipient
                "-> piv-p256 <tag> <…>\n<wrapped FK>\n"        a hardware / plugin recipient
                "--- <header MAC>\n"
                <payload: ChaCha20-Poly1305 STREAM, 64 KiB chunks, under a key from FK>
              [ + optional detached Ed25519 signature by the sealer, in a sidecar stanza ]
```

### 3.1 Payload framing (HPKE envelope, revised 10-10)

```
header        = magic "sgit-seal/1" ‖ header_nonce (16 random bytes) ‖ recipient stanzas
                (each: HPKE enc ‖ HPKE-Seal(recipient pub, FK)) ‖ chunk_size (u32, 65536)
H             = SHA-256(header)
PK            = HKDF-SHA256(ikm=FK, salt=header_nonce, info="sgit seal payload v1")   (32 bytes)
plaintext'    = HMAC-SHA256(K_cmp, plaintext) ‖ plaintext        (the comparison value rides inside)
chunk i       = plaintext'[i·65536 : (i+1)·65536]                 (the last may be shorter;
                                                                   an empty file is one empty final chunk)
nonce_i       = u88_be(i) ‖ final_i                               (12 bytes; final_i = 0x01 on the last chunk only)
aad_i         = H ‖ u64_be(i) ‖ final_i
ct_i          = AES-256-GCM(PK, nonce_i, chunk i, aad_i)
sealed file   = header ‖ ct_0 ‖ ct_1 ‖ … ‖ ct_n
```

- **The AAD binds each chunk to this header, its position and whether it ends the file**, so
  chunks cannot be moved between files, reordered, dropped from the end (the new last chunk
  has `final = 0` and fails) or followed by more (anything after a `final = 1` chunk is
  refused). The index is also in the nonce, which keeps nonces unique under `PK` without
  storing them.
- `PK` is fresh per sealing (random `FK` and `header_nonce`), so the counter nonce never repeats
  under one key. At most 2^32 chunks (256 TiB) per file.
- A reader streams: it verifies and releases chunk *i* before reading *i+1*, but treats the
  file as complete only after a valid `final = 1` chunk. The plaintext is written to a temp
  file and renamed only then, so a truncated file never reaches the working copy.
- Test vectors (Python and Web Crypto, byte for byte): empty file, exactly one chunk, one
  chunk plus one byte, three chunks; and the refusals: truncated at a chunk boundary, two
  chunks swapped, a chunk appended after the final one, a final flag on chunk 0 of three, a
  header byte changed.

## 4. Policy: which files, to whom, written by whom

A committed policy file, signed like any commit. It works the way `.gitattributes` works
for git-crypt:

```
# .sgit/seal      (committed; changes to it are themselves a signed, reviewable commit)
recipients:
  dinis   = age1qy…            # published key, fingerprint pinned here
  backup  = age1zz…            # offline recovery key
  ops     = age1yubikey1q…     # hardware-held
seal:
  secrets/**        -> dinis, backup
  finance/*.xlsx    -> dinis, ops, backup
  **/.env           -> dinis, backup
authors:                       # optional: who may change a sealed path (§2)
  secrets/**        -> dinis
```

- **Recipients by public key**, fetched from the published key directory and **pinned by
  fingerprint in the policy**. A later change at the directory cannot silently add
  someone; the policy changes only through a commit.
- `sgit commit` seals any changed file a rule matches. `sgit seal add <path> --to <name>`
  and `sgit seal rekey` edit the policy.

## 5. On disk, in the working copy

| Clone | A sealed file looks like |
|---|---|
| Has a working identity for that file | the **plaintext**, written 0600 (secret writer). `sgit status` compares `HMAC(K_cmp, plaintext)` with the value inside the envelope (cached locally per blob, revised 10-10); never by re-sealing, which is randomised |
| Has no identity, or the provider is unreachable | the **sealed bytes**, unchanged (an `age` file). `status` treats it as unchanged, never deleted or modified: the same "keep the committed entry" rule the symlink ban uses |

Integration points in the current code:
- **Tree entries** carry `content_hash` = an unkeyed `sha256(plaintext)[:12]` (today's
  `Vault__Crypto.content_hash`), stored under the vault read key. For a sealed file that
  would let any vault reader *confirm a guess* of the content. **For sealed files the hash
  is taken over the sealed bytes.** The entry also gets a `sealed` flag and the
  recipients' fingerprints (still under the read key).
- **Blob reuse** (`encrypt_or_reuse_blob` matches on `content_hash`) then works on sealed
  bytes. Re-sealing an unchanged file is skipped as long as the plaintext is unchanged and
  the policy did not change (a local cache of plaintext hash → sealed blob).
- **Merge:** sealed files are binary unless both sides can be opened locally. A conflict
  keeps both versions (`.conflict`). Diff shows `sealed, changed` without an identity.

## 6. The decryption service ("identity provider")

Only the **16-byte file key** crosses the boundary, never the content:

```
sgit ──(stanza: recipient tag + wrapped FK)──► provider ──(FK, or "refused")──► sgit
```

| Provider | Where the private key lives | Notes |
|---|---|---|
| Local identity file | `~/.config/sgit/identities` (0600) | the simple default; written by the secret writer |
| ssh key / ssh-agent | your existing ssh key (ed25519/rsa) | age natively supports ssh recipients; nothing new to manage |
| Hardware | YubiKey / PIV / TPM / Secure Enclave via `age-plugin-*` | touch-to-decrypt; the key cannot be copied |
| Remote service | a team service, cloud KMS, or an SG/Send service, over an authenticated API | can **log, rate-limit, require approval and revoke** per unwrap, per file: an audit trail of who opened what. Offline means unreadable, by design |

Configuration is per clone (`.sg_vault/local/identities` naming providers) or per user.
The interface is the age plugin protocol, so any existing plugin works, and our own
remote-service provider is just one more plugin.

**Capability hand-off.** The same envelope moves *vault* capabilities between people.
`sgit share --to dinis` seals a read or write capability to Dinis's published key: no
passphrase in chat, argv or shell history. This closes most of TM-R14 and is phase 2 of
the earlier analysis.

## 7. What it protects, and what it does not

| Threat | Covered |
|---|---|
| Host reads content | yes (outer layer, as today) |
| A vault member who is not a recipient reads a sealed file | **yes** |
| The vault read key leaks (a share, a log, an old clone) | **yes for sealed files**: they need a recipient key as well |
| A recipient's key is revoked | only for **new** seals: history sealed to them stays readable to them (inherent; rotate secrets, not just files) |
| A non-recipient writer replaces a sealed file | detected with signed envelopes / author rules (§2); not prevented on the host |
| File names, paths, sizes, history from vault readers | not hidden (they live in the vault's tree). Sizes are approximate (age adds per-chunk overhead); pad if needed |
| Plaintext on a recipient's disk | out of scope: it is the recipient's machine (written 0600) |
| Provider compromise | as strong as the provider: hardware or approval-based providers limit it |

## 8. Relation to the native PKI mode

- **Independent of the vault mode:** sealed files work in symmetric vaults today.
- **In a PKI vault**, per-member envelopes are also the natural way to hand `DK` to each
  member: the vault's `DK` is sealed to every member's public key instead of to one
  shared `R`. Removing a reader then means re-sealing to the rest (native-mode doc §6).
- The deposit capability (native-mode doc §5) plus sealed files gives a **drop box**:
  contributors can add files that only the owner can open, and cannot read each other's.

## 9. Effort

| Step | What | CLI estimate |
|---|---|---|
| 1 | HPKE envelope (DHKEM(P-256, HKDF-SHA256) + AES-256-GCM, chunked), Python and Web Crypto with shared vectors; `seal export --age` | ~1 week |
| 2 | `.sgit/seal` policy, seal on commit, open on checkout/pull, sealed-bytes hashing, status rules | 1–1.5 weeks |
| 3 | Providers: identity file + ssh keys, then the plugin protocol (hardware/KMS), then a remote-service plugin | ~1 week (+ service side) |
| 4 | Signed envelopes + author rules on pull | ~0.5 week |
| 5 | `sgit share --to <contact>` (capability hand-off) | ~0.5 week |
| — | Web UI: open sealed files with Web Crypto (no WASM) + a provider bridge | web team |

## 10. Decisions for you

1. **Format (revised 10-10):** the Web-Crypto-native HPKE envelope, with age as an export and
   plugin-bridge format. (Was: age.)
2. **Working copy:** plaintext when the clone can open the file (git-crypt style), or
   always sealed on disk with `sgit cat` / `sgit open` to read?
3. **Integrity for sealed paths:** signed envelopes + author rules in the first version,
   or later?
4. **First remote provider:** an SG/Send-hosted unwrap service with approval and audit,
   or a cloud KMS plugin?
