# Advisory to the SG/Send API Team — Simple Token Security (lessons learned)

**From:** SGit-AI CLI team (architect review, 2026-08-06)
**To:** SG/Send API team — owners of the server-side vault read/write API and the web client
**Status:** Advisory + concrete asks. Nothing here is actionable by the CLI alone.
**Companion doc:** `team/explorer/architect/reviews/08/06/v0__security-review__crypto-entropy-simple-tokens.md`

---

## 0. Why you are getting this

We ran a security review of the SGit-AI CLI crypto with a focus on key entropy. The passphrase-vault path is sound. **The Simple Token path is broken**, and the break is at the **protocol/addressing layer**, not in the CLI.

We have disabled Simple Token *creation* in the CLI. That does not fix the problem, because:

1. **The vulnerability is in the derivation and the addressing scheme**, which the API and web client also implement.
2. **Existing token-addressed vaults on the server remain breakable**, regardless of what the CLI does.
3. **Several required controls are server-side only** (rate limiting, TTL, revocation, log hygiene).
4. **If the web UI / transfer API still mints tokens, users are still being handed broken vaults.** We cannot see or fix that from here — please confirm.

There is also a **time-sensitive operational item** in §4 (existing logs may already be a token-recovery corpus). Please read that one first if you read nothing else.

---

## 1. The finding, in one paragraph

A Simple Token (`word-word-NNNN`, 356-word list) carries **30.2 bits** of entropy (356² × 10⁴ = 1,267,360,000). The token deterministically yields the **read key, write key, and EC signing seed** — so recovering it means read, write, *and* identity forgery. The public vault identifier is `transfer_id = sha256(token)[:12]` — a **fast, unsalted hash of the 30-bit secret**. Anyone who observes a vault_id (cloud operator, CDN, log pipeline, object-store breach — precisely the parties zero-knowledge is meant to exclude) can enumerate the entire keyspace in **~0.1 seconds on a single GPU** and recover the token. The 600k-iteration PBKDF2 is bypassed entirely, because the fast hash is a shortcut around it.

Verify it yourself:

```python
# 1.27e9 candidates; one SHA-256 each. Match against any observed vault_id.
import hashlib, itertools
from wordlist import WORDS            # the 356-word list
target = "…12 hex chars from a vault path…"
for w1, w2 in itertools.product(WORDS, WORDS):
    for n in range(10000):
        t = f"{w1}-{w2}-{n:04d}"
        if hashlib.sha256(t.encode()).hexdigest()[:12] == target:
            print("token recovered:", t)   # -> full read+write+sign keys
```

---

## 2. The most important technical point: what actually fixes this

For a **self-contained shareable credential** (no server secret in the derivation), security is bounded by:

```
effective_security  ≈  token_entropy  +  log2(cost_per_guess)
```

That equation drives the entire remediation, and it rules out the two most tempting quick fixes:

| Change | Cheapest guess becomes | Total work at 30 bits | Verdict |
|---|---|---|---|
| *(today)* | 1 × SHA-256 (via `transfer_id`) | 2³⁰ → **~0.1 s / GPU** | broken |
| Remove the fast-hash public ID | 1 × PBKDF2-600k | 2⁴⁹·⁴ → **~21 GPU-hours** | still broken |
| Add a per-vault salt | 1 × PBKDF2-600k | same per target | **does not help** |
| Argon2id (256 MB, t=3) | 1 × memory-hard | expensive but finite | not sufficient alone |
| **Raise entropy to ~78 bits (6 EFF words)** | — | 2⁷⁸ × hard KDF | **infeasible** ✅ |

Two consequences worth internalising:

- **Salting does not rescue a self-contained token.** A salt derived from the token is recomputed per candidate by the attacker (no benefit). A transmitted random salt prevents *cross-target precompute* but still leaves ~21 GPU-hours per target. The current fixed global salt (`b'sgraph-send-v1'`) is worse still — it lets one **~21 GPU-hour table crack every token vault ever created** — but fixing only the salt leaves you broken.
- **Removing `transfer_id` is necessary but not sufficient.** Every derived identifier is an oracle: `ref_file_id` and `branch_index_file_id` are `HMAC(read_key, domain)`, so an attacker enumerating tokens derives each candidate's `read_key` and matches against observed file IDs. Removing the fast hash only raises the price from *one SHA-256* to *one KDF invocation* per guess.

**Therefore all three are required together: (1) no fast-hash public identifier, (2) memory-hard KDF, (3) raised entropy.** Entropy is the only fundamental fix; KDF hardness is a multiplier, not a substitute.

---

## 3. What the CLI has done (and why it isn't enough)

Shipped in `2dd1bd7`, `1d7b656`:

- `sgit vault export`, `sgit vault share`, `sgit share send`, `sgit share publish` → routed to a disabled stub (exit 2).
- `sgit clone <simple-token>` transfer-import path (`Step__Transfer__Init_Vault`) → gated before it mints a token.
- `sgit init` / `sgit create` → no longer auto-mint tokens; they use the 124-bit passphrase vault key.
- Verified: **no reachable CLI path calls the token generator**; `Vault__Sync.init(token=)` has no live callers.

Deliberately **retained**: token *consumption* (`share receive`, `clone <token>`, `vault probe`) and the whole derivation backend, so the rework can refactor in place.

**Why this is not a fix:** it is a client-side gate on one of several clients. The derivation, the addressing scheme, and the minting logic in the web/API are untouched. It is reversible by a one-line dispatcher change. It does nothing for vaults that already exist.

---

## 4. ⚠ Time-sensitive: your existing logs may already be a token-recovery corpus

Because `vault_id` for a token vault is an invertible function of the token, **any historical log containing those vault_ids is a list of recoverable secrets** — retroactively, for every simple-token vault ever created.

Please check for vault_ids in: S3/object-store access logs · CloudFront/CDN logs · API gateway / ALB access logs · application logs · SIEM and log-aggregation platforms · third-party analytics or APM · backups of any of the above.

This is an incident-response question as much as a design one, and the exposure may extend to systems outside your direct control (log processors, vendors). Suggested handling: inventory where vault_ids landed, assess retention and third-party reach, and treat any simple-token vault whose ID appeared in an externally-reachable log as **compromised — re-key rather than patch**.

---

## 5. What only the server / API can fix

| # | Ask | Why it must be server-side |
|---|---|---|
| **S1** | **Stop minting Simple Tokens** for anything durable or sensitive (web UI + transfer API). Confirm current behaviour. | Only you control the web/API mint path. The CLI gate does not cover it. |
| **S2** | **Change vault addressing** so the public ID is *not* a fast hash of the secret — derive it from the expensive KDF output, or use an **independent random ID** transmitted with the token. | Addressing is a wire/storage-layout decision spanning API + object store. |
| **S3** | **Rate-limit and monitor vault_id lookups**; alert on enumeration patterns. | Pure server-side control. Raises the cost of online probing. |
| **S4** | **TTL / expiry** for token-addressed vaults. | A self-contained token cannot expire itself. |
| **S5** | **Revocation list** for compromised/rotated tokens. | A self-contained token cannot revoke itself. |
| **S6** | **Log hygiene** — scrub/rotate vault_ids, shorten retention, keep them out of third-party sinks (see §4). | You own the log pipeline. |
| **S7** | **Uniform error semantics** — ensure 403/404 do not become an existence oracle for probing vault IDs. | Server response behaviour. |
| **S8** | **Migration plan** for existing token vaults: re-key to 124-bit passphrase vaults; treat old tokens as burned. | Requires server-side inventory + coordinated client support. |

---

## 6. Shared protocol changes (need joint coordination)

These cannot be shipped by one side alone. **CLAUDE.md requires byte-for-byte crypto interop between CLI, browser, and server**, and this is the binding constraint on the schedule.

| # | Change | Coordination note |
|---|---|---|
| **J1** | **Token KDF: PBKDF2 → Argon2id** (suggest 256–512 MB, t=3) | **Web Crypto has no Argon2** — the browser needs a WASM implementation. This is the main integration cost. |
| **J2** | **Wordlist: 356-word → EFF-large (7776 words, 12.9 bits/word)**, minimum **6 words (~78 bits)** for anything durable | Generators exist in multiple codebases; all must agree. |
| **J3** | **Version the token format** so old and new coexist during migration | Precedent exists — the PKI payload already carries `v`. |
| **J4** | **Shared test vectors** for every KDF/format change, asserted in all three runtimes | Non-negotiable per the interop requirement; make this the definition of done. |
| **J5** | **Tiered credential model** (see below) | Product + API + CLI must agree on which tier applies where. |

**Recommended tiering:**

- **Durable / sensitive vaults** → 124-bit passphrase vault key. *This is already the secure default; steer users here.*
- **Human-friendly durable share** (only if product requires it) → ≥6 EFF words + Argon2id + non-invertible public ID. Secure, but no longer "simple".
- **Ephemeral transfers only** → short token acceptable *only* with short TTL, server rate limiting, revocation, and an explicit "not for secrets" label in the UI.

---

## 7. Lessons learned (generalisable — worth adopting as review rules)

1. **Never derive a public identifier from a secret with a fast hash.** If an ID must be derived from a secret, derive it from the *expensive* KDF output — or make it independent and random. A fast public derivative silently nullifies every KDF iteration you paid for.
2. **A self-contained credential's security is capped at its own entropy.** No amount of KDF work rescues 30 bits. Fix entropy first; treat KDF hardness as a multiplier.
3. **Salting does not defend a self-contained token against enumeration** — it only prevents cross-target amortisation. A *fixed global* salt additionally converts a per-target attack into a one-time table for all targets: strictly the worst option.
4. **Use memory-hard KDFs (Argon2id) for human-memorable secrets.** PBKDF2 iterations are cheap to parallelise on GPU/ASIC; memory bandwidth is not.
5. **Count entropy against the real wordlist, in code review.** "word-word-NNNN" *sounds* adequate and is 30 bits. Put the arithmetic in the PR.
6. **Enumerate every public derivative of a secret** — not just the obvious one. Here, `ref_file_id` and `branch_index_file_id` are secondary oracles at KDF cost.
7. **Separate capabilities.** One string granting read + write + sign, with no expiry and no revocation, means any compromise is total and permanent.
8. **Disabling a client surface is not fixing a protocol.** It buys time; it is reversible in one line; it leaves existing data exposed.
9. **Ask "what does this put in the logs?"** An identifier derived from a secret turns routine logging into long-lived secret storage, retroactively and often outside your control.
10. **Human-friendliness and durable secrecy are in tension.** Resolve it with explicit tiers and honest UI labelling, not by hoping a short token is good enough.

---

## 8. Concrete checklist

**Immediate**
- [ ] Confirm whether web UI / transfer API still mints Simple Tokens (**S1**)
- [ ] Audit logs/backups for vault_id exposure; assess third-party reach (**§4**, **S6**)
- [ ] Decide policy for existing token vaults: re-key vs. accept (**S8**)

**Near-term (P0 — classically exploitable today)**
- [ ] Non-invertible vault addressing (**S2**)
- [ ] Argon2id token KDF, versioned, with shared test vectors (**J1**, **J3**, **J4**)
- [ ] EFF wordlist, ≥6 words for durable tokens (**J2**)
- [ ] Rate limiting, TTL, revocation, uniform errors (**S3**, **S4**, **S5**, **S7**)
- [ ] Agree tiered credential model + UI labelling (**J5**)

**Roadmap (P1 — no known practical attack yet)**
- [ ] Widen 48-bit truncated object/file IDs to ≥128 bits (CAS collision risk ≈ 2²⁴ objects)
- [ ] Decide on deterministic-encryption metadata leak: mitigate or document as accepted
- [ ] Hybrid post-quantum PKI — Ed25519+ML-DSA signatures, X25519+ML-KEM messaging (payload-versioned). *Note: vault confidentiality is AES-256 and already quantum-safe; the quantum exposure is the PKI, in particular harvest-now-decrypt-later on RSA-4096 contact messaging.*

---

## 9. Open questions for you

1. Does the web UI or transfer API still create Simple Tokens? Under what flows?
2. Are vault_ids present in any log sink, and what is the retention / third-party reach?
3. How many token-addressed vaults exist today, and can you enumerate them for migration?
4. Is there any server-side rate limiting on vault_id lookups today?
5. What is the intended lifetime of PKI contact messages? (Determines urgency of the ML-KEM migration — harvest-now-decrypt-later only matters for long-lived secrets.)
6. Can the browser take a WASM Argon2 dependency, and on what timeline? *This gates J1 and is likely the critical path for the whole P0 set.*

---

## 10. Scope note — what the CLI team decided

- **Accepted risk:** vault keys / `edit_token` are stored in cleartext in the local clone (`.sg_vault/local/config.json`), and local signing keys as unencrypted PEM. Rationale: the clone already contains the decrypted working copy, so local disk access implies content compromise regardless; the marginal exposure is *remote* capability (pull, push/forge, other branches), which matches the SSH-private-key trust model. Recorded as a deliberate decision, not an open finding.
- **Out of CLI scope:** everything in §5 (server-side controls) and §6 (joint protocol changes). We can implement the CLI half of any agreed protocol change and supply CLI-side test vectors.

*Contact: SGit-AI CLI team. Full analysis, entropy arithmetic, and threat model in the companion review linked at the top.*
