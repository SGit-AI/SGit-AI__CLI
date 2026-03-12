# AppSec — Villager Team

## Scope

- Security review of vault data structures (server-side and clone-side)
- Audit encrypted vs unencrypted fields in all schemas and storage formats
- Identify injection points, data leakage, and key material exposure
- Review crypto implementation against known attack vectors
- Adversarial testing: attempt behaviour-changing code modifications to find test gaps

## Security Review Checklist

| Area | What to Check |
|------|---------------|
| Key material | No decryption keys or derivation material in plaintext structures |
| Vault contents | All file contents encrypted (AES-256-GCM) |
| File names | Are file paths in tree structures encrypted or plaintext? |
| Commit metadata | No user-identifiable information beyond signatures |
| API tokens | Tokens masked in logs, not persisted in plaintext |
| Secrets store | Encrypted at rest, passphrase not stored |
| Error messages | No sensitive data leaked in error output |
| Bare vault | No unencrypted sensitive data in .sg_vault/ structure |

## Adversarial Testing Protocol

During Phase 3 (refactoring), work with QA to stress-test the safety net:

1. Change a default value — does a test catch it?
2. Remove a validation — does a test catch it?
3. Alter an encryption parameter — does a test catch it?
4. Change a state transition — does a test catch it?
5. Modify key derivation constants — does a test catch it?

Every undetected behaviour change = a gap in test coverage. Write the missing test. Revert the adversarial change.

## Deliverables

- Security findings document: every field in server-side and clone-side structures mapped
- Vulnerability log: any issues found, captured as passing tests (fix in Phase 3)
- Adversarial testing report: gaps found and tests added
