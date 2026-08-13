# Security Response — External Review Remediation

**From:** SGit-AI CLI team
**To:** the external security reviewer (and anyone assessing sgit-ai's security posture)
**Date:** 2026-08-13
**Reviewed version:** `dev` @ `bca2a6f`
**Remediated in:** `431e4bf`, `5e62605`, `f7a840d`, `c7896cc`, `7874eac`
**Companion documents:**
- `team/explorer/architect/reviews/08/06/v0__security-review__crypto-entropy-simple-tokens.md` (our own independent review, which reached the same conclusion on tokens)
- `team/explorer/architect/contracts/08/06/v0__advisory__sg-send-api__simple-token-security.md` (the server/web half, not actionable in this repo)

---

## 0. Summary

Thank you for the review — it was accurate. We verified every finding against the source before acting on any of it, and we found one issue you did not report that was materially more serious than the one you did (§2.2).

**All five findings are now addressed.** Two of them were fixed more broadly than reported, one was fixed by deleting the feature outright rather than hardening it, and one (the 48-bit IDs) is *mitigated* rather than *eliminated* — we are explicit about that distinction in §3.

| # | Finding | Severity | Status |
|---|---|---|---|
| F1 | Share tokens ~30 bits entropy + `SHA256(token)[:12]` oracle | High | **Removed** — feature deleted, not hardened |
| F2 | Arbitrary file overwrite when receiving archives (zip-slip) | High | **Fixed, and broadened** — the same class existed in the core clone path |
| F3 | Object IDs only 48 bits, unconditional overwrite | Medium | **Mitigated** — silent corruption → loud failure. Width unchanged (§3.1) |
| F4 | Plaintext local signing key without explicit permissions | Medium | **Fixed** — 0600 regardless of umask |
| F5 | Supply chain: mutable `@dev` action refs | Concern | **Fixed** — all external actions pinned to verified SHAs |

Net change vs the reviewed commit: **97 files, +565 / −7168 lines**. The reduction is almost entirely the removed feature; the additions are the path guard, the collision guard, and 33 new security tests.

---

## 1. F1 — Simple Token entropy and the `transfer_id` oracle

### What you reported
Tokens are `word-word-NNNN` over a 356-word list ⇒ 356² × 10⁴ = 1.27×10⁹ ≈ **2³⁰·²**. The server-visible `transfer_id` is `SHA256(token)[:12]`, a fast unsalted hash of the secret, giving an offline oracle that bypasses the 600k-iteration PBKDF2 entirely.

### What we confirmed
All of it, independently, before you reported it — our own 6 August review reached the identical conclusion and added two details:

- The PBKDF2 salt was a **fixed global constant** (`b'sgraph-send-v1'`), so one precomputed table (~21 GPU-hours) would have covered *every* token vault ever created — strictly worse than a per-target attack.
- The token deterministically yielded **read key, write key and EC signing seed**, so recovery meant read, write *and* identity forgery — not just disclosure.
- The in-code comment describing the derived vault ID as "safe to log in URLs" was **false** for tokens (true only for passphrase vaults, where the ID is an HMAC under a 124-bit key).

### What we did
We did not attempt to harden the scheme. Raising entropy to a safe level (~6 EFF words) plus a memory-hard KDF plus a non-invertible public ID would have produced something no longer "simple", and the product had already stopped relying on it. **We deleted the entire feature** (`5e62605`):

- **Deleted:** `crypto/simple_token/*` (derivation + word list), `Vault__Transfer`, `Vault__Archive`, `API__Transfer`, `Transfer__Envelope`, the transfer clone workflow and all `Step__Transfer__*` steps, the transfer/archive schemas, `CLI__Share`, `CLI__Publish`, `CLI__Export`, `CLI__Disabled_Command`, `Safe_Str__Simple_Token`.
- **Commands gone:** `sgit share` (send/receive/publish), `sgit vault export`, `sgit vault share`, `sgit vault probe`, and the `sgit clone <simple-token>` transfer variant.
- **Derivation gone:** `Vault__Crypto.derive_keys_from_simple_token` and the auto-detect branch in `derive_keys_from_vault_key` that silently downgraded any token-shaped string to the weak path. `Safe_Str__Vault_Key`'s regex no longer admits the `word-word-NNNN` alternative.
- **Config gone:** `Schema__Local_Config.edit_token` and `Enum__Local_Config_Mode.SIMPLE_TOKEN`.

There is now **no code path in this repository that can mint, derive, or consume a low-entropy credential.** The `transfer_id` oracle does not exist because the function that computed it does not exist.

### Accepted consequence
This is a breaking change, taken deliberately: **existing simple-token-addressed vaults are no longer readable by the CLI.** They fail loudly (`ValueError` on the removed enum member) rather than silently misbehaving. The migration path is to re-key to a `passphrase:vault_id` vault key. Recorded in `CHANGELOG.md`.

### What this does *not* fix (important)
Your review correctly scoped itself to the CLI and excluded the Transfer API/server. Three things remain outside this repo and are tracked in our advisory to the SG/Send team:

1. **Existing token-addressed vaults on the server are still breakable** regardless of what the CLI does.
2. **If the web UI or transfer API still mints tokens**, users are still being handed weak credentials. We cannot see or change that from here.
3. **Historical logs are a recovery corpus.** Because `vault_id` for a token vault was an invertible function of the token, any log, CDN record, or object-store access log containing those IDs is a list of recoverable secrets, retroactively. That is an incident-response question for whoever owns those log pipelines, and it is time-sensitive.

---

## 2. F2 — Arbitrary file overwrite (path traversal)

### 2.1 What you reported
ZIP entry names were passed to `os.path.join(destination, path)` without rejecting absolute paths or `../`, so a malicious sender could escape the output directory. Same pattern on the binary-envelope filename.

### 2.2 What we found that you did not — and it was worse
The archive path was real, but it was **not the most serious instance of the bug**. The identical pattern existed in the **core clone/checkout path**, which has nothing to do with the transfer feature:

`Vault__Sub_Tree.checkout()` writes each file at `os.path.join(directory, full_path)` where the name comes from **decrypted tree-entry data** — chosen by whoever authored the vault, not by the user cloning it. So a hostile vault containing an entry named `../../.bashrc` (or an absolute path, which discards the destination entirely) would overwrite files outside the working copy on an ordinary `sgit clone`. The same held for `_checkout_flat_map` on the pull/merge path.

This mattered more than the reported instance because it is reachable through the primary workflow, needs no transfer feature, and survives the removal in §1. Had we only fixed what was reported, the more serious variant would have shipped.

### 2.3 What we did
Added `sgit_ai/storage/Vault__Path_Guard.py` (62 lines) and applied it at **every** working-copy write that consumes a vault-derived path. The guard rejects:

- empty paths;
- absolute paths (leading `/`, leading `\`, or `os.path.isabs`);
- any `..` component — detected after normalising **both** separators, so Windows-style `..\..\x` is caught on POSIX too;
- anything whose `abspath`-resolved target is not inside the destination (the backstop that catches whatever the component checks miss).

Guarded sites, all reachable on a hostile vault:

| Site | Reached by |
|---|---|
| `Vault__Sub_Tree.checkout` | `sgit clone`, checkout |
| `Vault__Sync__Base._checkout_flat_map` | `sgit pull` fast-forward, merge |
| `Vault__Sync__Base._remove_deleted_flat` | pull/merge deletions — a hostile path must not *delete* outside either |
| `Vault__Sync__Sparse` fetch | `sgit fetch <path>` |
| `Vault__Merge.write_conflict_files` | merge conflict materialisation |
| `Vault__Merge__Resolve._resolve_theirs` | `sgit resolve --theirs` |
| `Vault__Revert` restore loop | `sgit revert` |
| `Vault__Restore._extract_working_copy` | backup restore |

`checkout` fails closed (raises); the pull/merge helpers skip the offending entry, because those loops already tolerate per-file failures and aborting a whole pull on one hostile name would be a denial-of-service lever. Stash is deliberately **not** guarded: its paths are the user's own local files, never sourced from a vault.

The bare-restore zip extract uses `zipfile.extract()`, which sanitises `..` itself in modern Python — verified, left as is.

### 2.4 A bug we introduced and caught
While auditing our own fix we found that the first version of `safe_join` normalised `\` → `/` *before joining*. On POSIX a backslash is a legal filename character, so a vault containing `weird\name.txt` would have had that file silently written as the directory `weird/name.txt` — data corruption introduced by a security fix. Corrected in `7874eac`: the join now uses the original path and normalisation is used **only** for `..` detection. Regression tests assert both that the literal name round-trips and that `..\..\evil` is still rejected.

We mention this because it is the kind of defect a security patch is most likely to introduce, and because it is the direct answer to "do these fixes affect existing vaults?" — this one would have.

---

## 3. F3 — 48-bit object IDs

### What you reported
`obj-cas-imm-{sha256(ciphertext)[:12]}` is a 48-bit address, and the object store overwrote an existing path without collision detection. At ~1M objects the birthday probability is ≈0.18%.

### What we confirmed
Correct, and we had independently flagged it as F5 in our own review. Two distinct problems live inside this one finding:

1. **The consequence** — an unconditional overwrite turns a collision into *silent* data loss or a fetch returning the wrong object.
2. **The probability** — driven by the 48-bit truncation itself.

### 3.1 What we fixed, and what we did not
**Fixed — the consequence.** `Vault__Object_Store.store()` and `store_raw()` now read back and compare when an object already exists at a computed ID:

- identical bytes → idempotent no-op (the normal CAS-dedup case);
- **different bytes → raises `Vault__Object_Collision_Error`** instead of overwriting.

**Not fixed — the probability.** The IDs are still 48 bits. Widening them is not a patch: object IDs are a cross-runtime wire format embedded in tree entries, commit `tree_id`/`parents`, refs, and server `file_id` paths, and trees are themselves content-addressed — so changing the width re-identifies the **entire object graph** and requires a coordinated CLI + browser + server format bump plus a whole-vault migration (comparable to the existing `Migration__Tree_IV_Determinism`). We have scheduled that as a versioned format change to be bundled with the next breaking schema bump, and when it happens we will take the full 256-bit hash rather than an intermediate width, since the migration cost is identical either way and the size cost is negligible against ciphertext.

**So, precisely:** the risk of *silent* corruption from a collision is eliminated; the risk of *encountering* a collision is unchanged and still grows with adoption. We would rather state that plainly than claim the finding is closed.

**Unexpected benefit:** the guard is measurably *faster* than the code it replaced, because re-storing an already-present object is now a read-and-compare instead of a write — 19.4 µs vs 115.3 µs per op on tree-sized objects, 753 µs vs 899 µs at 256 KB.

---

## 4. F4 — Local signing key permissions

### What you reported
`store_private_key_locally` wrote the plaintext PEM with a plain `open(path,'w')`, so its mode depended on the process umask and could be group- or world-readable — unlike the rest of `.sg_vault/local/`, which is chmod'ed 0600.

### What we did
`Vault__Key_Manager.store_private_key_locally` now creates the file with `os.open(..., O_CREAT, 0o600)` and applies an explicit `chmod` afterwards, so the mode is 0600 irrespective of umask and there is no window in which the file exists with wider permissions.

Note on scope: we retain the deliberate decision that **the local clone is trusted storage** — the working copy is decrypted on disk anyway, so local-disk compromise implies content compromise regardless. What 0600 protects is the *other* local users on a shared machine, and the marginal exposure that the signing key grants (commit forgery) beyond what the working copy already reveals. Encrypting these at rest remains an explicitly accepted risk, matching the SSH-private-key trust model.

---

## 5. F5 — Supply chain

### What you reported
The release workflow invoked third-party publishing actions through a mutable `@dev` reference and publishes on pushes to `dev`; release automation should be pinned to full commit SHAs.

### What we did
Pinned **every** external action across all workflows and the composite action, not just the `@dev` ones, retaining the original ref as a trailing comment so updating is a one-line edit:

| Action | Pinned |
|---|---|
| `owasp-sbot/OSBot-GitHub-Actions` — `git__increment-tag`, `git__update_branch`, `pypi__publish` | `c2af482d73aaad222f7e6b091d35ab1e5c116f3b` `# dev` |
| `actions/checkout` | `11d5960a326750d5838078e36cf38b85af677262` `# v4` |
| `actions/setup-python` (workflow + composite) | `a26af69be951a213d495a4c3e4e4022e16d87065` `# v5` |
| `actions/upload-artifact` | `ea165f8d65b6e75b540449e92b4886f43607fa02` `# v4` |
| `docker/setup-buildx-action` / `login-action` / `build-push-action` | `8d2750c…` / `c94ce9f…` / `ca052bb…` |

Each SHA was resolved with `git ls-remote` against the upstream repository at pin time — none were guessed or recalled. Same-repo `./.github/...` references are unchanged, as they carry no supply-chain exposure.

**Not changed:** publishing still triggers on pushes to `dev`. That is a release-policy decision for the maintainer, not a defect we should alter unilaterally; the mutable-reference problem that made it dangerous is what we fixed.

---

## 6. Test coverage for the exploit paths

Your review noted an extensive suite (3,822 tests at the time) but did not distinguish general coverage from *exploit-path* coverage. We agree that distinction matters, and our first pass was uneven — the guard had unit tests but four of the newly guarded write sites had none. Current state, **33 tests specifically targeting these findings**:

| File | Tests | Covers |
|---|---|---|
| `tests/unit/storage/test_Vault__Path_Guard.py` | 15 | Guard unit behaviour: traversal, absolute, empty, both separators, literal-backslash preservation |
| `tests/unit/appsec/test_AppSec__Path_Traversal.py` | 3 | `checkout` driven with a malicious **tree entry name**, asserting nothing is written outside |
| `tests/unit/appsec/test_AppSec__Path_Traversal__Write_Sites.py` | 8 | Exploit payloads against `_checkout_flat_map`, `_remove_deleted_flat` (must not *delete* outside), merge conflict writes — each paired with a benign case so the guard cannot pass by breaking normal writes; plus a coverage-invariant test that fails if any known write-site module stops using the guard |
| `tests/unit/storage/test_Vault__Object_Store__Collision.py` | 4 | Idempotent identical store; `Vault__Object_Collision_Error` on differing bytes; foreign content not clobbered |
| `tests/unit/crypto/test_Vault__Key_Manager__Permissions.py` | 3 | PEM is 0600, including under `umask 000`; key still loads |
| `tests/unit/appsec/test_AppSec__Vault_Security.py` | 11 | Pre-existing: no plaintext in the object store, key never persisted in objects |

Honest limitation: sparse fetch, revert, and backup-restore are guarded and covered by the invariant test, but are exercised end-to-end only indirectly — they require full vault fixtures. We consider the residual risk low given the shared guard and the invariant test, and we would rather say so than imply uniform depth.

**Full unit suite: 3,483 passing.**

---

## 7. What remains open

We are not claiming a clean bill of health. Outstanding, in rough priority order:

| Item | Status | Why it is still open |
|---|---|---|
| **48-bit ID width** | Mitigated, not eliminated (§3.1) | Requires a coordinated cross-runtime format bump + migration; scheduled, not patchable |
| **Server-side token exposure** | Out of scope here | Existing token vaults, any web/API mint path, and historical log exposure are owned by the SG/Send team; advisory delivered |
| **Deterministic tree encryption leaks metadata** | Accepted, documented | Filename/size/content equality and dedup structure are visible to a key-less server. This is the deliberate price of CAS tree dedup; it weakens "the server learns nothing" and we state it rather than hide it |
| **PKI is classical-only** | Roadmap | ECDSA P-256 signatures and RSA-4096 messaging are quantum-vulnerable (harvest-now-decrypt-later applies to the messaging). Vault confidentiality is AES-256 and already quantum-resistant, so this is an authenticity/roadmap item, not a present-day exploit |
| **CI has no lint/type/dependency/security gate; coverage not enforced** | Open | Your Ruff (185) and Bandit (23 medium) findings and the 158 broad `except Exception` handlers are real. These are code-quality debt; adding gates is a process change we have not made |
| **PyPI publish triggers on push to `dev`** | Maintainer's decision | See §5 |
| **`Alpha` classifier** | Accurate | We are not changing it. The project is pre-1.0 and the label should reflect that |

---

## 8. On the original recommendation

Your recommendation was: sandbox only, avoid all simple-token sharing, accept transfers only from trusted senders, pin installation to an audited commit, and do not use for confidential data until the token design and path-containment issues are fixed and independently reviewed.

Against that list, as of the commits above:

- *"Avoid all simple-token sharing features"* — those features no longer exist.
- *"Accept transfers only from trusted senders"* — the transfer feature no longer exists; and the broader containment issue that made hostile input dangerous (including on ordinary clone, which your advice would not have covered) is fixed.
- *"Pin installation to an audited commit"* — still sound advice for any pre-1.0 tool, and now the release pipeline itself is pinned.
- *"Until the token design and path-containment issues are fixed **and independently reviewed**"* — the first two are done; **the independent re-review has not happened.** We would welcome one, and we would specifically ask a re-reviewer to attack the guarded write sites in §2.3 and the collision guard in §3.1.

We would characterise the current state as: the two High findings are closed, the client-side Mediums are closed or explicitly mitigated, the supply-chain concern is closed, and what remains is one scheduled format change plus code-quality debt — with the server-side half of the token problem still owned elsewhere.

---

*Every claim in this document was verified against the source at the commits listed in the header. The path-traversal scope in §2.2 and the self-inflicted bug in §2.4 were found by re-auditing our own remediation rather than by re-reading the report, which is why we recommend that any re-review start there.*
