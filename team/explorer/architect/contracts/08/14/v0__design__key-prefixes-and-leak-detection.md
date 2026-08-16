# Design — Identifiable Key Prefixes & Leak Detection

**Version:** v0 (proposal — awaiting maintainer sign-off on the prefix strings)
**Date:** 2026-08-14
**Role:** Architect (Explorer)
**Problem:** sgit's secrets are unscannable. A vault key is
`{passphrase}:{vault_id}` — an arbitrary string with a colon — and a read key
is bare 64-hex. Neither can be reliably detected by secret scanners, git
hooks, or GitHub push protection, so a key pasted into a repo, a log, or a
vault file leaks silently. Industry practice (GitHub `ghp_`, AWS `AKIA`,
OpenRouter `sk-or-v1-`, Anthropic `sk-ant-`) is a distinctive prefix that
makes the secret self-identifying.

---

## 1. Prefix format (proposed)

There is **no cross-vendor standard prefix to adopt** — the convention is the
*shape*: short vendor tag + type tag + version, delimited so that (a) the
regex is trivial and anchored, (b) double-click selects the whole token,
(c) the type and version are readable by a human at a glance. Underscore
delimiters (GitHub's choice, made for exactly reasons a+b) fit best:

| Secret | Today | Prefixed form | Scanner regex |
|---|---|---|---|
| Vault key | `{passphrase}:{vault_id}` | `sgit_vk1_{passphrase}:{vault_id}` | `\bsgit_vk1_[^\s"']+` |
| Read-only key | `{64 hex}` | `sgit_rk1_{64 hex}` | `\bsgit_rk1_[0-9a-f]{64}\b` |

- The digit is the **format version** (future rotation → `vk2`), not a crypto
  version — key *material* is untouched.
- **The value after the prefix is byte-identical to today's key.** That single
  property is what gives the whole design its compatibility story: any old
  sgit or old SG/Vault web works if the user strips the prefix by hand.
- Read keys become *perfectly* scannable (fixed alphabet + length). Vault keys
  are scannable from the anchor even though the passphrase tail is free-form.
- Rejected alternatives: `sk-`-style prefixes (collide with the sk- namespace
  other vendors mine; invite misclassification), embedding a checksum GitHub-
  style (worthwhile, but it changes the token tail and would break the
  "strip the prefix and it works" rule — revisit at `vk2` if ever).

## 2. Where the change lands (small, by construction)

Parsing is already centralised, which is what makes this cheap:

- `Vault__Crypto.parse_vault_key` (`crypto/Vault__Crypto.py:45`) — strip a
  leading `sgit_vk1_` before the existing `rsplit(':', 1)`. Every vault-key
  consumer (init, clone, clone-branch/headless/range, move, credential store)
  goes through it or through `derive_keys_from_vault_key`.
- `Vault__Crypto.import_read_key` (`crypto/Vault__Crypto.py:126`) — strip a
  leading `sgit_rk1_` before `bytes.fromhex`. Read-only clone and
  `derive-keys` go through it.
- **Display/generation sites** switch to emitting the prefixed form:
  `CLI__Create.py:99,102`, `CLI__Vault.py:193,1411,1451,1800,1808`, and
  `sync.init`'s returned `vault_key`. `.sg_vault/VAULT-KEY` and
  `clone_mode.json` store the prefixed form for NEW vaults/clones; readers
  accept both, existing files are never rewritten.
- SG/Vault web: mirror the same two strip-on-input rules and emit prefixed on
  display. Until it does, users paste the part after the prefix — degraded but
  functional, per the compatibility rule.

### Compatibility matrix

| Actor | Old (bare) key | New (prefixed) key |
|---|---|---|
| New sgit / new SG/Vault web | accepted (strip is conditional) | accepted |
| Old sgit / old SG/Vault web | works as today | works after manually removing the prefix — key material identical |
| Server | never sees keys (zero-knowledge) — no change | same |

Existing vaults: zero impact. Keys are not rotated, re-derived, or re-stored;
only newly *displayed* keys gain the prefix.

## 3. Detection layers (what the prefix unlocks)

1. **Generic scanners.** Ship the two regexes as: a `gitleaks.toml` fragment
   and a GitHub custom-pattern snippet, published in `docs/` so any org can
   paste them; long-term, GitHub's secret-scanning partner program becomes
   possible (requires the distinctive prefix — this is the enabling step).
2. **Git pre-commit hook.** `sgit hooks install` writes a pre-commit hook that
   greps staged content for both patterns plus the heuristic legacy pattern
   (bare 64-hex near the words key/vault — warn, don't block, on that one).
3. **sgit's unfair advantage — exact-match self-scanning.** Unlike a generic
   scanner, sgit *knows the current vault's own secrets* (vault key, read key,
   derived hex forms). `sgit commit`/`push` can therefore check outgoing
   plaintext for exact occurrences of this vault's own key material — catching
   even legacy unprefixed keys with zero false positives. This closes the
   worst loop: pushing a vault's own key *into* that vault, where every
   read-only holder can read it. Implementation note: match on the derived
   hex strings and the stored key strings; constant strings in memory the CLI
   already holds — no new secret handling.
4. **`sgit doctor`** gains a secrets section: scan the working tree and staged
   git content for patterns 1–3 and report.

Default posture: **block on exact-match self-leak (layer 3), block on
prefixed-key matches, warn on legacy heuristics** — overridable with an
explicit `--allow-secret` so the valid cases stay possible but deliberate.

## 4. The valid case — storing a vault key inside a vault

Storing vault B's key inside vault A is legitimate (key escrow, team handoff).
The rule the push-guard enforces: a vault key stored in a vault must be
**wrapped** so that A's read-only holders cannot read it. Proposed
`sgit secrets put <name>` / `sgit secrets get <name>`:

- Wrap: AES-GCM encrypt the secret under a key derived from A's **write key**
  (`HKDF(write_key, info='sg-vault-v1:secret-wrap')`) — read_key holders (and
  the Lambda §4.2 persona) see only ciphertext; writers can unwrap. Stored as
  an ordinary vault file with a recognisable envelope
  (`{"sgit_secret_v1": {...}}`) that the push-guard treats as already-safe.
- The push-guard's exact-match layer then has a clean answer when it fires:
  "this looks like a vault key in plaintext — wrap it with `sgit secrets put`
  or pass `--allow-secret`."
- Double-encryption comes free: the vault layer encrypts the file again with
  the content key, so at rest on the server it is ciphertext-in-ciphertext.

## 5. Rollout

1. Accept-both parsing + prefixed display (one release; trivially reversible).
2. Detection: hook installer, doctor section, scanner-rule docs.
3. Push-guard (warn-only for one release, then block-by-default) +
   `sgit secrets put/get`.
4. Coordinate SG/Vault web adoption of §2 (two strip rules + display change);
   publish the regexes to their team at the same time.

## 6. Open decisions for the maintainer

1. **The prefix strings themselves** — `sgit_vk1_` / `sgit_rk1_` proposed.
   (Alternatives considered: `sgv_`/`sgr_` — shorter but less self-explanatory
   and weaker as a search anchor; `sgit-vk1-` — hyphens break double-click
   selection.) A one-way door once users share prefixed keys: pick once.
2. Should `VAULT-KEY` files in *existing* clones be rewritten to prefixed on
   next use (better local scannability) or left untouched (proposed: untouched
   — minimal side effects; an old CLI sharing the clone keeps working)?
3. Push-guard default: warn-first release then block, or block from day one?
