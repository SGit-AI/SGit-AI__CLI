# Changelog

All notable, user-visible changes to **sgit-ai** are recorded here.

The format is loosely based on Keep a Changelog; the project follows semantic
versioning per `sgit_ai/_version.py`.

## [Unreleased]

### Security

  - **Path-traversal containment in vault checkout.** Vault tree-entry names are
    decrypted from vault data and chosen by whoever authored the vault, so a
    hostile vault cloned with `sgit clone` could carry an entry named
    `../../etc/foo` (or an absolute path) and overwrite files outside the working
    copy. All working-directory writes derived from vault data now pass through
    `Vault__Path_Guard`, which rejects absolute paths and `..` traversal and
    verifies the target stays under the destination.

### Removed — Simple Token / SG-Send transfer feature

The Simple Token credential scheme (`word-word-NNNN`) and the SG/Send
transfer/share/publish/export feature built on it have been **removed entirely**.
The scheme carried only ~30 bits of entropy and exposed a fast public-ID oracle;
it is no longer part of sgit. Removed:

  - Commands: `sgit share` (send/receive/publish), `sgit vault export`,
    `sgit vault share`, `sgit vault probe`, and the `sgit clone <simple-token>`
    transfer variant.
  - Code: `Simple_Token`, the word list, `Vault__Transfer`, `Vault__Archive`,
    `API__Transfer`, `Transfer__Envelope`, the transfer clone workflow and its
    steps, and the associated transfer/archive schemas.
  - The `edit_token` field on the local config and the `simple_token` config
    mode are gone; existing simple-token-addressed vaults are no longer readable
    by the CLI (re-key to a `passphrase:vault_id` vault key).

`sgit clone <vault-key>` (the `passphrase:vault_id` form), commit, push, pull,
and all standard vault operations are unaffected.
