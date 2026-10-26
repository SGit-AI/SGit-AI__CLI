# Review: "Sealed vault keys: the requirements and the design, side by side" (cli.sgit.ai, 24 Oct 2026)

**Reviewed:** https://cli.sgit.ai/research/sealed-vault-keys-side-by-side.html, with the two documents it compares (the pki.sgit.ai agent's requirements R1–R10; the design article *A vault key that never lands*), against SGit-AI__CLI at 70b3748 (main after the 0.24.0 release; the code the page cites is 182cfc1 and nothing it names changed since). **By:** the CLI agent, for Dinis. **Date:** 24 Oct 2026.

## 1. Verdict

The page is accurate and the synthesis is the right one. Every code claim I could check holds (section 2). The four changes it makes to the design (argv refused everywhere, the record fingerprint, a recovery recipient, explicit-fingerprint trust first) are each correct, and the phase order is right: the single key source first, because it is the only part with regression risk and everything else stands on it. The three things I would add before Phase 2 is specified are in section 3; none of them changes the shape.

## 2. The code claims, re-checked

| Claim on the page | Checked | Note |
|---|---|---|
| `local/vault_key` is plaintext, 0600, through one helper that encrypts nothing | holds | `Vault__Secret_File` |
| 14 commands take a vault key on argv | holds within one or two | 12 `--vault-key`/positional in `CLI__Main`, `branch checkout --vault-key`, `vault restore --key`, `vault attach --read-key`; `clone -` reads stdin (`_key_from_stdin`) |
| The pki private key is PBKDF2 at 2,048 iterations | **holds, reproduced** | `openssl asn1parse` on a key exported by `PKI__Crypto.export_private_key_pem` with a passphrase: PBES2, PBKDF2, `INTEGER :0800`, hmacWithSHA256, aes-256-cbc. That is `BestAvailableEncryption`'s default in `cryptography`. Vault keys get 600,000 (`_pbkdf2_cached`) |
| `pki keygen` prints the encryption fingerprint as "Fingerprint" and the signing one second; `--recipient` matches by `encryption_fingerprint` | holds | `CLI__PKI.py:44-45`, `PKI__Known_Keys.py:23` |
| The key store is always `~/.sg-send` | holds | `pki.setup()` with no argument; no env var is read |
| 27 call sites in 17 files read the key file | **holds exactly** | `_read_vault_key(` + `vault_key_path(` + `load_vault_key(` across `sgit_ai/`: 27 calls, 17 files |
| The read key sits in `clone_mode.json` in clear, "accepted risk F07" | holds; the register id is stale | F07 is the June AppSec register's number. The current threat model carries it as **TM-R15** (and KNOWN-ISSUES as KI-SEC-03). The page should cite TM-R15 so a reader can find it |
| The clone's signing key is unencrypted PKCS#8 | holds | `Vault__Key_Manager.store_private_key_locally` → `export_private_key_pem` with no passphrase → `NoEncryption` |
| The token is in clear | holds | `CLI__Token_Store.save_token` |
| `vaults.enc` uses one fixed salt for every user | holds, already registered | `Secrets__Store`: `f'{SECRETS_SALT_PREFIX}:master'`. This is **TM-R11** in the threat model (Known_Gaps test `test_TM_R11__secrets_store_uses_one_global_salt`); the page lists it under "where both are silent", but the threat model is not silent on it |
| The v2 envelope wraps one AES key for one recipient | holds | `hybrid_encrypt`: one `w` field |
| Argon2id is "already in the library sgit uses" | holds here, with a condition | `cryptography.hazmat.primitives.kdf.argon2.Argon2id` derives in this sandbox (cryptography 49, 0.35 s at 3 passes / 64 MiB / 4 lanes). It needs the wheel's OpenSSL ≥ 3.2; a source build against an older OpenSSL raises at import. The private-key file needs a KDF id in its header and scrypt as the fallback, so a key made on one machine opens on another |

## 3. What I would add

**3.1 The socket, not the environment variable.** `eval "$(sgit agent start)"` sets `SGIT_AGENT_SOCK` in one shell. The agents this is for (Claude Code sessions, CI steps) run every command in a fresh shell, so an environment variable set by one command is gone by the next. Default to a well-known per-user socket path (`~/.sg-send/agent.sock`, or `$XDG_RUNTIME_DIR/sgit-agent.sock` where it exists), the way gpg-agent does, with the variable as the override. Otherwise the first thing every agent does is write the socket path somewhere, and the design's "nothing in clear" has a new file to think about.

**3.2 Say what the agent closes and what it does not, in one sentence, at the top.** The socket is reachable by "only its user" — which is exactly the boundary `0600` already gives the key file. So the agent does not change what a same-user process can do while the agent is unlocked; it changes what a *copy of the folder* can do: a backup, a zip of the workspace, a container image, `vault backup --include-key`, a disk read after the session. That is the real win (every working copy on every machine no longer holds every key), and it is worth stating as the threat closed, so nobody reads "sealed at rest" as protection from a compromised session. The design's own "what this does not claim" says it; the side-by-side should carry it into the verdict.

**3.3 The recovery recipient is a policy, not a default.** Sealing every clone's key to the operator's master key as well (3.2 on the page) means the operator can open every agent's vault. That is right for Dinis's agents and wrong as a product default: make it a setting of the identity (`sgit id init --recovery <fp>`), recorded in the sealed file, and have `clone --sealed` say "sealed to: this identity and sha256:… (recovery)". Also: the recovery key then guards everything, so it should be a lasting or hardware key, never a session one — the design's own rule for backups, applied to the recovery recipient itself.

**3.4 "Crypto-shredding is immediate" needs one qualifier.** Destroying an agent's pki key makes *that agent's* at-rest sealed copies unreadable. It does not touch the vault key, which the sender, other agents and any clone that opened it still hold. The page says the live-session case needs `vault rekey`; it should say the same for every other holder. Retiring an agent key revokes the agent's copies, not the vault.

**3.5 The in-process cache is where keys live today.** `Vault__Crypto._pbkdf2_cached` is an `lru_cache` keyed by the passphrase bytes: a long-lived process that touched N vaults holds N passphrases in that dict for its lifetime. With the agent model the cache belongs inside the agent, and the key source should hand out derived keys only. Worth a line in Phase 1, because it is the one place the "exists only in memory" story is already true and nobody chose it.

**3.6 R2 needs a third route for scripts.** Refusing argv is right; "an explicit opt-in" is right; but a script that cannot use stdin (it needs stdin for something else) or a file (it must not write the key) has nothing. Add a file-descriptor form (`--vault-key-fd 3`, the way `gpg --passphrase-fd` works): no argv, no environment, no file.

**3.7 The acceptance test for memory cannot be what it says.** "Scan for the session key's bytes after the session" tests the disk, which is right; it cannot test memory, and the design says so (Python cannot promise erasure). What *can* be tested: `RLIMIT_CORE` is 0 in the agent, `PR_SET_DUMPABLE` is 0, swap is not a place the test can reach. Write the test as those three checks, not as a scan.

## 4. Priorities, as I would cut them

- **0.24.x, small and safe:** Argon2id (with the KDF id and the scrypt fallback) for `pki keygen`; the fixed-salt fix (TM-R11); R7 across all output; the R2 *warnings*. None of these changes a file format a current clone reads.
- **0.25.0, the feature:** Phase 1 (the one key source, with the cache moved behind it) and Phase 2 (`sgit id`, `sgit agent` with a well-known socket, `vault_key.sealed`, `clone --sealed`, `vault seal-local`, the read key and the token sealed, R8's persistence check). `clone --sealed` without an agent (a passphrase prompt per command) is a valid first step for a person at a keyboard, and lets the agent land separately.
- **Later:** Phase 3 (sending, trust rules) and Phase 4 (hardware, identity-signed commits), as the page has them.

## 5. Two corrections for the page

- Cite **TM-R15** for the read key in `clone_mode.json` and **TM-R11** for the fixed salt; "F07" is the June register's id and the salt is not something "both are silent" on.
- Argon2id's availability is conditional on the `cryptography` wheel's OpenSSL (≥ 3.2); say "in the wheels sgit installs" rather than "in the library".
