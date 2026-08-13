# Brief 08 — `--vault-key` flag for headless administrative commands

**Date:** 2026-05-07
**Audience:** SGit Dev Agent
**Scheduling:** lands AFTER the vault-ops sprint (briefs 06/07/04/02/03), before visualisation. Estimated effort: ~½ day.
**Author:** Villager orchestrator (Opus)

---

## 1. Why this exists

Some administrative commands today require a local clone to operate, even when conceptually they only need credentials. The motivating case: a user with a broken / unclonable vault on the server can't run `sgit vault delete-on-remote` to clean it up, because that command resolves credentials from the local clone's `.sg_vault/local/config.json`. Workaround today is `sgit clone-headless <key> /tmp/...` first, then `sgit vault delete-on-remote /tmp/...` — a 10-second detour that shouldn't be necessary.

The fix: add a `--vault-key <key>` flag to admin commands that fundamentally just need the vault credentials. With the flag, the command derives `vault_id` + `write_key` directly from the key, skips any local-clone resolution, and acts on the server.

`--vault-key` is the right name because:
- It's literally the contents of the `VAULT-KEY` file. Users already think in those terms.
- Unambiguous against `--token` (SG/Send access credential, established in brief 01) and `--as` (Simple Token used as a publish/share name, also brief 01).
- Accepts both simple-token form (`word-word-NNNN`) and full-key form (`<passphrase>:<vault_id>`), matching how `sgit clone` already takes either.

---

## 2. Scope — which commands gain `--vault-key`?

The flag applies to commands that:
- Need vault credentials (vault_id + write_key, or vault_id + read_key).
- Don't need local objects (no bare/data tree walk, no working-copy state).
- Are typically run when the local clone is broken, missing, or never existed.

Three commands qualify in v1:

| Command | Why it's a fit | What `--vault-key` enables |
|---|---|---|
| `sgit vault delete-on-remote` | Calls `api.delete_vault(vault_id, write_key)`; doesn't touch local objects | Recover from a broken vault without a local clone |
| `sgit vault probe` | Probes server for vault existence; only needs vault_id | Test "does this vault exist?" without cloning |
| `sgit vault info --remote` | Could surface server-side state (manifest, key_generation) without a local clone | See vault metadata without cloning |

Out of scope for v1: `vault rekey`, `vault uninit`, `vault clean`, `clone`, `pull`, `push`, `commit`. These either need local objects or need to update local state — `--vault-key` doesn't help them.

---

## 3. CLI surface

For each command, the directory argument stays positional with default `.` (existing behaviour). `--vault-key` is an alternative path:

```
sgit vault delete-on-remote [<directory>]
    [--vault-key <key>]               # NEW: skip local clone; derive credentials from key
    [--yes]
    [--json]
    [--token <access-token>]          # SG/Send API access (existing, unchanged)
```

When `--vault-key` is passed:
- The `<directory>` argument is ignored (with a one-line note: `"--vault-key set — ignoring directory argument"`).
- Credentials are derived via `crypto.derive_keys_from_simple_token(...)` or `derive_keys_from_vault_key(...)` depending on form.
- No `.sg_vault/` is required, created, or modified anywhere on disk.
- Confirmation prompts include the resolved `vault_id` so the user can sanity-check what they're about to act on.

When `--vault-key` is NOT passed: existing behaviour unchanged. The command resolves credentials from the local clone at `<directory>` (default `.`).

---

## 4. Implementation

### 4a. New helper in `Vault__Sync__Base`

`Vault__Sync__Base._init_components_from_vault_key(vault_key: str) -> Vault__Components`

Mirror of the existing `_init_components(directory)` but derives credentials from the key directly. Doesn't touch the filesystem. Returns a populated `Vault__Components` with `vault_id`, `read_key`, `write_key`, `branch_index_file_id`, `ref_file_id` derived via crypto. Other fields (`storage`, `pki`, `obj_store`, `ref_manager`, `branch_manager`) can be left None or constructed against an in-memory ephemeral path — only fields needed by the calling command should be required.

The two action methods that consume this (`Vault__Sync__Lifecycle.delete_on_remote`, `Vault__Sync__Lifecycle.probe_token`) already read narrow fields. Audit each: if a method only uses `c.vault_id` and `c.write_key`, the helper just needs to populate those two.

### 4b. Action method overload

`Vault__Sync__Lifecycle.delete_on_remote` gains an alternate form:

```python
def delete_on_remote(self, directory: str = None, vault_key: str = None) -> dict:
    """Delete every server-side file for this vault.
    Provide either `directory` (a local clone) OR `vault_key` (no local clone needed).
    """
    if vault_key is None and directory is None:
        raise ValueError('delete_on_remote requires either directory or vault_key')

    if vault_key is not None:
        c = self._init_components_from_vault_key(vault_key)
    else:
        c = self._init_components(directory)

    if not c.write_key:
        raise RuntimeError('delete-on-remote requires write access — read-only access cannot delete a vault')

    result = self.api.delete_vault(c.vault_id, c.write_key)
    self.crypto.clear_kdf_cache()

    if directory is not None:
        storage = Vault__Storage()
        self._clear_push_state(storage.push_state_path(directory))

    return result
```

Same pattern for `probe_token` (already accepts `token_str` directly — no real change there, just confirmation that the existing API works).

### 4c. CLI handler change

In `cmd_delete_on_remote` (`CLI__Vault.py`):

```python
def cmd_delete_on_remote(self, args):
    vault_key = getattr(args, 'vault_key', None)
    directory = getattr(args, 'directory', '.') or '.'

    if vault_key:
        # Headless mode: skip directory entirely
        if directory and directory != '.':
            print(f'  --vault-key set — ignoring directory argument: {directory}', file=sys.stderr)

        # Confirmation prompt shows resolved vault_id
        from sgit_ai.crypto.simple_token.Simple_Token import Simple_Token
        from sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
        crypto = Vault__Crypto()
        if Simple_Token.is_simple_token(vault_key):
            keys = crypto.derive_keys_from_simple_token(vault_key)
        else:
            keys = crypto.derive_keys_from_vault_key(vault_key)
        vault_id = keys['vault_id']

        if not args.yes:
            print(f'About to DELETE vault {vault_id} from the remote server.')
            print(f'  Vault key: {vault_key[:8]}...')
            print(f'  This is irreversible — the vault_id will be tombstoned.')
            confirm = input('Continue? [y/N] ').strip().lower()
            if confirm not in ('y', 'yes'):
                print('Aborted.', file=sys.stderr)
                sys.exit(1)

        sync   = self.create_sync()
        result = sync.delete_on_remote(vault_key=vault_key)
    else:
        # Existing behaviour — resolve from local clone
        ...
```

### 4d. CLI registration in `CLI__Main.py`

```python
dor_p = vault_sub.add_parser('delete-on-remote',
    help='Hard-delete this vault from the server. Pass --vault-key to act without a local clone.')
dor_p.add_argument('directory', nargs='?', default='.',
                   help='Vault directory (default: .) — ignored if --vault-key is set')
dor_p.add_argument('--vault-key', dest='vault_key', default=None, metavar='KEY',
                   help='Vault key (simple token or full key form). Skips local-clone lookup.')
dor_p.add_argument('--yes', action='store_true', default=False, help='Skip confirmation prompt')
dor_p.add_argument('--json', action='store_true', default=False, help='Output result as JSON')
dor_p.set_defaults(func=self.vault.cmd_delete_on_remote)
```

Note `dest='vault_key'` so argparse exposes it as `args.vault_key` (Python keyword `key` is fine but `vault_key` is more grep-friendly across the codebase).

---

## 5. Tests

In `tests/unit/cli/test_CLI__Vault__Delete_On_Remote__VaultKey.py` (new):

1. `test_delete_with_vault_key_simple_token_form` — set up a real vault on `Vault__API__In_Memory`; run `delete-on-remote --vault-key word-word-NNNN --yes`; assert vault is removed from the in-memory API.
2. `test_delete_with_vault_key_full_key_form` — same but with full `<passphrase>:<vault_id>` form.
3. `test_delete_with_vault_key_skips_directory_argument` — pass both `<directory>` and `--vault-key`; assert directory was ignored, the warning was printed to stderr.
4. `test_delete_with_vault_key_no_local_dir_required` — run from an empty directory with no vault; assert command succeeds (no `.sg_vault/` was needed).
5. `test_delete_with_vault_key_wrong_key_errors_clearly` — pass a vault key that doesn't match any existing vault; assert clear error (vault not found / write key invalid).
6. `test_delete_with_vault_key_after_already_deleted_handles_tombstone` — call delete twice; second call should report "already deleted / not found" without crashing. (Couples with brief 02's tombstone behaviour — the second delete returns 403, which should be translated to a friendly message.)
7. `test_delete_with_vault_key_confirmation_default_no` — without `--yes`, the prompt defaults to "no" and aborts when nothing is typed.
8. `test_delete_with_vault_key_resolves_vault_id_for_confirmation` — the confirmation prompt includes the vault_id so the user can verify before agreeing.

In `tests/unit/core/test_Vault__Sync__Base__From_Vault_Key.py` (new):

1. `test_init_components_from_vault_key_simple_token` — asserts `vault_id` + `write_key` correctly derived.
2. `test_init_components_from_vault_key_full_key` — same for the colon form.
3. `test_init_components_from_vault_key_does_not_touch_disk` — assert no `.sg_vault/` directory created anywhere as a side effect.
4. `test_init_components_from_vault_key_invalid_form_rejected` — pass garbage; assert clear "not a valid vault key" error.

---

## 6. Documentation

Update `sgit vault delete-on-remote --help` text to mention both forms:

```
usage: sgit vault delete-on-remote [-h] [--vault-key KEY] [--yes] [--json] [--token TOKEN] [directory]

Hard-delete this vault from the server. Local clone is untouched.

Two ways to specify which vault:
  1. Local clone:  sgit vault delete-on-remote .          (default — uses .sg_vault/ in <directory>)
  2. Headless:     sgit vault delete-on-remote --vault-key word-word-NNNN
                   (skips local clone; useful for broken vaults)

After deletion the vault_id is permanently tombstoned on the server —
that vault_id can never be reused or written to again.
```

Update `team/villager/v0.13.x__brief-pack/visualisation/...` if any of the visualisation docs reference `delete-on-remote` workflows. Not expected, but worth a `grep -rn "delete-on-remote"` sweep.

---

## 7. Out of scope

- **Extending `--vault-key` to commands that need local state** — `pull`, `push`, `commit`, `clone`, etc. These don't fit the pattern; each has its own directory-rooted state. Don't extend the flag to them.
- **`--read-key <hex>` for read-only operations** — could be useful for `vault probe` against a read-only-shared vault. Defer; covers a smaller use case.
- **Unifying `--vault-key` with the positional simple-token argument** that `sgit clone` accepts — `clone` takes the vault key positionally; `vault delete-on-remote` already takes a directory positionally. The flag form for delete is the unambiguous answer; don't try to merge with `clone`'s positional pattern.
- **Auto-detection** of "is this a vault key or a directory?" in the positional argument — explicit flag is clearer than heuristic detection.

---

## 8. Verification checklist

When done:

- All ~12 new tests pass.
- `sgit vault delete-on-remote --vault-key pearl-ridge-2662 --yes` works against a real test vault without any local clone setup.
- `sgit vault delete-on-remote .` (the existing form) still works unchanged.
- Confirmation prompt shows the resolved vault_id when `--vault-key` is used.
- Help text for `delete-on-remote` documents both forms.
- KNOWN_VIOLATIONS unchanged.

Estimated effort: ~½ day total (helper + action overload ~1.5h, CLI handler ~1h, tests ~2h, doc/help-text update ~30min).
