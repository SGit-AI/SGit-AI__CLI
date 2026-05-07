# Brief 07 — `.vault-settings` in tree + initial commit on `sgit init`

**Date:** 2026-05-07
**Audience:** SGit Dev Agent
**Scheduling:** lands AFTER brief 06 (dotfile tracking) and BEFORE brief 02 (vault move). Estimated effort: ~1 day.
**Author:** Villager orchestrator (Opus)

---

## 1. Why this exists

Vault metadata (`vault_name`, `created`, `created_by`, future settings) currently lives in `.sg_vault/local/config.json` on each clone. This is fragile:

- Different clones can disagree about the vault's `vault_name`. There's no single source of truth.
- Settings are lost on re-clone unless the user copies `.sg_vault/local/` over.
- Vault settings can't travel with the vault when it's moved between servers.
- There's no audit trail of who renamed the vault and when.

The fix: store vault settings in a `.vault-settings` blob at the root of every tree. The settings:

- Are encrypted with the vault's read-key (like any other blob).
- Are content-addressed (just another `obj-cas-imm-*`).
- Survive `vault move`, `vault backup/restore`, server moves — all naturally, because they're just a tracked file.
- Have full audit trail in commit history (rename a vault → new commit).
- Are visible in every working copy as `.vault-settings` (a JSON file the user can read but typically edits via `sgit vault settings set`).

This also aligns sgit with the SG/Send web client (`createFromToken`), which already writes `.vault-settings` to the root tree. Without this brief, web-created vaults would have an extra file that sgit-created vaults don't — interop friction.

**Bonus:** the schema has natural room to grow. Future fields (branch policies, hooks, plugin config, default share permissions) all fit cleanly into `.vault-settings` sections without new infrastructure.

---

## 2. The `.vault-settings` schema (v1)

New file `sgit_ai/schemas/vault/Schema__Vault_Settings.py`:

```python
from osbot_utils.type_safe.Type_Safe              import Type_Safe
from sgit_ai.safe_types.Safe_Str__Vault_Name      import Safe_Str__Vault_Name
from sgit_ai.safe_types.Safe_Str__ISO_Timestamp   import Safe_Str__ISO_Timestamp
from sgit_ai.safe_types.Safe_Str__Semver          import Safe_Str__Semver
from sgit_ai.safe_types.Safe_UInt__Schema_Version import Safe_UInt__Schema_Version


class Schema__Vault_Settings(Type_Safe):
    schema_version : Safe_UInt__Schema_Version = None    # always 1 for v1
    vault_name     : Safe_Str__Vault_Name      = None    # human-readable name
    created        : Safe_Str__ISO_Timestamp   = None    # vault creation timestamp
    created_by     : Safe_Str__Semver          = None    # 'sgit v0.14.x'
```

Round-trip invariant must pass:
```python
assert Schema__Vault_Settings.from_json(obj.json()).json() == obj.json()
```

Serialised form (what gets encrypted and stored as a blob):
```json
{
  "schema_version": 1,
  "vault_name":     "my-research-vault",
  "created":        "2026-05-07T12:00:00Z",
  "created_by":     "sgit v0.14.x"
}
```

Path inside every tree: `.vault-settings` (root-level). Same exact filename the web team uses — interop is intentional.

### 2a. Future-proofing

The schema is intentionally minimal in v1. The brief reserves these fields for v2+:

- `branches: list[Schema__Branch_Policy]` — per-branch read/write rules
- `hooks: list[Schema__Hook]` — pre-commit / post-commit hooks
- `plugins: dict[plugin_name, Schema__Plugin_Settings]` — per-plugin config
- `share: Schema__Share_Defaults` — default share token policies

Don't implement these yet. Just ensure `schema_version` is in v1 so future migrations can detect old settings and upgrade them.

---

## 3. Behaviour changes

### 3a. `sgit init` now creates an initial commit

Today: `sgit init` creates the `.sg_vault/` directory, derives keys, creates a branch index, writes the vault key. Zero commits.

After this brief: `sgit init` does all of the above, plus:

1. Builds a `.vault-settings` blob (encoding `Schema__Vault_Settings.json()` as bytes, encrypting with the read-key).
2. Builds a root tree containing only `.vault-settings`.
3. Creates a commit with message `Initialize vault: <vault_name>`.
4. Writes both clone-branch ref and named-branch ref pointing at the commit.
5. Writes `.vault-settings` to the user's working directory (it's part of the tree, so it appears in the working copy like any other file).

Result: a fresh `sgit init` produces a vault with:
- 1 commit
- 1 tree (root, containing `.vault-settings`)
- 1 blob (`.vault-settings` content)
- 2 refs (clone + named, both pointing at the commit)
- 1 branch index

This is **6 objects on the server after `sgit push`**, matching what's needed for any vault to be coherent. The initial commit also gives every vault a guaranteed audit-trail starting point: "vault created at X by Y."

### 3b. `sgit clone` extracts `.vault-settings` to the working dir

No special handling needed — `.vault-settings` is just a tracked file in the tree. The existing `Step__Clone__Extract_Working_Copy` writes it like any other file.

The user sees a `.vault-settings` file in their working directory. They can `cat` it, edit it, commit edits — it's a normal tracked file. The convention is "edit via `sgit vault settings set`, not by hand," but direct edits work and are visible in commit history if they happen.

### 3c. `sgit vault info` reads from `.vault-settings`

Today, `sgit vault info` reads from `.sg_vault/local/config.json` (and probably the server's manifest.json). After this brief, the canonical source of `vault_name`, `created`, and `created_by` is the `.vault-settings` blob in the HEAD tree. Reading it:

1. Load the HEAD commit.
2. Walk the root tree, find the `.vault-settings` entry.
3. Decrypt the blob.
4. Parse via `Schema__Vault_Settings.from_json(...)`.
5. Surface fields in the `vault info` output.

Add a fallback: if `.vault-settings` is absent (legacy vaults — see §4 migration), generate a synthetic record with `vault_name = "(unnamed)"` and surface a one-line note: "this vault has no settings — run `sgit vault settings init` to create one."

### 3d. New CLI: `sgit vault settings get/set/init`

```
sgit vault settings get [<directory>]                # print current .vault-settings
sgit vault settings set <key> <value> [<directory>]  # update a field, commit, push
sgit vault settings init [<directory>]               # create .vault-settings on a legacy vault
```

`get` reads the current `.vault-settings` from HEAD and prints the JSON. Returns nonzero if `.vault-settings` is absent.

`set` reads the current settings, updates the named field (e.g. `vault_name`), writes the updated blob into a new commit with message `vault-settings: set <key> = <value>`, pushes. Type-checks the field name against `Schema__Vault_Settings.__annotations__`; rejects unknown keys.

`init` is the migration entry point (§4) — adds `.vault-settings` to a legacy vault that doesn't have one.

---

## 4. Migration for existing vaults

Pre-this-brief vaults have no `.vault-settings`. Two options:

- **Option A: lazy.** Tolerate vaults without `.vault-settings`. Generate synthetic data when `vault info` is called. User runs `sgit vault settings init` if they want the real settings tracked.
- **Option B: eager.** Add a one-shot migration `Migration__Vault_Settings` that walks HEAD and prepends a commit adding `.vault-settings`.

**Recommendation: Option A.** No migration runs automatically. Users who care about settings opt in via `sgit vault settings init` (which produces a commit `Initialize vault settings`).

Rationale: the tree-IV migration (`Migration__Tree_IV_Determinism`) is already in flight; piling another auto-migration on top complicates the v0.14.x release. Lazy fallback keeps existing vaults working unchanged. Users who want the new feature explicitly invoke it.

---

## 5. Implementation outline

### 5a. New files

```
sgit_ai/schemas/vault/
├── __init__.py
└── Schema__Vault_Settings.py

sgit_ai/safe_types/
├── Safe_Str__Vault_Name.py        (if not already present)
└── Safe_UInt__Schema_Version.py   (if not already present)

sgit_ai/core/actions/settings/
├── __init__.py
└── Vault__Sync__Settings.py       # get/set/init operations
```

### 5b. Modified files

- `sgit_ai/cli/CLI__Vault.py` — add `cmd_vault_settings_get/set/init` plus a `cmd_init` extension to write `.vault-settings` and create the initial commit.
- `sgit_ai/cli/CLI__Main.py` — register `vault settings get/set/init` subparsers under `_register_vault_ns`.
- `sgit_ai/core/Vault__Sync.py` — add `vault_settings_get(directory)`, `vault_settings_set(directory, key, value)`, `vault_settings_init(directory)` delegate methods on the umbrella facade.
- `sgit_ai/core/actions/init/Vault__Sync__Init.py` (or wherever the init logic lives) — add the initial-commit step at the end of `sgit init`.

### 5c. Init flow change in detail

After today's `sgit init` finishes setting up `.sg_vault/` and writing `VAULT-KEY`, append:

```python
# 1. Build settings
settings = Schema__Vault_Settings(
    schema_version = Safe_UInt__Schema_Version(1),
    vault_name     = Safe_Str__Vault_Name(args.vault_name or '(unnamed)'),
    created        = Safe_Str__ISO_Timestamp(now_utc_iso()),
    created_by     = Safe_Str__Semver(f'sgit {VERSION}'),
)
settings_bytes = json.dumps(settings.json()).encode('utf-8')

# 2. Encrypt + store as blob
sub_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
blob_id, _, file_hash = sub_tree.encrypt_or_reuse_blob(
    settings_bytes, None, read_key)

# 3. Build initial root tree
flat = {'.vault-settings': dict(blob_id=blob_id, size=len(settings_bytes),
                                content_hash=file_hash, content_type='application/json',
                                large=False)}
root_tree_id = sub_tree.build_from_flat(flat, read_key)

# 4. Create initial commit
vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                             object_store=obj_store, ref_manager=ref_manager)
commit_id = vault_commit.create_commit(
    tree_id     = root_tree_id,
    read_key    = read_key,
    parent_ids  = [],
    message     = f'Initialize vault: {settings.vault_name}',
    branch_id   = clone_branch_id,
    signing_key = signing_key,
)

# 5. Write both refs to the new commit
ref_manager.write_ref(clone_ref_id, commit_id, read_key)
ref_manager.write_ref(named_ref_id, commit_id, read_key)

# 6. Write .vault-settings to the working dir
with open(os.path.join(directory, '.vault-settings'), 'wb') as f:
    f.write(settings_bytes)
```

---

## 6. Tests

### 6a. `tests/unit/schemas/vault/test_Schema__Vault_Settings.py`

1. Round-trip invariant.
2. Required fields rejected when missing (Type_Safe enforces this).
3. Schema version is always 1 in v1.

### 6b. `tests/unit/core/actions/init/test_Vault__Sync__Init__Settings.py`

1. `test_init_creates_vault_settings_blob` — after init, the HEAD tree has a `.vault-settings` entry.
2. `test_init_creates_initial_commit` — after init, `sgit history log` shows exactly 1 commit titled `Initialize vault: <name>`.
3. `test_init_writes_vault_settings_to_working_dir` — `.vault-settings` exists at `<directory>/.vault-settings` and parses through `Schema__Vault_Settings.from_json`.
4. `test_init_clone_ref_and_named_ref_aligned` — both refs point at the same commit (the initial one).
5. `test_init_with_explicit_vault_name` — `sgit init my-vault <directory>` produces settings with `vault_name == 'my-vault'`.

### 6c. `tests/unit/core/actions/settings/test_Vault__Sync__Settings.py`

1. `test_settings_get_returns_current_state`.
2. `test_settings_set_creates_commit_with_updated_field`.
3. `test_settings_set_rejects_unknown_field`.
4. `test_settings_init_on_legacy_vault_adds_vault_settings`.
5. `test_settings_init_on_vault_with_existing_settings_errors_clearly`.
6. `test_settings_set_updates_visible_in_working_dir_after_pull` — round trip via push/pull from a fresh clone.

### 6d. `tests/unit/cli/test_CLI__Vault__Settings.py`

1. `test_vault_info_reads_vault_name_from_settings`.
2. `test_vault_info_falls_back_for_legacy_vault_without_settings`.
3. `test_vault_settings_get_prints_json`.
4. `test_vault_settings_set_creates_commit_and_pushes`.
5. `test_vault_settings_init_creates_initial_settings_commit`.

### 6e. Integration test

In `tests/qa/sync/test_Vault__Init_With_Settings.py`:
1. `test_init_then_clone_extracts_vault_settings` — init a vault locally, push, clone from a fresh dir, confirm `.vault-settings` is in the cloned working copy and matches.
2. `test_two_clients_see_consistent_vault_name` — client A inits, client B clones, both `sgit vault info` show the same vault_name.

---

## 7. Interaction with other v0.14.x briefs

- **Brief 06 (dotfile tracking):** must land before brief 07. With brief 06's blanket-dotfile rule dropped, `.vault-settings` is naturally tracked. No special-case logic required.

- **Brief 04 (backup/restore):** `.vault-settings` is just a tracked file. Backup zip captures it as part of the tree. Restore extracts it. No new logic.

- **Brief 02 (vault move):** the move workflow re-encrypts `.vault-settings` like any other blob — object ID stays the same per the move design. `vault_name` inside `.vault-settings` does NOT change during a move (it's user-facing identity, not the cryptographic vault_id). The move-history tracking of `vault_id` changes lives in `.sg_vault/local/move-history.json` (separate from `.vault-settings`).

- **Brief 03 (vault move tests):** add an invariant test asserting `.vault-settings` survives a move with the same content but a re-encrypted blob (object ID stable per the move design's stable-ID property).

---

## 8. Out of scope for this brief

- Branch policies, hooks, plugin config in `.vault-settings` — schema fields reserved but not implemented.
- Auto-migration for legacy vaults — `Option A` (lazy) only; no `Migration__Vault_Settings` runs automatically.
- Renaming an existing field — the `set` command updates values; field renames would require schema_version=2 + a migration.
- Cross-vault settings inheritance — N/A.

---

## 9. Verification checklist

When done:

- All ~22 new tests pass.
- Schema round-trip invariant holds.
- `sgit init` produces a vault with exactly 1 commit.
- `sgit clone <token>` of a fresh vault produces a working copy containing `.vault-settings`.
- `sgit vault info` reads `vault_name` from the HEAD tree's `.vault-settings`.
- `sgit vault settings set vault_name "new-name"` produces a new commit with the updated value.
- `sgit vault settings init` on a legacy vault adds `.vault-settings` and produces an initial-settings commit.
- A vault created via `sgit init` and a vault created via the SG/Send web client's `createFromToken` are byte-identical at the `.vault-settings` level (same schema, same field names, same key types).

Estimated effort: ~1 day total (schema ~1h, init flow change ~2h, settings get/set/init commands ~3h, tests ~2h, web-client interop verification ~30min).
