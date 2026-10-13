## `_key_for` in sgit_ai/core/actions/verify/Vault__Signatures.py (L28-L40)

**Purpose:** Resolves the public key that a commit's signature will be checked against. Every "verified" verdict in the system (pull, clone, switch, push, `check verify`) rests on which key this returns; returning `None` turns the commit into `no-key`, which `signatures-required` refuses.

**Inputs & Assumptions:**
- `c` (Vault__Components): gives `branch_manager` and `key_manager`. Trust: trusted (built locally by `_init_components` or the clone/pull workspace).
- `read_key` (bytes): the vault read key. Trust: trusted (derived locally).
- `commit` (Schema__Object_Commit): a decrypted commit. Trust: **semi-trusted** — its bytes decrypted under the read key (`Vault__Commit.load_commit` L78-L80), so a read-key holder authored it; the host could not. `author_key_id` is typed `Safe_Str__Author_Key_Id` (regex `^[a-zA-Z0-9:_\-]{1,128}$`, `sgit_ai/safe_types/Safe_Str__Author_Key_Id.py:L5`), so it is path-safe but is **not** required to look like a `key-rnd-imm-…` id.
- `index` (Schema__Branch_Index | None): the local branch index, used only when the commit carries no `author_key_id` (L30).
- Implicit: the local `bare/keys/` directory (`Vault__Key_Manager.key_exists` → `_key_path`, `sgit_ai/crypto/Vault__Key_Manager.py:L69-L70, L78-L79`); the server, when `self.key_fetch` is set (L33-L34).
- Precondition: none checked. A commit with neither `author_key_id` nor a branch in the index yields `None` (L35-L36).

**Outputs & Effects:**
- Returns a loaded EC public key or `None`.
- Side effect: may download and write `bare/keys/<kid>` through `Vault__Key_Fetch.fetch_missing` (L34) — a disk write inside a function named like a lookup.
- Any exception from `load_public_key` (bad ciphertext, non-PEM) is swallowed into `None` (L37-L40).

**Block-by-Block:**

```python
# L29-L32
kid = str(commit.author_key_id) if commit.author_key_id else ''
if not kid and index is not None and commit.branch_id:
    meta = c.branch_manager.get_branch_by_id(index, str(commit.branch_id))
    kid  = str(meta.public_key_id) if (meta and meta.public_key_id) else ''
```
- **What:** Picks the key id: the commit's own claim first, else the index's branch→key mapping.
- **Why here:** `author_key_id` was introduced so the verifier no longer depends on the index still listing the branch (`Vault__Commit.py:L49-L52`).
- **Assumes:** that whoever wrote the commit named the key it was signed with. The commit is encrypted under the read key, so this is a read-key-holder's claim (TM-R01). For the fallback: that the index's `public_key_id` for that branch is the right key; the index is itself read-key-encrypted and merged from the server copy (`Vault__Index_Sync.refresh` L271-L300), so it is also a read-key-holder's claim.
- **Establishes:** `kid` is either `''` or a string matching the Author_Key_Id / Key_Id regex (no `/`, no `..`).
- **Depended on by:** L33-L38.

```python
# L33-L34
if kid and not c.key_manager.key_exists(kid) and self.key_fetch is not None:
    self.key_fetch.fetch_missing(c, [kid])
```
- **What:** Fetches the key file from the server when this clone lacks it and a fetcher was given.
- **Why here:** Before `key_exists` is consulted a second time (L35); a teammate registered after the clone would otherwise be `no-key` forever (module docstring L7-L9).
- **Assumes:** `fetch_missing` only saves a file that decrypts under the read key to a public-key PEM (`Vault__Key_Fetch._is_public_key` L54-L59) — so the host cannot plant a key, but any read-key holder can (TM-R01, `tests/security/test_Security__Known_Gaps.py::test_TM_R01__signatures_required_stops_unsigned_but_not_self_signed`).
- **Establishes:** nothing guaranteed; `fetch_missing` never raises (L27-L31 of Key_Fetch) and returns 0 offline.
- **Depended on by:** L35.

```python
# L35-L40
if not kid or not c.key_manager.key_exists(kid):
    return None
try:
    return c.key_manager.load_public_key(kid, read_key)
except Exception:
    return None
```
- **What:** Loads and decrypts `bare/keys/<kid>`; any failure is `None`.
- **Why here:** after the fetch attempt.
- **Assumes:** `load_public_key` (`Vault__Key_Manager.py:L33-L38`) decrypts under the read key and imports `data['pem']`. A key file written by `create_clone_branch` (`Vault__Branch_Manager.py:L62`) or by `fetch_missing` is the only source; a legacy *private* key file in `bare/keys/` (TM-R27) would also decrypt here — `load_public_key` reads `data['pem']` without checking `data['type']` (L37-L38 of Key_Manager). `import_public_key_pem` on a private PEM raises, which this `except` turns into `no-key`: nothing found that checks `type == 'public'` on this path (the check exists only in `Vault__Key_Fetch._is_public_key` L57).
- **Establishes:** the returned object is a usable public key.
- **Depended on by:** `status_of` L49-L52.

**Cross-Function Dependencies:**
- Callee `Vault__Branch_Manager.get_branch_by_id` (internal, `sgit_ai/storage/Vault__Branch_Manager.py:L99-L103`): linear scan by id; returns `None` when absent. Nothing more.
- Callee `Vault__Key_Manager.key_exists` / `_key_path` (internal, L69-L70, L78-L79): `os.path.isfile(os.path.join(vault_path, 'bare/keys', kid))`. Path containment rests on the Safe_Str regexes above, not on this code.
- Callee `Vault__Key_Fetch.fetch_missing` (internal): see its record. Filters `kid` through `KEY_ID__REGEX` (`^key-rnd-imm-[0-9a-f]{8,64}$`, `Safe_Str__Key_Id.py:L5`) before asking the server; an `author_key_id` not of that shape is never fetched (so it is `no-key` unless already local).
- Callee `Vault__Key_Manager.load_public_key` (internal, L33-L38): read, `crypto.decrypt(read_key, …)` (AES-GCM; a wrong key or tampered file raises), `json.loads`, `import_public_key_pem(data['pem'])`.
- Callers: `status_of` (L49) only.
- Shared state: `bare/keys/` with `create_clone_branch`, `fetch_missing`, `vault move`.
- Invariant coupling: the system's "a commit was signed by a key whose file decrypts under the read key" (threat model §5, Commit signatures row). This function is exactly that statement; it establishes nothing about *who* holds the key.

**Open Questions:**
- unclear; whether `Safe_Str__Author_Key_Id` permitting `:` and arbitrary 1-128 chars (vs `Safe_Str__Key_Id`'s strict `key-rnd-imm-` shape) was intended to allow a non-local key naming scheme. On this path such an id can only resolve if a file by that name already exists under `bare/keys/`.
