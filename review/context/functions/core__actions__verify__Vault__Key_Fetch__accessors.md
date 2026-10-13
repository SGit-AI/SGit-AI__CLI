## `branch_key_ids` in sgit_ai/core/actions/verify/Vault__Key_Fetch.py (L24-L25)

**Purpose:** `[str(b.public_key_id) for b in index.branches if b.public_key_id]` — the ids `fetch_missing` should pre-fetch after an index refresh.

**Inputs & Assumptions:** `index` may be anything with a `branches` attribute or `None` (`getattr(index, 'branches', None) or []`). `public_key_id` is `Safe_Str__Key_Id` on `Schema__Branch_Meta` (L15), so each id already matches `KEY_ID__REGEX`; `fetch_missing` re-checks anyway (L33).

**Outputs & Effects:** list of str; no effects.

**Cross-Function Dependencies:** Callers: `Step__Pull__Load_Branch_Info._refresh_index` L41; `Vault__Sync.verify_signatures` L270.

**Open Questions:** none.

---

## `_is_public_key` in sgit_ai/core/actions/verify/Vault__Key_Fetch.py (L54-L59)

**Purpose:** The acceptance test for a key blob from the server: decrypts under the read key, `type == 'public'`, PEM contains `PUBLIC KEY`.

**Inputs & Assumptions:** `blob` (bytes) untrusted (from the host); `read_key` trusted. AES-GCM `decrypt` (`Vault__Crypto.py:L301-L305`) raises on a wrong key or any bit flip; the `except Exception: return False` (L58-L59) covers that plus bad JSON / non-dict.

**Outputs & Effects:** bool; no effects.

**Establishes:** "this blob was produced by someone holding the read key and says it is a public key". It does not import the PEM (see `fetch_missing` record) and does not bind the content to the file name it was served under (binding is done by `kid not in wanted` in `fetch_missing` L45).

**Cross-Function Dependencies:** Callers: `fetch_missing` L45 only.

**Open Questions:** none.
