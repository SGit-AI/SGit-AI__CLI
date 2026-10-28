# Design 02: signing commits and tags with your own key, the way Git does it

**Roadmap item:** 2.2 in `roadmap__git-parity.md` (priority 1).
**Status:** design, not built. Written against `c57aea9`+ on `claude/charming-babbage-5hzcxq`.
**Size:** about 4 days with tests (section 10).
**Gate:** none. Section 5.9 proves why; two items must still be confirmed before release (5.9.4, D7).

---

## 1. Summary and the exact Git behaviour matched

Git does not decide who is allowed to write. It signs with the key the user already has, stores the signature in the
commit, and leaves trust to whoever verifies. sgit does the same, as an optional second signature next to the
per-clone ECDSA signature it already makes.

### 1.1 Signing

| Concern | What Git does | What sgit will do |
|---|---|---|
| Key source | `user.signingKey`; for SSH, `gpg.ssh.defaultKeyCommand` when unset | Same keys, read from the user's Git config (5.6) |
| Formats | `gpg.format = openpgp` (default), `ssh`, `x509` | `openpgp` and `ssh`. `x509` is refused by name (non-goal) |
| Program | `gpg.program` / `gpg.openpgp.program`; `gpg.ssh.program` (default `ssh-keygen`) | Same keys, same defaults |
| SSH signing call | `ssh-keygen -Y sign -n git -f <key>` (a literal key goes in a temporary file, with `-U` meaning "the private half is in the agent") | Same argv. The payload goes on stdin and the signature comes back on stdout, so the payload never touches disk (5.5) |
| GPG signing call | `gpg --status-fd=2 -bsau <key>`, payload on stdin, armored detached signature on stdout | `gpg --status-fd=2 -bsu <key>` (binary, not armored, so it is stored compactly); `SIG_CREATED` required on the status fd |
| When it signs | `commit.gpgSign`, `tag.gpgSign`, `tag.forceSignAnnotated`, `-S` / `--gpg-sign[=<key>]`, `--no-gpg-sign`, `tag -s` / `-u <key>` | The same flags. The automatic switch is `sgit.gpgSign` (D2), so an existing `commit.gpgSign = true` does not change what agents do after an upgrade |
| Where it lives | `gpgsig` header in the commit, excluded from the signed bytes | `user_signature` member in the commit JSON, excluded from **both** signatures' signed bytes (5.1) |
| Failure | "gpg failed to sign the data", no commit is written | Same: refuse, nothing written, exit 1 |

### 1.2 Verifying

| Concern | What Git does | What sgit will do |
|---|---|---|
| SSH trust | `gpg.ssh.allowedSignersFile`, `gpg.ssh.revocationFile` | Same files, read in-process (5.4), with `ssh-keygen` as a fallback for the cases in 5.4.5 |
| SSH verify | `ssh-keygen -Y find-principals`, then `-Y verify -n git -I <principal> -Overify-time=<commit date>`; if no principal matches, `-Y check-novalidate` | The same three outcomes, computed in-process |
| GPG verify | `gpg --keyid-format=long --status-fd=1 --verify <sigfile> -`, then parse `GOODSIG`/`BADSIG`/`ERRSIG`/`EXPSIG`/`EXPKEYSIG`/`REVKEYSIG`/`VALIDSIG`/`TRUST_*` | Same command and parser |
| Result codes | `%G?`: `G` good, `B` bad, `U` good with unknown validity, `X` good but expired signature, `Y` good but expired key, `R` good but revoked key, `E` cannot check, `N` no signature | Same letters, plus word names (5.2) |
| Display | `log --show-signature`, `verify-commit`, `verify-tag`, `tag -v` | `history log --show-signature`, `history show --show-signature`, `check verify`, `vault tag show` |

**What stays as it is:**

- **The clone key.** Every commit keeps its per-clone ECDSA signature (`signature`, `author_key_id`).
  `signatures-required` keeps meaning "every commit carries a valid clone signature".
- **TM-R01.** It is unchanged at vault level. It is closed for any verifier who keeps an allowed-signers file, in
  exactly the way Git closes it (6.1).

---

## 2. Scope and non-goals

### 2.1 In scope

- Commits and annotated tags (`vault tag create`) carry an optional user signature.
- SSH (all key types OpenSSH signs with, 5.4.3) and OpenPGP via `gpg`.
- Settings are read from the user's Git config (global and system), and can be overridden per command.
- Verification surfaces:
  - `history log --show-signature`
  - `history show --show-signature`
  - `check verify`, extended with a user-signature summary, `--require-user-signature` and `--json`
  - `vault tag show`
  - the `--json` output of those commands
- An in-process verifier for SSH signatures. No `ssh-keygen` is needed to verify; it is needed only to sign with
  agent or hardware keys.
- A per-clone verification cache.

### 2.2 Non-goals

Each one is listed with where it belongs instead.

| Non-goal | Where it goes |
|---|---|
| A list of who may write, carried in the vault; owner keys; joining; revocation records | SGitHub (future server), roadmap section 4 |
| A vault policy requiring user signatures (a `user-signatures-required` feature) | Not Git behaviour. The local gate is `check verify --require-user-signature` |
| X.509 / `gpgsm` | Later, if asked |
| SSH certificates (`cert-authority` lines) verified in-process | Delegated to `ssh-keygen` when installed; otherwise reported as `cannot-check` (5.4.5) |
| Binary KRL revocation files in-process | Same delegation |
| Re-signing history that a rewrite produces (pack import/export, migrate) | Signatures are dropped and counted (7.6), as `git filter-repo` drops them |
| A name/email author field in commits | A separate parity item. The principal from the allowed-signers file is what identifies the signer |
| User signatures on pack index headers | Not needed (7.11) |
| A new top-level command | Rule 9: everything below is flags on existing commands |

---

## 3. CLI surface

### 3.1 Flags

Git's spelling everywhere it exists.

| Command | New flags | Notes |
|---|---|---|
| `sgit commit` | `-S`, `--gpg-sign`, `-S<KEY>`, `--gpg-sign=<KEY>`, `--no-gpg-sign` | The key form must be **attached** (as in Git): `-S msg` must not read `msg` as a key, because `message` is an optional positional. See 3.3. |
| `sgit write` | same | Agents normally pass nothing; the switch is off unless `sgit.gpgSign` is set |
| `sgit pull`, `sgit branch merge` | `-S` / `--gpg-sign[=KEY]` / `--no-gpg-sign` | Sign the merge commit (Git: `pull -S`, `merge -S`) |
| `sgit history revert --as-commit` | same | Goes through `commit()` (`Vault__Sync__History_Edit.py:105`) |
| `sgit vault tag create` | `-s` / `--sign`, `-u <KEY>` / `--local-user <KEY>`, `--no-sign` | Git `tag -s` / `-u`; every sgit tag is annotated, so `tag.forceSignAnnotated` counts as `tag.gpgSign` |
| `sgit history log` | `--show-signature` | Also a `user_signature` object in `--json` |
| `sgit history show` | `--show-signature` | |
| `sgit check verify` | `--user` (show per-commit user-signature lines with `--verbose`), `--require-user-signature`, `--json` | The summary line for user signatures is printed whenever any checked commit has one |
| `sgit vault tag show` | none | Always reports the user signature when present |

### 3.2 Configuration

Configuration is read from Git's config files (5.6). There is nothing to set in sgit.

| Key | Meaning in sgit | Default |
|---|---|---|
| `sgit.gpgSign` | sign every commit and tag (the automatic switch, D2) | `false` |
| `user.signingKey` | key to sign with (GPG key id/email/fingerprint; SSH private-key path, public-key path, or literal `ssh-…` / `key::ssh-…`) | unset |
| `gpg.format` | `openpgp` / `ssh` (`x509` refused by name) | `openpgp` |
| `gpg.program`, `gpg.openpgp.program` | gpg binary | `gpg` |
| `gpg.ssh.program` | ssh-keygen binary | `ssh-keygen` |
| `gpg.ssh.allowedSignersFile` | trust file for SSH | unset → every good SSH signature is `untrusted` (`U`), as in Git |
| `gpg.ssh.revocationFile` | revoked SSH keys (plain public-key lines; a KRL is delegated, 5.4.5) | unset |
| `gpg.ssh.defaultKeyCommand` | prints a key to use when `user.signingKey` is unset (Git: e.g. `ssh-add -L`) | unset |
| `gpg.minTrustLevel` | lowest GPG trust that counts as `good` | Git's default (5.7.3) |
| `commit.gpgSign`, `tag.gpgSign`, `tag.forceSignAnnotated` | **read only for display** (`sgit doctor` mentions them), never acted on unless `sgit.gpgSign` is also true (D2) | n/a |

### 3.3 How the attached key form is parsed

`CLI__Main.run` gets a pre-parse step, `CLI__Argv__Signing.normalise(argv)`:

- `-S<KEY>` becomes `--gpg-sign-key <KEY> -S`
- `--gpg-sign=<KEY>` becomes `--gpg-sign-key <KEY> --gpg-sign`
- bare `-S` / `--gpg-sign` are left as flags (`store_true`)

`--gpg-sign-key` is a hidden option, so `-S msg` keeps meaning "sign, message msg". The step applies only to argv
tokens in the commands listed in 3.1, and only when they come before `--`.

### 3.4 Output

**Signing.** A signed commit adds one line to the existing commit output:

```
Signed with ssh key SHA256:uK0E…Qx8 (user.signingKey ~/.ssh/id_ed25519.pub)
```

A signing failure exits 1 and writes nothing:

```
error: signing failed: ssh-keygen: agent refused operation
       nothing was committed. Run again without signing: sgit commit --no-gpg-sign
```

**`history log --show-signature`.** The line goes under each commit, worded as Git words it:

```
  commit obj-cas-imm-3f9a…
  Good "git" signature for alice@example.com with ED25519 key SHA256:uK0E…Qx8
  Clone signature: verified (key-rnd-imm-0011223344556677)
  Date:      …
```

The other outcomes:

| Outcome | First line |
|---|---|
| untrusted (`U`) | `Good "git" signature with ED25519 key SHA256:…` and then `No principal matched.` |
| bad (`B`) | `BAD signature from <principal or key fingerprint>` |
| GPG | the gpg status summarised: `Good signature from "Alice <a@x>" [full]` / `[unknown]` |
| none (`N`) | nothing (Git prints nothing for an unsigned commit) |

**`check verify`.** One new summary line, printed only when at least one commit carries a user signature:

```
Checked 412 commit(s): 412 verified, 0 bad, 0 unsigned, 0 without a known key, 0 missing
User signatures: 37 good, 2 untrusted, 0 bad, 0 expired key, 0 revoked, 0 cannot check, 373 none
```

**`vault tag show v1.0`:**

```
  Signature: signature verified
  Signed by: alice@example.com (ssh, good)
```

### 3.5 Exit codes

| Command | Exit 0 | Exit 1 |
|---|---|---|
| `commit` / `write` / `pull` / `branch merge` / `vault tag create` with signing on | signed and written | signing failed; nothing written (no commit, no ref move, no tag object) |
| `check verify` | nothing bad | as today a bad clone signature, **plus** any user signature that is `bad`. `untrusted`, `expired-key`, `revoked`, `cannot-check` and `none` do not fail (Git parity: `verify-commit` exits 0 for `U`) |
| `check verify --require-user-signature` | every checked commit is `good` | any commit is not `good` |
| `vault tag show` | unchanged rule: the tag's clone signature must verify | additionally a `bad` user signature |

### 3.6 JSON shapes

The same object appears in `history log --json`, `history show --json`, `check verify --json` (per commit with
`--verbose`) and `vault tag show --json`. All values are strings:

```json
"user_signature": {
  "status":          "good",
  "code":            "G",
  "format":          "ssh",
  "principal":       "alice@example.com",
  "key_type":        "ED25519",
  "key_fingerprint": "SHA256:uK0E…Qx8",
  "signed_at_ms":    "1761600000000",
  "reason":          ""
}
```

`status` is one of `good`, `untrusted`, `bad`, `expired-signature`, `expired-key`, `revoked`, `cannot-check`, `none`.

`check verify --json` adds:

```json
{
  "total": 412,
  "counts": { "verified": 412, "bad": 0, "unsigned": 0, "no-key": 0, "missing": 0 },
  "user_counts": { "good": 37, "untrusted": 2, "bad": 0, "expired-signature": 0, "expired-key": 0,
                   "revoked": 0, "cannot-check": 0, "none": 373 },
  "user_by_status": { "untrusted": ["obj-cas-imm-…", "…"], "bad": [] },
  "first_failure": null
}
```

---

## 4. How the code works today

### 4.1 Commit schema and the signing input

| File:line | What it does |
|---|---|
| `sgit_ai/schemas/Schema__Object_Commit.py:11-21` | Fields: `schema`, `tree_id`, `parents`, `timestamp_ms`, `message_enc`, `branch_id`, `signature`, `author_key_id`, `author_signature` (reserved), `attestations` (reserved). |
| `sgit_ai/safe_types/Safe_Str__Signature.py:5-14` | `^[A-Za-z0-9+/=]{1,256}$`, max 256, strict. **Too small for an SSHSIG or OpenPGP signature**. A 300-character `author_signature` is rejected (tested 28 Oct), so the reserved field cannot be reused without breaking every existing client. |
| `sgit_ai/storage/Vault__Commit.py:34-36` | `signing_bytes`: JCS of `commit.json()` minus `signature` (sorted keys, compact, UTF-8, `ensure_ascii=False`). |
| `sgit_ai/storage/Vault__Commit.py:38-40` | `legacy_signing_bytes`: `json.dumps(commit.json())` with `signature: None`, default separators. Used for commits without `author_key_id`. |
| `sgit_ai/storage/Vault__Commit.py:42-76` | `create_commit`: builds the schema, signs `signing_bytes(commit.json())` with the clone key, stores `json.dumps(commit.json())` encrypted (random IV) and content-addressed. |
| `sgit_ai/storage/Vault__Commit.py:78-103` | `load_commit`: decrypt, `json.loads`, `Schema__Object_Commit.from_json(raw)`. **Unknown keys are ignored and do not reappear in `.json()`** (tested 28 Oct with a dict-valued `user_signature`, for both commits and tags). |
| `sgit_ai/storage/Vault__Commit.py:111-128` | `verify_commit_signature`: tries `signing_bytes`, then `legacy_signing_bytes` when `author_key_id` is null. |

### 4.2 Signature checks today

| File:line | What it does |
|---|---|
| `sgit_ai/core/actions/verify/Vault__Signatures.py:28-52` | `_key_for` finds the clone key (`author_key_id`, else the branch index), fetching missing key files (`Vault__Key_Fetch`); `status_of` returns `verified` / `bad` / `unsigned` / `no-key` / `missing`. |
| `sgit_ai/core/actions/verify/Vault__Signatures.py:54-86` | `verify_chain` walks all parents. Used by `check verify`, pull (`Vault__Incoming_Check.require_signatures`, `sgit_ai/core/actions/pull/Vault__Incoming_Check.py:13-55`), clone (`Step__Clone__Verify_Signatures.py:24-70`) and push (`Vault__Sync__Push.py:208`). |

### 4.3 Tags

| File:line | What it does |
|---|---|
| `sgit_ai/schemas/Schema__Object_Tag.py` | `schema`, `name`, `commit_id`, `message`, `timestamp_ms`, `tagger_branch`, `tagger_key_id`, `signature`. |
| `sgit_ai/core/actions/tag/Vault__Sync__Tag.py:92-140` | `create` signs `_signing_bytes(tag)` with the clone key. |
| `sgit_ai/core/actions/tag/Vault__Sync__Tag.py:182-184` | `_signing_bytes` is JCS minus `signature`. |
| `sgit_ai/core/actions/tag/Vault__Sync__Tag.py:196-210` | `_status`: verified / bad / unsigned / no-key. |
| `sgit_ai/core/actions/tag/Vault__Sync__Tag.py:65-80` | `resolve` refuses an unverified tag (TM-R06). |

### 4.4 Where commits are made

| Site | Who signs today | User signature? |
|---|---|---|
| `Vault__Sync__Commit.commit` (`sgit_ai/core/actions/commit/Vault__Sync__Commit.py:162-187`) | clone key | **yes**: this covers `commit`, `--amend`, merge-resolution commits, and `history revert --as-commit` (via `Vault__Sync__History_Edit.py:105`) |
| `Vault__Sync__Commit.write_file` (`Vault__Sync__Commit.py:327-337`) | clone key | **yes** (`sgit write`) |
| `Step__Pull__Merge` merge commit (`sgit_ai/workflow/pull/Step__Pull__Merge.py:158-181`) | clone key | **yes** (pull, `branch merge`) |
| `Step__Pull__Merge` rewind re-apply (`Step__Pull__Merge.py:285-301`) | clone key | **yes** (it is the user's work re-committed) |
| `Vault__Sync.init` first commit (`sgit_ai/core/Vault__Sync.py:116-123`) | clone key | **no** (an empty `init` commit; Git signs the first commit only if asked, and the user has no way to ask here). Follows `-S` if passed to `init`? Not in v1 |
| `Vault__Ignore__Apply` (`sgit_ai/core/actions/admin/Vault__Ignore__Apply.py:75`) | clone key | **yes**, it is a user action (`vault ignore`); follows the switch |
| `Step__Move__Write_Sentinel_Commits` (`sgit_ai/workflow/move/steps/Step__Move__Write_Sentinel_Commits.py:108`) | clone key | **no** (automated, mid-workflow; D5) |
| `Vault__Pack_Convert` (`sgit_ai/core/actions/pack/Vault__Pack_Convert.py:150`) | clone key of the new vault | **no**: rewrites history; old user signatures dropped and counted (7.6) |
| `Migration__Tree_IV_Determinism._rewrite_commits` (`sgit_ai/migrations/tree_iv/Migration__Tree_IV_Determinism.py:342`) | none | **no**: same as above |

### 4.5 The cross-client rule

`tests/_fixtures/interop_vectors.json`, key `commit_signing`, states the JCS rule and gives a stored commit with its
signing bytes and signature. The web UI follows that rule. The rule text changes in 5.10.

### 4.6 Existing subprocess pattern

`sgit_ai/core/serve/Container__Command_Runner.py:10-31`: argv lists only, `capture_output`, `text=True`, timeouts
mapped to code 124, a missing binary to 127, and `# nosec B603` comments for Bandit. Signing needs bytes on
stdin/stdout, so it gets its own runner (5.5) following the same pattern.

---

## 5. Design

### 5.1 The signed bytes

There is one definition, used by both signatures (clone and user), for commits and for tags:

```
SIGNATURE_MEMBERS = ('signature', 'user_signature')            # class attribute on Vault__Commit and Vault__Sync__Tag

signing_bytes(d) = UTF-8( JCS( { k: v for k, v in d.items() if k not in SIGNATURE_MEMBERS } ) )
                 = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
```

- `d` is `commit.json()` (or `tag.json()`) of the **current** schema, which includes `author_signature: null` and
  `attestations: []` exactly as today. Removing `user_signature` makes these bytes identical to what every existing
  client computes. Existing clients never see the member, because their schema drops it (4.1).
- **Legacy form** (`author_key_id` null): `legacy_signing_bytes(d)` must also drop `user_signature` before setting
  `signature: None`. Otherwise a new client would add `"user_signature": null` to the bytes and fail every pre-0.19
  commit. This is the one easy-to-miss change.
- **Both signatures cover the same bytes.** The user signature therefore covers:
  - `tree_id` and `parents` (the content and the history);
  - `timestamp_ms`;
  - `message_enc` (the ciphertext, which AES-GCM authenticates, so it fixes the plaintext);
  - `branch_id` and `author_key_id` (it binds the clone key that co-signed).

  It does not cover the clone signature, and the clone signature does not cover it. Either can be checked alone,
  and stripping one leaves the other valid. That is what Git does with `gpgsig` and the commit.
- **For SSH**, the user signature is an SSHSIG over these bytes with namespace `git` (D1) and hash `sha512`
  (ssh-keygen's default). **For OpenPGP**, it is a binary detached signature over these bytes.

### 5.2 New types and schemas

All new files follow the existing Safe type layout. Validation is `strict_validation = True` unless noted.

| New file | Type | Definition |
|---|---|---|
| `sgit_ai/safe_types/Enum__User_Signature_Format.py` | `Enum__User_Signature_Format(str, Enum)` | `SSH = 'ssh'`, `OPENPGP = 'openpgp'` |
| `sgit_ai/safe_types/Safe_Str__User_Signature_Blob.py` | `Safe_Str__User_Signature_Blob(Safe_Str)` | regex `^[A-Za-z0-9+/]{16,8188}={0,2}$` (MATCH mode), `max_length = 8192`, `allow_empty = False`, `trim_whitespace = True`. Base64 of the **binary** signature: the SSHSIG blob (not armored), or the OpenPGP signature packet. RSA-8192 SSHSIG ≈ 2.9 KB of base64, and OpenPGP RSA-4096 ≈ 0.8 KB, so 8 KB leaves room. |
| `sgit_ai/schemas/Schema__User_Signature.py` | `Schema__User_Signature(Type_Safe)` | `format : Enum__User_Signature_Format = None`, `blob : Safe_Str__User_Signature_Blob = None` |
| `sgit_ai/schemas/Schema__Object_Commit.py` (changed) | new field | `user_signature : Schema__User_Signature = None   # the signer's own key (SSH/OpenPGP), Git's gpgsig; excluded from both signatures' signed bytes` |
| `sgit_ai/schemas/Schema__Object_Tag.py` (changed) | new field | same |
| `sgit_ai/safe_types/Enum__User_Signature_Status.py` | `Enum__User_Signature_Status(str, Enum)` | `GOOD='good'`, `UNTRUSTED='untrusted'`, `BAD='bad'`, `EXPIRED_SIGNATURE='expired-signature'`, `EXPIRED_KEY='expired-key'`, `REVOKED='revoked'`, `CANNOT_CHECK='cannot-check'`, `NONE='none'`, with `code()` → `G U B X Y R E N` |
| `sgit_ai/safe_types/Safe_Str__Signer_Principal.py` | `Safe_Str__Signer_Principal(Safe_Str)` | printable, no control characters (regex replaces `[\x00-\x1f\x7f]`), max 256. From the verifier's own file or keyring, **never stored in the vault** |
| `sgit_ai/safe_types/Safe_Str__Key_Fingerprint.py` | `Safe_Str__Key_Fingerprint(Safe_Str)` | `^(SHA256:[A-Za-z0-9+/]{43}|[0-9A-F]{40}|[0-9A-F]{64})$` (SSH SHA256, OpenPGP v4, OpenPGP v5/v6) |
| `sgit_ai/safe_types/Safe_Str__Signing_Key_Spec.py` | `Safe_Str__Signing_Key_Spec(Safe_Str)` | what `user.signingKey` holds: a path, a key id/email/fingerprint, or a literal public key. Printable, max 4096, no NUL/newline |
| `sgit_ai/schemas/Schema__User_Signature__Result.py` | `Schema__User_Signature__Result(Type_Safe)` | `status : Enum__User_Signature_Status = None`, `format : Enum__User_Signature_Format = None`, `principal : Safe_Str__Signer_Principal = None`, `key_type : Safe_Str__Key_Type = None` (`ED25519`, `ECDSA`, `RSA`, `ED25519-SK`, `ECDSA-SK`, or OpenPGP algo name), `key_fingerprint : Safe_Str__Key_Fingerprint = None`, `reason : Safe_Str__Text = None` |
| `sgit_ai/schemas/Schema__Signing_Config.py` | `Schema__Signing_Config(Type_Safe)` | `sign : bool = False`, `format : Enum__User_Signature_Format = None`, `signing_key : Safe_Str__Signing_Key_Spec = None`, `gpg_program : Safe_Str__File_Path = None`, `ssh_program : Safe_Str__File_Path = None`, `allowed_signers_file : Safe_Str__File_Path = None`, `revocation_file : Safe_Str__File_Path = None`, `default_key_command : Safe_Str__Command_Line = None`, `min_trust_level : Enum__GPG_Trust = None`, `source : Safe_Str__Text = None` (for `doctor`: where each value came from) |

**How the field is written.** `Vault__Commit.create_commit` stores
`data = commit.json(); if data.get('user_signature') is None: del data['user_signature']`, and the same for tags. So an
unsigned commit is **byte-identical** to today's format. Nothing grows and no new `null` member appears for the web UI
to meet.

### 5.3 Classes

There is a new package, `sgit_ai/crypto/signing/`. It has an `__init__.py` (source only; tests have none, per rule 8).
Everything is a `Type_Safe` class, with no module-level functions and no `@staticmethod`.

#### 5.3.1 Signing

| Class (file = class name) | Responsibility | Key methods |
|---|---|---|
| `Signing__Command_Runner` | the one place signing runs a program | `which(name) -> str`; `run(argv: list, stdin: bytes, timeout: int, env: dict) -> dict(code, out: bytes, err: bytes)`. Rules in 5.5 |
| `Git__Config__Reader` | read the user's Git config | `read() -> dict` (lower-cased keys → last value); `_read_with_git()`; `_read_files()` (fallback parser, 5.6.2) |
| `Signing__Config__Resolver` | flags > Git config → `Schema__Signing_Config` | `resolve(flags: Schema__Signing_Flags) -> Schema__Signing_Config`; `for_tags(...)` |
| `SSH__Signer` | `ssh-keygen -Y sign` | `sign(payload: bytes, config) -> Schema__User_Signature` |
| `SSH__Signer__In_Process` | signs with an **unencrypted** OpenSSH private-key file through `cryptography`, producing the same SSHSIG as `ssh-keygen` (ed25519 byte-identical, 9.3) | `sign(payload, key_path) -> Schema__User_Signature`. Used when `gpg.ssh.program` is not found and `user.signingKey` names an unencrypted private-key file (D4). Also what the unit tests sign with. |
| `GPG__Signer` | `gpg -bsu` | `sign(payload, config) -> Schema__User_Signature` |
| `User__Signer` | façade picked from the config | `from_config(config) -> User__Signer`; `sign(payload) -> Schema__User_Signature`; `describe() -> str` ("ssh key SHA256:… (user.signingKey …)") |

#### 5.3.2 Verifying

| Class (file = class name) | Responsibility | Key methods |
|---|---|---|
| `SSH__Wire` | SSH wire primitives over a bytes buffer with bounds checks | `read_uint32()`, `read_string()`, `read_mpint()`, `at_end()`; writers for the signer |
| `SSH__Sig__Blob` | parse/build SSHSIG (5.4.1) | `parse(blob: bytes) -> SSH__Sig__Blob`; fields `public_key_blob`, `namespace`, `reserved`, `hash_algorithm`, `signature_blob`; `signed_data(payload) -> bytes`; `armor() / dearmor(text)` |
| `SSH__Public_Key` | parse a wire public key and verify a signature with it | `from_wire(blob)`; `from_openssh_line(text)`; `fingerprint() -> 'SHA256:…'`; `key_type() -> str`; `verify(signature_blob, data) -> bool` (5.4.3) |
| `SSH__Allowed_Signers` | parse the allowed-signers file (5.4.4) | `load(path)`; `principals_for(public_key, namespace, at_time_s) -> list`; `matches_key_outside_window(...)` |
| `SSH__Revocation_List` | plain-key revocation file; KRL detection | `load(path)`; `is_revoked(public_key) -> bool`; `is_krl() -> bool` |
| `SSH__Sig__Verifier` | the in-process `find-principals` + `verify` + `check-novalidate` | `verify(sig: Schema__User_Signature, payload, at_time_ms, config) -> Schema__User_Signature__Result` |
| `SSH__Sig__Verifier__Keygen` | delegate to `ssh-keygen` for certificates and KRLs | same signature as above |
| `GPG__Status_Parser` | parse `[GNUPG:]` lines | `parse(stdout: bytes) -> dict` (5.7.2) |
| `GPG__Verifier` | `gpg --verify` | `verify(sig, payload, at_time_ms, config) -> Schema__User_Signature__Result` |
| `User__Signature__Verifier` | façade with cache | `verify(obj_id: str, sig, payload, at_time_ms) -> Schema__User_Signature__Result` |
| `User__Signature__Cache` | `.sg_vault/local/user-signature-cache.json` | `get(obj_id, trust_digest)`, `put(...)`; written with `Vault__Storage.write_private` (0600, atomic) |

#### 5.3.3 Vault-level

| Class (file = class name) | Responsibility | Key methods |
|---|---|---|
| `Vault__User_Signatures` (`sgit_ai/core/actions/verify/`) | per-commit / per-chain user-signature status, next to `Vault__Signatures` | `status_of(c, read_key, commit_id) -> Schema__User_Signature__Result`; `verify_chain(c, read_key, head, stop_at, limit, boundaries) -> dict(user_counts, user_by_status)` |
| `CLI__Argv__Signing` (`sgit_ai/cli/`) | 3.3's argv normalisation | `normalise(argv: list) -> list` |

### 5.4 SSH: exact formats and the in-process verifier

#### 5.4.1 SSHSIG layout (OpenSSH `PROTOCOL.sshsig`)

**Blob** (what we store, base64 in `blob`):

```
byte[6]  MAGIC_PREAMBLE  "SSHSIG"
uint32   SIG_VERSION     0x00000001
string   publickey       (wire-encoded public key; for certificates, the certificate)
string   namespace       "git"
string   reserved        ""   (verifiers ignore its content)
string   hash_algorithm  "sha512" | "sha256"
string   signature       (an SSH signature: string algorithm, then the algorithm's blob)
```

**Signed data** (what the key actually signs):

```
byte[6]  MAGIC_PREAMBLE  "SSHSIG"
string   namespace
string   reserved
string   hash_algorithm
string   H(message)       SHA-512 or SHA-256 of signing_bytes (5.1)
```

**Armor** (only for display and for `ssh-keygen`):
`-----BEGIN SSH SIGNATURE-----`, base64 wrapped at 70 columns, `-----END SSH SIGNATURE-----`.

**Parser rules** (every one of these has a test):

- the whole blob ≤ 6144 bytes after base64 decoding;
- every string length ≤ the remaining bytes;
- no trailing bytes;
- magic exact;
- version == 1;
- namespace == the configured namespace (`git`, D1);
- hash in {sha256, sha512};
- the signature algorithm must agree with the key type: `ssh-ed25519` ↔ `ssh-ed25519`; `ecdsa-sha2-nistpN` ↔ the same;
  RSA keys only with `rsa-sha2-256` / `rsa-sha2-512` (**`ssh-rsa` / SHA-1 is rejected**, as `ssh-keygen` does);
  sk types ↔ the same.

#### 5.4.2 Fingerprints and display

- The fingerprint is `SHA256:` + base64 (no padding) of SHA-256 over the wire public-key blob, exactly as
  `ssh-keygen -l` prints it.
- The key type name for display follows `ssh-keygen`: `ED25519`, `ECDSA`, `RSA`, `ED25519-SK`, `ECDSA-SK`.

#### 5.4.3 Key types verifiable in-process with `cryptography` 49.0 (installed)

| SSH key type | How | In-process? |
|---|---|---|
| `ssh-ed25519` | `Ed25519PublicKey.from_public_bytes(pk32).verify(sig64, signed_data)` | yes |
| `ecdsa-sha2-nistp256/384/521` | public point → `EllipticCurvePublicNumbers`. The signature blob is `mpint r, mpint s` → `utils.encode_dss_signature(r, s)`; verify with SHA-256/384/512 respectively | yes |
| `ssh-rsa` key, `rsa-sha2-256/512` signature | `RSAPublicNumbers(e, n)`; `PKCS1v15` with SHA-256/512 | yes |
| `sk-ssh-ed25519@openssh.com` | key: `string pk32, string application`. Signature: `string sig64, byte flags, uint32 counter`. Signed message = `SHA256(application) ‖ flags ‖ counter ‖ SHA256(signed_data)` (OpenSSH `PROTOCOL.u2f`). Ed25519 verify over that | yes (parsed by `SSH__Public_Key`, not by `load_ssh_public_key`) |
| `sk-ecdsa-sha2-nistp256@openssh.com` | key: `string curve, string Q, string application`. Signature: `string ecdsa_sig(mpint r, mpint s), byte flags, uint32 counter`; same message construction; ECDSA-SHA256 | yes |
| `*-cert-v01@openssh.com` (certificates) | needs the CA in a `cert-authority` line | **delegated** to `ssh-keygen` (5.4.5) |
| `ssh-dss` | OpenSSH no longer signs with DSA | rejected |

**sk flags:** user-presence bit `0x01` is required unless the matching allowed-signers line has `no-touch-required`.
Verify-required (`0x04`) is required when the line has `verify-required`. These are the same rules `ssh-keygen`
applies.

#### 5.4.4 The allowed-signers file

Format from `ssh-keygen(1)`, ALLOWED SIGNERS section: one entry per line,
`principals [options] keytype base64-key [comment]`. `#` starts a comment and blank lines are ignored.

- **Principals:** comma-separated patterns. `*` and `?` are wildcards, and a leading `!` negates (`match_pattern_list`
  semantics). A principal matches if it matches at least one positive pattern and no negated one.
- **Options handled in-process:**
  - `namespaces="git,file"`: the configured namespace must be in the list;
  - `valid-after="YYYYMMDD[HHMM[SS]][Z]"`, `valid-before="…"`: local time unless `Z`; compared with the commit's
    `timestamp_ms` (5.4.6);
  - `no-touch-required`, `verify-required`.
- **Option that forces delegation:** `cert-authority` (5.4.5).
- **`principals_for(key, ns, t)`** returns, in file order, every line whose key equals the signature's public key and
  whose namespace and validity allow it. When there is more than one, the first principal is shown and the rest are
  listed in `--json`.

**The three outcomes, as Git produces them:**

| Case | Status | Shown |
|---|---|---|
| A line matches (key, namespace, validity) and the signature verifies | `good` | `Good "git" signature for <principal> …` |
| The signature verifies but no line matches the key (or there is no file) | `untrusted` (`U`, Git's `check-novalidate` path) | `Good "git" signature with <TYPE> key <fp>` / `No principal matched.` |
| A line matches the key but `valid-after`/`valid-before` exclude the commit time | `expired-key` | with the reason `key not valid at the commit time (valid-before 20261001)` |
| The key is in the revocation file | `revoked` | |
| The signature does not verify, or there is a namespace mismatch | `bad` | |
| A key type or a line that needs delegation, with no `ssh-keygen` installed | `cannot-check` | the reason names the missing program |

How Git's exact behaviour on `valid-before` is reported is not fully pinned down here. `ssh-keygen -Y verify` fails,
and Git then falls back to `check-novalidate`. The xver run (9.5) records what Git 2.43 prints, and the label is
aligned to it before release.

#### 5.4.5 Delegation to ssh-keygen

`SSH__Sig__Verifier__Keygen` is used only when one of these holds:

1. the signature's public key is a certificate;
2. the allowed-signers file has a `cert-authority` line;
3. the revocation file is a binary KRL (magic `SSHKRL\n\0`).

It reproduces Git's calls exactly:

```
ssh-keygen -Y find-principals -f <allowed> -s <sigfile> [-Overify-time=<YYYYMMDDHHMMSS>]
ssh-keygen -Y verify -n git -f <allowed> -I <principal> -s <sigfile> [-r <revocation>] [-Overify-time=…]   (payload on stdin)
ssh-keygen -Y check-novalidate -n git -s <sigfile>                                                         (payload on stdin)
```

- `<sigfile>` is the armored signature written to `.sg_vault/local/tmp/sig-<random>.sig` (0600) and removed in a
  `finally`. The payload is ciphertext-derived JSON, but it still goes on stdin, not to disk.
- Without `ssh-keygen`, the result is `cannot-check`, never `good`.

#### 5.4.6 Time

Commit time is `timestamp_ms`, chosen by the committer (as Git's committer date is). `valid-after`/`valid-before`
are checked against it, exactly as Git passes `-Overify-time=<committer date>`. 6.5 covers what that does and does
not prove.

### 5.5 Running ssh-keygen and gpg

`Signing__Command_Runner.run(argv, stdin, timeout, env)`:

- **Process:** `subprocess.run(argv_list, input=stdin_bytes, capture_output=True, timeout=…, env=env, cwd=<a safe
  dir>, close_fds=True)`. Never `shell=True`. argv is built from config values as separate list items; nothing is
  joined into a string.
- **Program:** resolved with `shutil.which` (config value first, then the default name). A config value that is a
  path is used as is. Not found → `code=127`.
- **cwd:** the user's home directory, never the vault working copy. Neither program reads per-directory config, but
  this removes any chance that a file in the vault is picked up.
- **Environment:**
  - **inherited:** `SSH_AUTH_SOCK` (agent), `GNUPGHOME`, `GPG_TTY`, `DISPLAY`/`WAYLAND_DISPLAY` and `SSH_ASKPASS`
    (pinentry and askpass), `HOME`, `PATH`;
  - **added:** `LC_ALL=C`, so messages are stable for the error text; the gpg status lines do not depend on locale
    anyway.
- **Timeouts:**
  - signing **120 s** (a passphrase prompt or a hardware-key touch can take a while);
  - verifying with `gpg` **30 s**;
  - `git config` **10 s**;
  - `gpg.ssh.defaultKeyCommand` **10 s**.

  A timeout is a failure with its own message.
- **stdin** is the payload, so passphrase prompts go to `/dev/tty` (ssh-keygen) or to pinentry (gpg), exactly as
  with Git. With no TTY and no agent, signing fails, and the command fails closed (3.5).
- **Signing argv:**

  | Case | argv |
  |---|---|
  | SSH, key is a private-key path | `[ssh_program, '-Y', 'sign', '-n', 'git', '-f', <path>]`, stdout = armored SSHSIG |
  | SSH, key is a `.pub` path | same; `ssh-keygen` finds the private half in the agent |
  | SSH, literal key (`key::ssh-…` or `ssh-…`) | write the literal to `.sg_vault/local/tmp/signing-<random>.pub` (0600) and pass `-f <that> -U`. `-U` exists from OpenSSH 8.9; on an older ssh-keygen the call fails and the error names the version |
  | SSH, no key but `gpg.ssh.defaultKeyCommand` set | run it (`shlex.split`, never a shell; Git runs it through a shell, a documented difference), take the first line of output starting `ssh-` or `key::`, then as the literal case |
  | GPG | `[gpg_program, '--status-fd=2', '-bsu', <key>]`, stdout = binary signature. Success requires `[GNUPG:] SIG_CREATED ` in stderr's status lines and exit 0 |

- **Output checks:**
  - SSH: dearmor, then `SSH__Sig__Blob.parse`, and the signer verifies its own output in-process before returning
    (this catches a misconfigured program).
  - GPG: the output must start with an OpenPGP signature packet tag (`0x88`/`0x89`/`0xC2`), with length within the
    8 KB cap.

### 5.6 Configuration resolution

#### 5.6.1 Order (first set wins per key)

1. **Command flags:** `-S` / `--gpg-sign[=KEY]` / `--no-gpg-sign`; for tags `-s` / `-u KEY` / `--no-sign`. A key
   given here also turns signing on (Git: `-S<key>`).
2. **The user's Git config, global then system** (5.6.2): `sgit.gpgSign` for the on/off switch; `user.signingKey`,
   `gpg.*` for how.
3. **Defaults:** signing off; format `openpgp` (Git's default) **unless** `user.signingKey` looks like an SSH key
   (a literal `ssh-` or `key::`, or a path ending `.pub` or to an OpenSSH private key). Git requires
   `gpg.format = ssh` for that; inferring it is a convenience, not a contradiction, because Git would fail on that
   key with `openpgp`. Flag D3b.

Repository-level Git config (`.git/config` of a repository the vault happens to sit in) is **not** read (D3). Vault
content is never read for signing settings: no file in the working copy or the vault can change how or whether sgit
signs (6.4).

#### 5.6.2 Reading Git's config

`Git__Config__Reader._read_with_git()` runs these when `git` is on `PATH`:

```
git config --global --includes --null --list
git config --system --includes --null --list
```

Both run in the home directory, with Git's own environment honoured (`GIT_CONFIG_GLOBAL`, `GIT_CONFIG_SYSTEM`,
`GIT_CONFIG_NOSYSTEM`, `XDG_CONFIG_HOME`). The output is NUL-separated `key\nvalue` records. Global overrides system,
and within a file the last value wins.

When `git` is not installed, `_read_files()` falls back to a small INI reader:

- **Files:** `$GIT_CONFIG_GLOBAL`, else `$XDG_CONFIG_HOME/git/config` then `~/.gitconfig`.
- **Supported:** sections, subsections, `key = value`, quoting, `\` escapes, booleans (`true/yes/on/1`).
- **Not supported:** `include`/`includeIf` (a warning names them).

The result is cached for the process, and `sgit doctor` gains a "Signing" block showing each value and its source.

### 5.7 OpenPGP specifics

#### 5.7.1 Verify call (Git's)

```
gpg --keyid-format=long --status-fd=1 --verify <sigfile> -
```

The payload goes on stdin. `<sigfile>` is the binary signature in `.sg_vault/local/tmp/` (0600, removed in
`finally`).

#### 5.7.2 Status parsing (`GPG__Status_Parser`, as Git's `gpg-interface.c`)

Only lines starting exactly with `[GNUPG:] ` on the status fd are read. gpg escapes newlines in user ids, so a user id
cannot inject a status line. Nothing else is read.

| Status | Result |
|---|---|
| `GOODSIG <keyid> <uid>` | candidate good |
| `BADSIG` | `bad` |
| `ERRSIG` | `cannot-check` (reason: missing public key, unsupported algorithm) |
| `EXPSIG` | `expired-signature` |
| `EXPKEYSIG` | `expired-key` |
| `REVKEYSIG` | `revoked` |
| `VALIDSIG <fpr> …` | fingerprint (`key_fingerprint`), primary fingerprint as the last field |
| `TRUST_UNDEFINED` / `TRUST_NEVER` | `untrusted` (`U`) |
| `TRUST_MARGINAL` / `TRUST_FULLY` / `TRUST_ULTIMATE` | `good` (`G`), subject to 5.7.3 |
| The principal | the `<uid>` from `GOODSIG`, unescaped (`%XX`), control characters removed |

#### 5.7.3 `gpg.minTrustLevel`

`undefined | never | marginal | fully | ultimate`. A good signature below it becomes `untrusted`. Unset, Git treats
`marginal` and above as `G` and lower as `U`; same here.

### 5.8 File-by-file changes

**Core changes:**

| File | Change |
|---|---|
| `sgit_ai/schemas/Schema__Object_Commit.py` | add `user_signature` (5.2) |
| `sgit_ai/schemas/Schema__Object_Tag.py` | add `user_signature` |
| `sgit_ai/storage/Vault__Commit.py` | `SIGNATURE_MEMBERS`; `signing_bytes` and `legacy_signing_bytes` drop `user_signature`; `create_commit(..., user_signer: User__Signer = None)` signs with the user key first (if given), then the clone key, over the same bytes. Serialisation drops a `None` `user_signature`. If the user signer raises, `create_commit` raises before storing anything |
| `sgit_ai/core/actions/tag/Vault__Sync__Tag.py` | `_signing_bytes` drops `user_signature`; `create(..., user_signer=None)`; `_describe` adds `user_signature` (result dict) |
| `sgit_ai/core/actions/verify/Vault__User_Signatures.py` | new (5.3.3) |
| `sgit_ai/core/Vault__Sync.py` | `verify_signatures(...)` also returns `user_counts` / `user_by_status` (computed in the same walk, from commits already loaded) |

**Commit sites:**

| File | Change |
|---|---|
| `sgit_ai/core/actions/commit/Vault__Sync__Commit.py` | `commit(...)` and `write_file(...)` take `signing: Schema__Signing_Flags = None`, resolve a `User__Signer`, and pass it to `create_commit`. The ref is written only after a successful store (already so) |
| `sgit_ai/workflow/pull/Step__Pull__Merge.py` | the merge commit and the rewind re-apply commit take the signer from the workflow input (`Schema__Pull__State` gains `signing : Schema__Signing_Flags = None`) |
| `sgit_ai/core/actions/history/Vault__Sync__History_Edit.py` | `revert_commit(..., signing=None)` passes it to `commit()` |
| `sgit_ai/core/actions/admin/Vault__Ignore__Apply.py` | passes the resolved signer (follows `sgit.gpgSign`) |
| `sgit_ai/core/actions/pack/Vault__Pack_Convert.py`, `sgit_ai/migrations/tree_iv/Migration__Tree_IV_Determinism.py` | count the source commits that had a `user_signature` and report `user_signatures_dropped` in their result dicts (7.6) |

**Other new classes:**

| File | Change |
|---|---|
| `sgit_ai/crypto/signing/*.py` | new (5.3) |
| `sgit_ai/schemas/Schema__Signing_Flags.py` | new: `sign : Enum__Sign_Choice = None` (`ON`/`OFF`/unset), `key : Safe_Str__Signing_Key_Spec = None` |

**CLI:**

| File | Change |
|---|---|
| `sgit_ai/cli/CLI__Argv__Signing.py` | new (3.3) |
| `sgit_ai/cli/CLI__Main.py` | `run()` calls `CLI__Argv__Signing().normalise(argv)`; commit/write/pull parsers get the flags (`:374-388` and the write/pull parsers); output line "Signed with …" |
| `sgit_ai/plugins/history/CLI__History.py` | `log` and `show` get `--show-signature` (`:76-105`) |
| `sgit_ai/plugins/check/CLI__Check.py` | `verify` gets `--user`, `--require-user-signature`, `--json` (`:23-27`) |
| `sgit_ai/cli/CLI__Vault.py` | `cmd_check_verify` (`:1832-1852`) prints the user line, exit codes per 3.5, JSON; `_print_log` (`:2274-2317`) passes `show_signature` to the inspector |
| `sgit_ai/cli/CLI__Tag.py` | `create` gets `-s/--sign`, `-u/--local-user`, `--no-sign` (`:41-47`); `show` prints "Signed by" |
| `sgit_ai/objects/Vault__Inspector.py` | `inspect_commit_chain` / `inspect_commit_dag` (`:97`, `:319`) carry `user_signature` (raw schema) per commit; `format_commit_log` (`:366-420`) prints the Git-worded lines when `show_signature`; `--json` includes the result object |
| `sgit_ai/cli/CLI__Doctor*` (where `doctor` lives) | a "Signing" block (5.6.2) |

### 5.9 Compatibility: why no gate is needed

#### 5.9.1 Clients from before this change

- **They read a signed commit without error.** `from_json` ignores the unknown member (tested on the current
  `osbot-utils`; 9.5 runs released builds).
- **Their clone-signature check still passes.** They compute `signing_bytes(commit.json())` from their schema, which
  has no `user_signature`. The new client computes the same bytes because it removes `user_signature` (5.1). The
  bytes are equal, so verification succeeds.
- **They never write the member back.** Commits and tags are immutable content-addressed objects, and no client
  re-serialises an existing one. The only rewriters (pack convert, migrate, move sentinels) make *new* commits; old
  clients would simply not carry the member, and new ones deliberately do not (7.6).
- **Their `signatures-required` checks see no change,** because that policy is about the clone signature.

#### 5.9.2 New clients reading old commits

`user_signature` is absent, so the status is `none`. `signing_bytes` and `legacy_signing_bytes` are unchanged for
these commits, because removing an absent or null member changes nothing. The legacy path needs the explicit removal
in 5.1, and a test pins it.

#### 5.9.3 Unsigned commits

They are byte-identical to today's (the member is not written when `None`).

#### 5.9.4 Two things to confirm before release

1. **The web UI.** If the web UI computes the clone signing bytes from the **raw stored JSON** rather than from its
   own schema, it will now include `user_signature` and report a bad signature on user-signed commits. Its rule must
   become "remove `signature` and `user_signature`". The interop vector (5.10) makes that testable for them. Until
   they confirm, a user-signed commit may show as bad in the web UI. Unsigned commits are unaffected. (D7)
2. **The oldest sgit still in use.** The xver run (9.5) must show that released builds (0.19.0, 0.21.0, 0.24.0,
   0.26.0) ignore the unknown member.
   - **Fallback if any of them rejects it:** sign only in vaults whose `min_client` is at or above the oldest build
     that tolerates it, and say so by name.
   - **Why this is not a gate:** it is a refusal to sign, not a format change.

### 5.10 Interop vectors to add (`tests/_fixtures/interop_vectors.json`)

**New key `commit_user_signing`:**

- **`rule`:** "signing bytes for BOTH signatures = JCS of the stored commit JSON with `signature` AND `user_signature`
  removed; `user_signature` = {format, blob}, blob = base64 of the binary SSHSIG (namespace `git`, hash `sha512`) or
  binary OpenPGP signature".
- **A fixed ed25519 OpenSSH test key:** private key in OpenSSH format, unencrypted, test-only, plus the public line.
- **`stored_commit_json`:** with both `signature` (the existing P-256 test key) and `user_signature` (ed25519
  SSHSIG; ed25519 is deterministic, so the blob is reproducible).
- **`signing_bytes_utf8`:** the expected bytes.
- **`sshsig_signed_data_hex`:** the SSHSIG signed-data structure for those bytes.
- **`armored`:** the same signature armored, for `ssh-keygen -Y verify` outside sgit.
- **`allowed_signers_line`:** `test@example.com namespaces="git" ssh-ed25519 AAAA…`.

**Changed:** the existing `commit_signing.rule` text gains "and `user_signature`". Its bytes are unchanged, because
that commit has no user signature.

**OpenPGP:** no vector, because the signature is not deterministic. Covered by real-gpg tests (9.4).

---

## 6. Security and threat model

### 6.1 What TM-R01 becomes

TM-R01 is the attack where any read-key holder with store write access mints a clone key and authors commits that
`check verify` calls *verified*. After this change:

- **For a verifier with an allowed-signers file (or a GPG keyring with trust):** a commit is attributable to a
  principal only if it carries a `good` user signature. The forger cannot produce one without that principal's
  private key. Its commits show `none` or `untrusted`, and `check verify --require-user-signature` fails on them.
  That is exactly Git's guarantee.
- **At vault level, nothing changes:** the vault does not require user signatures, and two verifiers with different
  files can disagree. That is by design (Git parity). Vault-level enforcement belongs to SGitHub.
- **Threat model text:** TM-R01's row gains "closed per verifier for commits carrying a user signature (design 02);
  vault-level enforcement: SGitHub".

### 6.2 Key material never enters the vault

- sgit never reads a private key, with one exception: `SSH__Signer__In_Process` reads an **unencrypted** OpenSSH
  key file that `user.signingKey` explicitly names, when `ssh-keygen` is absent (D4). It reads it in memory, never
  copies it, never logs it, and never caches it.
- Signing otherwise happens inside `ssh-keygen` or `gpg`, which talk to their agents.
- What the vault stores is the signature, whose SSHSIG form includes the **public** key, plus nothing else.
- **Suggested follow-up (small, separate):** extend the existing secret guard to refuse committing OpenSSH or OpenPGP
  **private** key files. Detect `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----BEGIN PGP PRIVATE KEY BLOCK-----`,
  with the existing `--allow-secret-file` override (D11).

### 6.3 What vault readers and the host learn

| Who | What they learn |
|---|---|
| Read-key holders | The signer's public key and, through their own allowed-signers file, possibly an identity. The same as Git, where a signed commit names its key. |
| The host (TM-R08) | It sees ciphertext only, but a signed commit is larger: SSH ed25519 ≈ +300 bytes, RSA-4096 ≈ +1.5 KB, OpenPGP ≈ +0.5–1 KB. So the host can tell which commits carry a user signature and roughly what key type. New row TM-R44. |

### 6.4 Subprocesses (TM-R45)

- **Which programs run:** they come from the user's global or system Git config, as with Git. **Vault content can
  never name a program**:
  - nothing is read from the working copy;
  - repository-level Git config is not read (D3);
  - vault content cannot plant `.git/*` anyway (TM-F03).
- **How they run:**
  - argv lists, no shell;
  - cwd is home;
  - stdin carries the payload;
  - timeouts are bounded;
  - output is bounded by the cap;
  - temporary files are 0600 under `.sg_vault/local/tmp/` and removed in `finally`.
- **`gpg.ssh.defaultKeyCommand`:** Git runs it through a shell; sgit splits it with `shlex` instead, so shell syntax
  in it is not interpreted. This is a documented difference.
- **Residual:** someone who controls the user's Git config already controls what Git runs. Accepted, the same as Git.

### 6.5 Principals and time

| Concern | Detail |
|---|---|
| **Principal spoofing (TM-R46)** | The principal shown comes only from the verifier's own allowed-signers file (or gpg's uid on `GOODSIG`). The commit never supplies it. Control characters are removed before display (`Safe_Str__Signer_Principal`), so a crafted uid cannot forge output lines. |
| **Namespace and cross-protocol replay (D1)** | Signatures use namespace `git` so existing `namespaces="git"` lines work, which GitHub's own instructions produce. An sgit payload is a JSON object starting with `{`; a Git commit payload starts with `tree ` and a Git tag payload with `object `. A signature made for one cannot verify as the other, because the bytes differ. |
| **Replay onto another sgit object** | The signed bytes contain `tree_id`, `parents`, `timestamp_ms`, `message_enc` (ciphertext), `branch_id` and `author_key_id`, and for tags the name and the commit. A signature cannot be moved to a different commit or tag: any other commit has different bytes. Copying the whole commit object is copying the commit itself. In another vault it does not decrypt (different read key), and after `rekey` or pack convert the bytes change. |
| **Timestamps (TM-R47)** | `valid-after`/`valid-before` and GPG key expiry are judged against `timestamp_ms`, which the signer chooses. A holder of a key that has since expired can backdate a commit into the window. This is exactly Git's situation (it passes the committer date). Revocation (`gpg.ssh.revocationFile`, gpg revocation) does not depend on time and catches a known-compromised key. Accepted. |
| **Stripping** | A read-key holder with write access can make a *new* commit without the user signature. It has a different id, so descendants do not point at it unless history is rewritten, which the rewind guard reports (TM-F12/R05). The original signed commit cannot be altered: AES-GCM plus the content address. |
| **Downgrade** | `--require-user-signature` treats `none` as failure, so a gate cannot be passed by omitting the signature. |
| **Parser hardening** | 5.4.1 rules. GPG status lines are read only by exact prefix. Blob size is capped by the Safe type (8 KB of base64) before anything is parsed. |

### 6.6 New threat-model rows

| ID | Row (short) | Kind |
|---|---|---|
| TM-R44 | A user signature enlarges the commit ciphertext: the host learns which commits are user-signed and roughly the key type | accepted, metadata (extends TM-R08) |
| TM-R45 | Signing and GPG verification run programs named by the user's global/system Git config; never by vault content or repository config | accepted, Git parity; `Fixed`-style tests that vault content cannot influence argv |
| TM-R46 | Trust in a user signature is the verifier's own file or keyring; the vault carries none, and verifiers may disagree; the principal is never taken from the commit | accepted by design; SGitHub later |
| TM-R47 | Key validity windows and expiry are judged at the self-asserted commit time | accepted, Git parity |
| TM-R01 (edit) | closed per verifier for user-signed commits | edit |

---

## 7. Interactions

| # | Area | Behaviour |
|---|---|---|
| 7.1 | `commit --amend` | A new commit, so it is re-signed if signing is on, as Git does. The old commit's user signature is not carried, because its bytes differ. |
| 7.2 | Merges (pull, `branch merge`) | The merge commit is user-signed when signing is on (Git's `merge -S`, `pull -S`). The rewind re-apply commit (`Step__Pull__Merge.py:285-301`) is the clone's own work re-committed, so it is user-signed under the same switch. A signing failure aborts the merge before the ref moves, leaving the merge state as on conflict. Message: "the merge is staged; run `sgit commit` to sign and finish, or `sgit merge-abort`". |
| 7.3 | `history revert --as-commit` | Through `commit()`, so signed by the same rule. A failed signature already restores the working copy (`Vault__Sync__History_Edit.py:106-109`). |
| 7.4 | `history undo` / `history reset` | No new commits, nothing to sign. |
| 7.5 | `vault move` | The sentinel commits are not user-signed (D5). Commits carried into the new vault are re-encrypted and get new bytes, so their user signatures cannot survive. Move reports `user_signatures_dropped`, as 7.6. |
| 7.6 | Pack import/export, `migrate` | History is rewritten, so every `user_signature` is dropped. The result dict and CLI output report "N user signature(s) dropped: history was rewritten (re-sign by recommitting, as with git filter-repo)". No refusal, because the rewrite is an explicit owner action (D10). |
| 7.7 | `vault rekey` | A new vault whose first commit is made by `rekey commit` through the commit path, so it is signed if the switch is on. The old history is not carried (as today). |
| 7.8 | Read-only clones | Verification works: it needs only the read key and local trust. They cannot commit, so nothing is signed. |
| 7.9 | Shallow and scoped clones | Verification covers the commits the clone has and stops at shallow boundaries, as `verify_chain` already does. Signing is unaffected, because the signed bytes are commit-level. |
| 7.10 | `signatures-required` | Unchanged, clone signatures only. No `user-signatures-required` feature (non-goal). Clone (`Step__Clone__Verify_Signatures`) and pull (`Vault__Incoming_Check`) do not look at user signatures. They would need local trust input, and Git's clone and pull do not check signatures by default either (`merge.verifySignatures` exists; a later opt-in `sgit.verifySignatures` could add it). |
| 7.11 | Pack index headers | Not user-signed. An index is a plan anchored to its commit (TM-R42), the commit carries the user signature, and the reader already refuses an index whose anchor does not match. A user prompt per index write would add friction and no assurance. |
| 7.12 | Tags | `vault tag create -s`. `resolve` (TM-R06) still requires the clone signature to be `verified`, and does not require a user signature (Git's `tag` resolution does not verify either). `vault tag show` exits 1 on a `bad` user signature. |
| 7.13 | `history log --author` | Unchanged by default. With `--show-signature`, `--author` also matches the principal of a `good` user signature (D12). |
| 7.14 | `dev dump`, `history show --json` | Include the result object. `dev dump` shows `user_signature.format` and blob length only, never the blob. |
| 7.15 | Web UI | See 5.9.4 and D7. |

---

## 8. Performance

| Operation | Expected cost | Notes |
|---|---|---|
| Sign with `ssh-keygen` (agent, ed25519) | 5–15 ms process start + agent round trip | once per commit; invisible next to tree building |
| Sign with `gpg` (agent) | 20–60 ms | once per commit |
| Sign in-process (ed25519 file) | < 1 ms | |
| Verify SSH in-process | ~0.1 ms (ed25519), ~0.3 ms (P-256), ~0.1 ms (RSA-4096 verify) + SHA-512 of ~600 bytes | `check verify` on 10,000 commits: about 1–2 s on top of the existing walk |
| Verify GPG | 15–40 ms per commit (one `gpg` process each) | 10,000 commits ≈ 3–7 min, so the cache matters (below) |
| Verify through `ssh-keygen` (delegated cases only) | 2–3 processes per commit, ~20–40 ms | rare: certificates and KRLs |
| `git config` read | 2 processes, ~5–10 ms total | once per sgit process, cached |

**The cache** (`User__Signature__Cache`, `.sg_vault/local/user-signature-cache.json`, 0600):

- **Key:** the commit or tag object id. It is a content address over the ciphertext that contains the signature, so
  it fixes both payload and signature.
- **Value:** the `Schema__User_Signature__Result` plus a `trust_digest`. For SSH, the digest is SHA-256 over the
  allowed-signers bytes, the revocation-file bytes, the namespace and the verifier version. For GPG, it is SHA-256
  over the size and mtime of `pubring.kbx`/`pubring.gpg` and `trustdb.gpg` in `GNUPGHOME`, plus `gpg.minTrustLevel`.
- **Invalidation:** an entry is used only when its digest equals the current one. Editing the allowed-signers file or
  the keyring invalidates everything at once.
- **Scope:** `check verify` and `history log --show-signature` use the cache; signing does not.
- **Size:** bounded at 200,000 entries. Oldest first out; the file is rewritten atomically.

---

## 9. Test plan

All tests use real objects: real `cryptography` keys, real `gpg` where present, real `git` for config. **No mocks.**
No `__init__.py` under `tests/`.

### 9.1 Unit: formats (`tests/unit/crypto/signing/`)

| File | Class | Cases |
|---|---|---|
| `test_SSH__Wire.py` | `Test_SSH__Wire` | uint32/string/mpint round trips; a string length past the end raises; negative mpint rejected for r/s; trailing bytes detected |
| `test_SSH__Sig__Blob.py` | `Test_SSH__Sig__Blob` | parse the interop vector; armor/dearmor round trip (70-column wrap); wrong magic, version 2, namespace `file`, hash `md5`, oversized blob, trailing byte → each rejected with its own message; `signed_data` equals the vector hex |
| `test_SSH__Public_Key.py` | `Test_SSH__Public_Key` | ed25519, nistp256/384/521, RSA 2048/4096 from generated keys (wire + OpenSSH line); fingerprints equal `cryptography`'s OpenSSH serialisation hashed as `ssh-keygen -l` does (vector); sk-ed25519 and sk-ecdsa parsed from fixed wire bytes; `ssh-dss` rejected |
| `test_SSH__Sig__Verifier.py` | `Test_SSH__Sig__Verifier` | signatures from `SSH__Signer__In_Process` for every non-sk type verify; one flipped payload byte → `bad`; one flipped signature byte → `bad`; `ssh-rsa` (SHA-1) signature built by hand → `bad`; algorithm/key mismatch → `bad`; sk-ed25519 and sk-ecdsa signatures built in-test (key generated with `cryptography`, authenticator data assembled per `PROTOCOL.u2f`) verify; with the presence flag clear → `bad`, unless the line has `no-touch-required` → `good` |
| `test_SSH__Allowed_Signers.py` | `Test_SSH__Allowed_Signers` | principal patterns (`*`, `?`, `!` negation, comma lists); `namespaces="git"` / `"file"`; `valid-after`/`valid-before` with and without `Z`, date-only and full forms; comments and blank lines; a quoted option with a comma; two lines with the same key, so two principals; `cert-authority` detected as delegation |
| `test_SSH__Revocation_List.py` | `Test_SSH__Revocation_List` | plain public-key lines; KRL magic detected |
| `test_GPG__Status_Parser.py` | `Test_GPG__Status_Parser` | real status transcripts captured from gpg 2.x (fixtures) for every row of 5.7.2; a uid containing `%0A[GNUPG:] GOODSIG` stays one uid; non-`[GNUPG:]` lines ignored |
| `test_Git__Config__Reader.py` | `Test_Git__Config__Reader` | with real `git` and `GIT_CONFIG_GLOBAL=<tmp file>` and `GIT_CONFIG_NOSYSTEM=1`: values, last-wins, booleans, `include.path`; the fallback parser on the same file (git hidden by an empty `PATH` dir) gives the same values except includes, with a warning |
| `test_Signing__Config__Resolver.py` | `Test_Signing__Config__Resolver` | flag beats config; `-S<key>` turns signing on; `--no-gpg-sign` beats `sgit.gpgSign`; `commit.gpgSign=true` alone does **not** sign (D2); format inference from key spec; `x509` refused by name |
| `test_CLI__Argv__Signing.py` | `Test_CLI__Argv__Signing` | `-S msg` keeps `msg` as the message; `-Skey`, `--gpg-sign=key`; tokens after `--` untouched; other commands untouched |

### 9.2 Unit: schema, bytes and compatibility (`tests/unit/storage/`, `tests/unit/schemas/`)

| File | Class | Cases |
|---|---|---|
| `test_Schema__User_Signature.py` | `Test_Schema__User_Signature` | round trip (`from_json(obj.json()).json() == obj.json()`); blob regex and 8 KB cap |
| `test_Vault__Commit__User_Signature.py` | `Test_Vault__Commit__User_Signature` | `signing_bytes` with and without `user_signature` are equal; `legacy_signing_bytes` likewise (**pins 5.1's legacy fix**); an unsigned commit's stored JSON has no `user_signature` key and equals the pre-change bytes for the same inputs; a signed commit verifies its clone signature, its user signature, and both independently; a user-signer that raises leaves no object in the store |
| `test_Vault__Commit__Old_Client_Compat.py` | `Test_Vault__Commit__Old_Client_Compat` | `tests/_fixtures/schemas_v0_26_0/Schema__Object_Commit.py` is a frozen copy taken from `git show v0.26.0:…`, loaded by path in the test. Cases: it parses a user-signed commit; its `json()` lacks the member; `signing_bytes` over its `json()` verifies the clone signature. Same for tags. |
| `test_Interop__Vectors.py` (extended) | existing class | the new `commit_user_signing` vector: bytes, SSHSIG signed data, blob, verify; the in-process signer reproduces the ed25519 blob byte for byte |

### 9.3 SSH without `ssh-keygen` in this container

- **Signing:** `SSH__Signer__In_Process` signs with real keys generated by `cryptography`. Ed25519 is deterministic,
  so it is checked byte for byte against the vector.
- **Cross-check with OpenSSH:** the interop vector's armored signature is produced **once with real `ssh-keygen`** on
  a machine that has it, and committed. The in-process verifier must accept it, and the in-process signer must
  reproduce it exactly (ed25519). This proves byte-compatibility without `ssh-keygen` at test time.
- **Integration** (`tests/integration/test_User_Signing__SSH_Keygen.py`, class `Test_User_Signing__SSH_Keygen`):
  real `ssh-keygen` sign and verify, `-Y verify` of an sgit signature outside sgit, delegation for a `cert-authority`
  line with a real CA and certificate, a KRL. **Skipped** when `shutil.which('ssh-keygen')` is empty. That is a
  missing-binary skip, not a mock. The CI integration job installs `openssh-client` so it runs there.

### 9.4 GPG (installed here)

`tests/unit/crypto/signing/test_GPG__Signer_Verifier.py`, class `Test_GPG__Signer_Verifier`:

- **Setup:** a temporary `GNUPGHOME` (0700), with a key made by
  `gpg --batch --pinentry-mode loopback --passphrase '' --quick-gen-key 'Test <t@example.com>' ed25519 sign never`
  (about 1 s, once per worker).
- **Cases:**
  - sign, then verify → `untrusted` (trust undefined);
  - `--quick-set-ownertrust` / `--import-ownertrust` ultimate → `good`;
  - `gpg.minTrustLevel=ultimate` with marginal trust → `untrusted`;
  - payload altered → `bad`;
  - the key removed from the keyring → `cannot-check`;
  - an expired key (`--quick-set-expire` to the past) → `expired-key`;
  - a revoked key → `revoked`.
- **Skipped** when `gpg` is absent.

### 9.5 Cross-version (xver)

- **Harness:** the existing one in the scratchpad (`server.py` in the 3.12 venv, `xver.py` driving pip-installed
  releases). It is promoted to `tests/qa/xver/` as a manual job.
- **Steps:**
  1. A new build creates a user-signed commit and tag.
  2. Released `sgit-ai` 0.19.0, 0.21.0, 0.24.0 and 0.26.0 each clone, pull, run `check verify`, `history log` and
     `vault tag show`, and make a commit on top.
- **Expected:** no error; clone signatures verified; the new build sees the old builds' commits as `none`.
- **Also recorded:** Git 2.43's output for a `valid-before` case, to align 5.4.4's label.

### 9.6 End to end on the in-memory API (`tests/unit/sync/test_User_Signing__End_To_End.py`)

Class `Test_User_Signing__End_To_End`, two clones over `Vault__API__In_Memory`:

- **Signing and verifying:**
  - A signs a commit (in-process SSH via `sgit.gpgSign` in a temp `GIT_CONFIG_GLOBAL`) and pushes; B pulls, and
    `check verify` shows `good` with B's allowed-signers file;
  - without B's file → `untrusted`;
  - `--require-user-signature` exits 1 on a mixed history.
- **Commit sites:**
  - a merge commit signed when `-S` is passed to pull;
  - a failing signer (`user.signingKey` pointing at a missing file) makes `commit` exit 1 with the working copy,
    ref, store and merge state unchanged;
  - `write -S` signs;
  - `history revert --as-commit -S` signs.
- **Tags:** `tag create -s` → `vault tag show` "Signed by".
- **Rewrites:** pack import of a user-signed vault reports the dropped count.
- **Display:** `history log --show-signature --json` carries the object; principal control characters are stripped.

### 9.7 Security (`tests/security/`)

| File | Case |
|---|---|
| `test_Security__Fixed__Signing_Config.py` | A vault whose content contains `.gitconfig`, `.git/config`, `gpg.conf` and `allowed_signers` at its root and in subfolders: none is read. argv is identical to that of an empty vault, checked by recording the argv in `Signing__Command_Runner` through a real subclass that writes the argv to a list, not a mock. Also: no `shell=True` anywhere under `sgit_ai/crypto/signing/` (AST scan). |
| `test_Security__Fixed__User_Signature_Replay.py` | A signature copied from commit X onto commit Y → `bad`; copied from a commit onto a tag with the same timestamp → `bad`; namespace `file` → `bad`; a Git-format commit payload signed with namespace `git` does not verify as any sgit object. |
| `test_Security__Known_Gaps.py` (rows added) | TM-R44 (the signed commit is larger), TM-R46 (two verifiers with different files disagree), TM-R47 (a backdated commit inside `valid-before` verifies `good`). |

### 9.8 Acceptance checklist (implementation and deployment)

**Format**

- [ ] `user_signature` is never written when `None`; unsigned commits are byte-identical to before (test).
- [ ] `signing_bytes` and `legacy_signing_bytes` both drop `user_signature` (test pins the legacy case).

**Compatibility**

- [ ] Old-schema fixture: parses, drops and verifies (test).
- [ ] xver: 0.19.0 / 0.21.0 / 0.24.0 / 0.26.0 read, verify and commit on top of a user-signed history (manual run
  recorded in the release note).
- [ ] Web UI team confirmed their signing-bytes rule excludes `user_signature`, or the release note states the
  known display issue (D7).

**Signing**

- [ ] `sgit.gpgSign` defaults off; `commit.gpgSign=true` alone changes nothing (test).
- [ ] Signing failure exits 1 and leaves working copy, refs, store, merge state and index untouched (test).

**Verifying**

- [ ] In-process SSH verify accepts the OpenSSH-produced vector and rejects every malformed case in 9.1.
- [ ] GPG statuses map as 5.7.2 with real gpg (test).
- [ ] `check verify` exit codes per 3.5 (tests); `--json` shape per 3.6.
- [ ] Cache invalidates on any change to the allowed-signers file or keyring (test).

**Security and release**

- [ ] Security tests 9.7 pass; TM rows R44–R47 added and R01 edited.
- [ ] Bandit baseline unchanged except the `# nosec B603` lines in `Signing__Command_Runner`, each with a reason.
- [ ] `sgit doctor` shows the signing block with sources.
- [ ] CHANGELOG entry; README "Signing with your own key" section; cli.sgit.ai docs page.
- [ ] `pytest tests/unit -n auto` and `pytest tests/security` green; integration green with `openssh-client`
  installed in CI.

---

## 10. Implementation steps (ordered commits)

| # | Commit | Contents | Estimate |
|---|---|---|---|
| 1 | `feat(signing): user_signature member, excluded from both signatures' bytes` | Safe types, `Schema__User_Signature`, commit/tag field, `SIGNATURE_MEMBERS`, legacy fix, omit-when-None, old-schema fixture and compat tests, interop vector skeleton | 0.5 d |
| 2 | `feat(signing): SSHSIG format and in-process verifier` | `SSH__Wire`, `SSH__Sig__Blob`, `SSH__Public_Key` (incl. sk), `SSH__Allowed_Signers`, `SSH__Revocation_List`, `SSH__Sig__Verifier`, `SSH__Signer__In_Process`, the OpenSSH-produced vector | 1 d |
| 3 | `feat(signing): Git config, ssh-keygen and gpg` | `Signing__Command_Runner`, `Git__Config__Reader`, `Signing__Config__Resolver`, `SSH__Signer`, `GPG__Signer`, `GPG__Status_Parser`, `GPG__Verifier`, `SSH__Sig__Verifier__Keygen`, `User__Signer`, `User__Signature__Verifier`, cache | 1 d |
| 4 | `feat(signing): sign commits, merges, writes, reverts and tags` | `create_commit(user_signer=)`, commit/write/pull/merge/revert/ignore/tag wiring, `CLI__Argv__Signing`, flags, failure paths | 0.5 d |
| 5 | `feat(signing): show and check user signatures` | `Vault__User_Signatures`, `history log/show --show-signature`, `check verify` summary/exit/`--json`, `vault tag show`, `doctor` block, rewrite counts (7.6) | 0.5 d |
| 6 | `test+docs(signing): security tests, threat model, xver, docs` | 9.7, TM rows, xver run, CHANGELOG, README | 0.5 d |

Total about 4 days. Each commit leaves `pytest tests/unit -n auto` and `pytest tests/security` green.

---

## 11. Open decisions for Dinis

| # | Decision | Recommendation |
|---|---|---|
| D1 | SSH namespace: `git` (works with existing `namespaces="git"` allowed-signers lines, including the ones GitHub's instructions create) or `sgit` (separate domain) | **`git`**. Payload formats cannot collide (6.5), and reuse of the user's Git setup is the point. |
| D2 | Automatic switch: honour Git's `commit.gpgSign` / `tag.gpgSign` directly, or require sgit's own `sgit.gpgSign` (set with `git config --global sgit.gpgSign true`) | **`sgit.gpgSign`**. Otherwise every machine with `commit.gpgSign=true` starts signing sgit commits on upgrade, and agents without an unlocked agent start failing. It keeps the extension rule (off by default) and needs no `sgit config` command. |
| D3 | Read repository-level Git config when the vault sits inside a Git repository | **No**: global and system only, so nothing next to the vault can change signing. |
| D3b | Infer `gpg.format=ssh` from an SSH-looking `user.signingKey` when `gpg.format` is unset | **Yes**, with a one-line note in `doctor`. |
| D4 | In-process signing with an unencrypted key file when `ssh-keygen` is absent | **Yes**: Windows and minimal containers, and the same class the tests use. Encrypted keys still need `ssh-keygen` or the agent. |
| D5 | User-sign `vault move` sentinel commits | **No**: automated commits mid-workflow; the clone signature covers them. |
| D6 | `check verify` exit code when user signatures are `untrusted` | **0** (Git parity); `--require-user-signature` is the strict gate. |
| D7 | Release before the web UI confirms its signing-bytes rule | **Hold the release** of signing (verification can ship) until the web UI confirms, or ship with a release-note line. Unsigned commits are unaffected either way. |
| D8 | X.509 (`gpgsm`) | Not in v1. |
| D9 | SSH certificates and KRLs | Delegate to `ssh-keygen` when installed; otherwise `cannot-check`. |
| D10 | History rewrites drop user signatures | **Report the count and proceed** (Git filter-repo behaviour); no refusal. |
| D11 | Extend the secret guard to OpenSSH/OpenPGP **private** keys | **Yes**, as a small separate change. |
| D12 | `history log --author` matches the signer principal when `--show-signature` is given | **Yes**; cheap with the cache. |
