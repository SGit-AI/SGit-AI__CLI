## `status_of` in sgit_ai/core/actions/verify/Vault__Signatures.py (L42-L52)

**Purpose:** Classifies one commit as `missing`, `unsigned`, `no-key`, `verified` or `bad`. It is the atom that `verify_chain` sums, so every policy refusal and every `check verify` line is one of these five words.

**Inputs & Assumptions:**
- `c` (Vault__Components), `read_key` (bytes): trusted, local.
- `commit_id` (str): an object id to classify. Trust: **semi-trusted** — it arrives from a decrypted ref (`Step__Pull__Fetch_Remote_Ref._parse_ref`) or a decrypted parent list (`verify_chain` L85), i.e. from a read-key holder; the host cannot forge it, but the host can withhold the object (→ `missing`).
- `index`: forwarded to `_key_for`.
- `vc` (Vault__Commit | None): built fresh when not given (L43).
- Precondition: `c.obj_store` is the clone's store; whether the object there is authentic rests on verify-before-write at download time (`Vault__Verified_Write.save` L72-L88), not on anything here.

**Outputs & Effects:**
- Returns one of the five status strings. No writes of its own; `_key_for` may write a key file (see its record).
- Raises (not caught here): anything `vc.load_commit` raises — a wrong read key (`InvalidTag`), a `ValueError` for a commit whose JSON does not fit `Schema__Object_Commit` other than the branch_id case (`Vault__Commit.load_commit` L97-L103). `verify_chain` does not catch these either (L78), so a malformed commit aborts the whole check rather than counting as `bad`.

**Block-by-Block:**

```python
# L44-L45
if not c.obj_store.exists(commit_id):
    return MISSING
```
- **What:** A commit this clone does not hold.
- **Why here:** `load_commit` would raise `Vault__Object_Missing_Error` (`Vault__Object_Store.load` L84-L91); this turns absence into a verdict.
- **Assumes:** callers have already fetched what they want classified. In pull that is `Vault__Sync__Status._fetch_commit_chain` run just before (`Vault__Incoming_Check.require_signatures` L42-L43); in clone it is the clone pipeline; in `check verify` nothing fetches, so an incomplete history reports `missing` commits.
- **Establishes:** the object file exists.
- **Depended on by:** L46.

```python
# L46-L48
commit = vc.load_commit(commit_id, read_key)
if not commit.signature:
    return UNSIGNED
```
- **What:** Decrypts the commit; a commit with no `signature` field is `unsigned`.
- **Assumes:** `Vault__Commit.load_commit` (L78-L103) decrypts under the read key (AES-GCM authenticates: a tampered object fails to decrypt and raises). The branch_id repair at L85-L96 rewrites `branch_id` to `''` on a pattern failure — that changes the dict `verify_commit_signature` later canonicalises (L118), so a signed commit with a web-UI branch_id verifies against bytes that differ from what was signed: `bad`.
- **Establishes:** `commit.signature` is non-empty.
- **Depended on by:** L49-L52.

```python
# L49-L52
key = self._key_for(c, read_key, commit, index)
if key is None:
    return NO_KEY
return VERIFIED if vc.verify_commit_signature(commit, key) else BAD
```
- **What:** Resolve the key; verify.
- **Assumes:** `verify_commit_signature` (`Vault__Commit.py:L111-L128`) tries the canonical JCS bytes (L119) and, only when `author_key_id` is absent, the legacy bytes (L120-L121); any exception from `PKI__Crypto.verify` (L71-L76, raises `InvalidSignature`) is caught and treated as "this candidate failed" (L123-L127). A 64-byte raw r||s is split at byte 32 (`PKI__Crypto.verify` L72-L73) — a signature of another length is a bad verdict, not a crash, because of that `except`.
- **Establishes:** `VERIFIED` means: some key file under `bare/keys/` that decrypts under the read key verifies these bytes.
- **Depended on by:** `verify_chain` L78-L81.

**Cross-Function Dependencies:**
- Callee `Vault__Commit.load_commit` (internal, L78-L103): read in full. It never checks that the object's bytes hash to `commit_id` — that is done at download time only (Verified_Write). Nothing here re-verifies.
- Callee `_key_for` (internal): see record.
- Callee `Vault__Commit.verify_commit_signature` (internal, L111-L128): as above.
- Callers: `verify_chain` (L78); `tests/security/test_Security__Known_Gaps.py::test_TM_R01__forged_commit_is_pulled_and_verifies` calls it directly to prove a self-signed forgery is `verified`.
- Shared state: none beyond the object store.
- Invariant coupling: `VERIFIED` ≠ "written by a teammate" — threat model §5 and TM-R01.

**Open Questions:**
- unclear; whether the `branch_id`-stripping repair in `load_commit` (L85-L96) is ever hit for a *signed* commit in practice (web-UI commits are described as unsigned). If it is, those commits read as `bad`, not `verified`, under the policy.
