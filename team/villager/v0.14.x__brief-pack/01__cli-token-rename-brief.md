# Brief — Rename `--token` overload on share/publish/export commands

**Date:** 2026-05-06
**Audience:** Sonnet executor + Sonnet reviewer (two-session pattern)
**Scheduling:** **Before** the visualisation track. Small CLI ergonomics fix; ~½ day total.
**Author:** Villager orchestrator (Opus)

---

## The bug

Three commands overload `--token` to mean a **Simple Token** (content identifier in the form `word-word-NNNN`), while every other command uses `--token` for the **SG/Send access token** (a bearer credential). Two completely different concepts, same flag name. Users hit this and get confused — and there is no way to pass both a custom Simple Token AND an explicit access token to the same command, because one flag has been claimed by each meaning.

| Command | What `--token` means today |
|---|---|
| `sgit vault share --token <word-word-NNNN>` | **Simple Token** — content identifier / share name |
| `sgit vault export --token <word-word-NNNN>` | **Simple Token** — content identifier |
| `sgit share publish --token <word-word-NNNN>` | **Simple Token** — content identifier |
| Every other command (`clone`, `pull`, `push`, `vault info`, `share send`, etc.) | **SG/Send access token** — bearer credential |

The Simple Token is not a credential — it's a memorable public identifier (the URL fragment for the share, e.g. `https://send.sgraph.ai/#word-word-NNNN`). Calling it `--token` invites the same confusion as if `git push` had a `--credential` flag that sometimes meant "the SSH key to authenticate with" and sometimes meant "the branch to push to."

---

## The fix

**Rename `--token` → `--as` on the three commands that publish a share.**

`--as <word-word-NNNN>` reads naturally — "publish this vault **as** `cool-name-1234`" — and aligns with how a user thinks about it (the Simple Token is the *name* the share will be known by). After the rename, top-level `--token` is unambiguously the SG/Send access token everywhere.

### File changes (3 argparse declarations)

In `sgit_ai/cli/CLI__Main.py`:

1. **`vault share`** subparser (in `_register_vault_ns`, around line where `share_p.add_argument('--token', ...)` lives):
   ```python
   share_p.add_argument('--as', dest='share_as', default=None, metavar='WORD-WORD-NNNN',
                        help='Publish under this Simple Token name (generated randomly if omitted)')
   share_p.add_argument('--rotate', action='store_true', default=False, ...)
   # Add a separate --token only if the command needs an access token:
   share_p.add_argument('--token', default=None, help='SG/Send access token')
   ```

2. **`vault export`** subparser (same registrar):
   ```python
   export_p.add_argument('--as', dest='share_as', default=None, metavar='WORD-WORD-NNNN',
                         help='Export under this Simple Token name (generated randomly if omitted)')
   export_p.add_argument('--token', default=None, help='SG/Send access token')
   ```

3. **`share publish`** subparser (in `_register_share_ns`):
   ```python
   publish_p.add_argument('--as', dest='share_as', default=None, metavar='WORD-WORD-NNNN',
                          help='Publish under this Simple Token name (generated randomly if omitted)')
   publish_p.add_argument('--token', default=None, help='SG/Send access token')
   ```

Note: the argparse attribute is `share_as` (because `as` is a Python keyword and can't be a bare attribute name). Use `dest='share_as'` so the consumer reads `args.share_as`.

### Consumer updates (3 sites)

- `sgit_ai/cli/CLI__Vault.py:197` (`cmd_share`): replace `getattr(args, 'token', None)` with `getattr(args, 'share_as', None)` for the Simple Token lookup. If the same handler also needs an access token (separate concept), read it from `args.token` via the existing `token_store.resolve_token(...)` pattern.
- `sgit_ai/cli/CLI__Vault.py:569` (`cmd_export` or wherever export's token_str is read): same rename.
- `sgit_ai/cli/CLI__Publish.py:19` (`cmd_publish`): rename `token_str = getattr(args, 'token', None)` to `share_as = getattr(args, 'share_as', None)`. Update internal variable name everywhere it's used in the function body.

After the change, `cmd_share` / `cmd_export` / `cmd_publish` should be able to consume both an access token AND a Simple Token without conflict. Verify the publish path still works against a private SG/Send endpoint by passing `--token <real-access-token> --as my-share-name` — both should be honoured.

### Help-text wording

For all three commands, the `vault share / vault export / share publish --help` text should clearly distinguish the two flags:

```
--as WORD-WORD-NNNN   Publish under this Simple Token name (generated randomly if omitted)
--token TOKEN         SG/Send access token (only needed once per directory; subsequent
                      commands pick it up automatically)
```

---

## Tests

In `tests/unit/cli/`:

- `test_CLI__Vault__Share` (or wherever `vault share` is tested): add a test that the rename works — `sgit vault share --as my-name <dir>` succeeds and the resulting share token is `my-name`. Also add a test that legacy `--token` (the old flag) **errors with argparse's standard "unrecognized argument"** — confirming the rename is a clean break, no soft alias.
- Same two tests for `vault export` and `share publish`.
- Regression: confirm `--token <access-token>` is still parsed correctly on these three commands and propagated to API__Transfer (the c4aafdc fix continues to work).
- Negative: `sgit vault share --token word-word-NNNN <dir>` should now fail with "unrecognized arguments: --token word-word-NNNN" — argparse will treat the value as a positional argument, which won't match the directory pattern, and error out. Capture the stderr text in a test so we get a stable error contract.

5 tests total. No mocks; use `Vault__Test_Env` fixtures.

---

## Documentation

- Update any CLI help-text examples in `team/villager/v0.13.x__brief-pack/sonnet__onboarding.md`, the email-fs-lite Appendix A draft (when it lands), and any README sections that reference the share workflow.
- Search the repo for `vault share --token`, `vault export --token`, `share publish --token`: `grep -rn 'vault share --token\|vault export --token\|share publish --token' --include='*.md' --include='*.py' --include='*.sh'` — replace with the new flag.

---

## Out of scope

- **No backwards-compat alias.** This is an internal-tooling release; clean break is preferable to dragging a deprecated `--token` through future versions. Argparse's "unrecognized argument" error is good enough — users see the error and read `--help`.
- **No rename of the top-level `--token`.** That one is correctly named (it IS an access token).
- **No rename of `vault info --token`** — that's the access-token usage too.
- **Don't touch positional Simple Token arguments** like `sgit init <token>` or `sgit share receive <token>` — those are unambiguous (positional, single value, not flagged).

---

## Verification checklist

When done:
1. `grep -rn "'--token'" sgit_ai/cli/` shows only the SG/Send-access-token meaning everywhere.
2. `grep -rn "share_as" sgit_ai/cli/` shows the new flag in 3 places + 3 consumers.
3. All 3,250+ unit tests pass.
4. `sgit vault share --help`, `sgit vault export --help`, `sgit share publish --help` clearly distinguish `--as` from `--token` in their output.
5. Manual smoke: `sgit vault share --as test-share-1234 .` — confirms the share publishes under `test-share-1234`.

---

## Why this lands before visualisation

Visualisation is additive and ships when ready. This rename touches the CLI surface — every doc, every example, every agent's muscle memory will encode the new names. Better to bake it in *before* visualisation work starts referencing share commands in mockups and writeups, so the visualisation track ships with the corrected vocabulary already canonical.

Effort: ~½ day total (3 argparse changes, 3 consumer renames, 5 tests, doc grep-and-replace). One commit per logical change (rename + tests + docs as 3 commits, or one if compact). Reviewer Fix pass after.
