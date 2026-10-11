## `cmd_vault_ignore` in sgit_ai/cli/CLI__Vault.py (L1609-L1653)

**Purpose:** Without `--apply`: list always-ignored folders. With `--apply FOLDER`: remove every head-tracked path under `FOLDER/` from the vault in one visible commit, work tree untouched (the deliberate escape from "tracked-wins" grandfathering).

**Inputs & Assumptions:** `args.directory`, `args.apply` (a single top-level folder name), `args.yes`. `Vault__Ignore__Apply(crypto=Vault__Crypto(), api=Vault__API())` (L1617) — a bare API (pinned default); the action makes no network call anyway.

**Outputs & Effects:**
- Preview via `tracked_under` (L1628; read-only, every exception → `[]`, `Vault__Ignore__Apply.py:L87-L108`).
- Confirmation prompt unless `--yes` (L1638-L1642; `CLI__Input().prompt` returns `None` on non-TTY ⇒ "Aborted. Nothing written.").
- `ignore_apply.apply(directory, apply_dir)` (L1644): in `Vault__Ignore__Apply.apply` (L19-L85): name validation (single segment, no `/`, not `.`/`..`, L26-L29); **requires a write key** (`Vault__Read_Only_Error`, L32-L33) although nothing is written to the server here; new tree = old flat minus the prefix (`build_from_flat`, L63-L64); signed with the local key when loadable, else **silently unsigned** (L66-L71 — no warning, unlike `Vault__Sync__Commit._load_signing_key`); `create_commit` with `author_key_id` only when signed (L75-L81); clone ref moved (L82).
- Prints the commit id and "Run `sgit push`".

**Assumes:** the clone branch head is this clone's own history; the removal commit is an ordinary commit to be pushed. The deleted paths' blobs stay in the object store (no GC here).

**Cross-Function Dependencies:**
- Callees: `Vault__Ignore__Apply.tracked_under`/`apply`; `Vault__Sub_Tree.flatten`/`build_from_flat`; `Vault__Commit.create_commit`; `Vault__Key_Manager.load_private_key_locally`; `Vault__Ref_Manager.write_ref`.
- Callers: `vault ignore` parser (L579-L587).

**Open Questions:**
- unclear; the silent-unsigned path in `Vault__Ignore__Apply.apply` L66-L71 versus the "never unsigned silently" rule stated in `Vault__Sync__Commit._load_signing_key` L21-L22. Under `signatures-required`, a teammate's pull would refuse the removal commit with `unsigned` and name it.
