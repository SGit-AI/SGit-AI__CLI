## `_prompt_passphrase` in sgit_ai/cli/CLI__Credential_Store.py (L57-L67)

```python
# L58-L67
passphrase = os.environ.get('SG_SEND_PASSPHRASE')
if passphrase:
    return passphrase
import getpass
passphrase = getpass.getpass('Passphrase: ')
if confirm:
    confirm_pp = getpass.getpass('Confirm passphrase: ')
    if passphrase != confirm_pp:
        raise RuntimeError('Passphrases do not match')
return passphrase
```

**Purpose:** Obtains the credential-store passphrase: environment variable first, interactive prompt otherwise. Called (as a "private" method) by `CLI__Vault.cmd_vault_add/list/remove/show` (`CLI__Vault.py:L1659,L1665,L1674,L1682`).

**Inputs & Assumptions:**
- `SG_SEND_PASSPHRASE`: Trust: the process environment (readable by same-user processes; inherited by children). The same variable is read by `CLI__PKI` (L30, L213) for the PKI key passphrase — ONE variable, two stores.
- `confirm` (bool): only `cmd_vault_add` passes `True` (L1659). With the env var set, confirmation is skipped (L59-L60 return before L63).
- Empty passphrase: `getpass` can return `''`; nothing here rejects it (contrast `CLI__PKI.cmd_keygen` L31-L33). An empty passphrase then derives a master key like any other (`test_Vault__Crypto__Hardening.py::test_pbkdf2__empty_passphrase` shows PBKDF2 accepts it). **nothing found** rejecting it on the credential-store path.

**Outputs & Effects:** str, or `RuntimeError` on mismatch. No state.

**Cross-Function Dependencies:** `getpass` (stdlib). Tests: `test_CLI__Credential_Store.py::test_prompt_passphrase__from_env`, `::test_prompt_passphrase__via_getpass`, `::test_prompt_passphrase__confirm_mismatch`, `::test_prompt_passphrase__confirm_match`.

**Open Questions:** none.
