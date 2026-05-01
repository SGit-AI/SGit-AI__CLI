# F04 — `probe_token` Leakage Surface

**Severity:** LOW
**Class:** Error-message leakage / token-existence side channel
**Disposition:** ACCEPTED-RISK / MINOR-DOC-FIX
**Files:** `sgit_ai/sync/Vault__Sync.py:1803-1837`,
`sgit_ai/cli/CLI__Vault.py:928-954`,
`tests/unit/sync/test_Vault__Sync__Probe.py`

## 1. What Probe Does

```python
# Vault__Sync.py:1803-1837
def probe_token(self, token_str: str) -> dict:
    token_str = token_str.removeprefix('vault://')
    if not _ST.is_simple_token(token_str): raise ...
    keys     = self.crypto.derive_keys_from_simple_token(token_str)
    vault_id = keys['vault_id']
    index_id = keys['branch_index_file_id']
    try:
        idx_data = self.api.batch_read(vault_id, [f'bare/indexes/{index_id}'])
        if idx_data.get(...): return dict(type='vault', vault_id=..., token=...)
    except Exception: pass
    # ... try transfer
    raise RuntimeError(f"Token not found... (derived vault_id={vault_id})")
```

Two network calls; returns `{type: 'vault'|'share', vault_id|transfer_id, token}`.

## 2. Disk Artefacts: NONE — Verified

Read of the function: only computes derived keys in memory, calls
`self.api.batch_read`, and an `_AT().info(vault_id)` for the share path.
No `open(...)`, no `save_file`, no `clone_mode.json` write. **Confirmed safe**:
probe leaves zero disk state.

Mutation M9 (planned): "make probe write `clone_mode.json` on success" would
NOT be caught by current tests because no test asserts the absence of
`clone_mode.json` after probe. **Test gap.**

## 3. Stderr / Stdout Leaks

- The CLI command (`cmd_probe` line 928-954) prints:
  - `vault   {token}` then `Vault ID: {vault_id}` (the token is the user-typed
    simple token; intentional echo).
  - For shares: `Transfer ID: {transfer_id}`.
- Failure path (line 1834-1837):
  ```
  Token not found on SGit-AI or SG/Send: '{token_str}'
    (derived vault_id={vault_id})
  ```
  This goes to stderr via the exception. The vault_id is the SHA-256 of the
  simple token, so it is **a hash of the token, not the token itself**.
  Knowing the hash does not reveal the token (preimage resistance of
  SHA-256).

**Concern:** if a user pastes the wrong token in front of an audience
("nope, that's a typo, let me try again"), the derived vault_id is printed
visibly. An observer can later use this vault_id to query the server to
check whether *some* vault with that hash exists. Since this is exactly what
probe does over the wire anyway, the leak is equivalent. **No new attack
surface.**

## 4. Token Echo

`cmd_probe` echoes the token in the success line: `vault   {token}`. If the
token was pasted on stdin (interactive shell), this is fine — same screen,
same user. If the token was piped from a less-privileged source
(`sgit probe < token.txt`), the token now appears in the output stream that
might be redirected to a more-privileged log. **Acceptable risk** —
identical to `git push` echoing remote URLs that contain HTTP basic auth.

Optional hardening: redact mid-chars: `give-****-8361`. Cosmetic only;
recommend it as a small UX/AppSec ticket, not a release blocker.

## 5. Token-Existence Oracle (the real probe risk)

The whole *purpose* of probe is to tell the user whether a token exists on
SGit-AI vs SG/Send. **This is by design a token-existence oracle.** An
attacker who can run `sgit probe` against arbitrary candidate tokens can
enumerate which ones are live. The defence is the simple-token format:
`word-word-NNNN` is ~25 bits of entropy (BIP39-ish wordlist of a few
thousand). This means a brute-force enumerator can find a live token in
~16M tries. **This is a known property of simple tokens** and should
already be documented in the Simple_Token spec.

**Verification request to Architect:** Does Simple_Token spec already
require server-side rate-limiting on `bare/indexes/...` GET? If not, this
is a denial-of-discovery gap for the share-token surface. **Send back to
Architect for confirmation.**

## 6. Authentication

`probe` calls `self.api.batch_read(vault_id, [...])` and `_AT().info(vault_id)`.
Both are unauthenticated reads on a public derived vault_id — no read_key
or write_key is ever sent over the wire. **Verified safe.**

## 7. Test Coverage

`tests/unit/sync/test_Vault__Sync__Probe.py` covers:
- Vault token returns vault type ✓
- Vault token includes vault_id ✓
- Vault://prefix stripping ✓
- Unknown token raises with 'not found' ✓
- Non-simple-token raises ✓
- JSON output keys ✓

**Gaps:**
- No test asserts probe leaves NO disk artefact — would miss M9 mutation.
- No test asserts probe makes only 1-2 network calls (could regress to
  many calls leaking timing info).
- No test asserts that the error message contains the **derived hash**, not
  the **plaintext token** — a refactor that swapped them in the f-string
  would be undetected.
- No test asserts that two distinct tokens produce two distinct derived
  vault_ids — protects against degenerate Simple_Token implementations.

## 8. Disposition

- **Doc-only:** add "probe is a token-existence oracle by design" to the
  CLI man page.
- **Test gap:** add three small tests (no-disk-artefact, error-contains-hash,
  vault_id-matches-derivation).
- **Escalate to Architect:** rate-limit policy on share-token probe.
- **Optional UX:** mid-char redaction in echo.
