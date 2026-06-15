# Changelog

All notable, user-visible changes to **sgit-ai** are recorded here.

The format is loosely based on Keep a Changelog; the project follows semantic
versioning per `sgit_ai/_version.py`.

## [Unreleased] — Simple Token security gate

### Disabled (pending Simple Token security rework)

The current Simple Token scheme (`word-word-NNNN`; no expiry, revocation, or
scoping) is under security rework. The following user-facing CLI commands are
TEMPORARILY DISABLED at the dispatcher and exit with code `2`:

  - `sgit vault export`
  - `sgit vault share`
  - `sgit share send`
  - `sgit share publish`
  - `sgit clone <simple-token>` — only the SG/Send transfer-clone variant; the
    SGit-AI vault clone path is unaffected because it uses an existing token
    rather than minting a new one.

Backend implementations (`Simple_Token`, `Simple_Token__Wordlist`,
`Vault__Transfer`, `Workflow__Clone__Transfer` wiring, `Vault__Sync.init`'s
`token=` parameter) are RETAINED so the rework can refactor in place.

### Changed (user-visible behaviour)

  - **`sgit init` (bare):** previously created a subdirectory named after an
    auto-generated simple token (e.g. `apple-banana-1234/`). Now initialises a
    vault in the **current directory** using a standard `passphrase:vault_id`
    vault key. If you want a named subdirectory, use `sgit init <name>`.
  - **`sgit create <vault-name>`:** no longer special-cases simple-token-shaped
    `<vault-name>` or `--vault-key`. Pass a standard vault key, or omit it to
    generate one.
  - **`sgit push` next-step hints:** no longer mention `sgit share` or
    `sgit publish` (both disabled). Hints remain for kept commands
    (`sgit status`).
  - **`sgit vault probe` help text:** softened from "Identify a simple token as
    a vault or share" to "Identify a token as a vault or share (no clone) —
    read-only diagnostic". Functionality is unchanged; `probe` remains a
    consume-only diagnostic that still accepts simple-token-shaped inputs for
    users with existing vaults.

### Kept unchanged

  - `sgit share receive <token>` — consumes tokens, never creates them.
  - `sgit clone <vault-key>` (passphrase:vault_id form) — never uses Simple
    Tokens.
  - `sgit vault probe` — read-only diagnostic.

### Implementation notes

  - Disabled commands print which `argv` was parsed so users can see that flags
    were accepted but ignored (the disablement is on the whole command, not
    any specific flag).
  - See `team/explorer/architect/reviews/06/13/v0__architect-review__cli-simple-token-disablement.md`
    for the architect's review of the disablement scope and the F1–F11
    findings addressed.
