## `write_private` in sgit_ai/storage/Vault__Storage.py (L128-L131)

```python
# L130-L131
from sgit_ai.crypto.Vault__Secret_File import Vault__Secret_File
Vault__Secret_File().write(path, data)
```

**Purpose:** The storage-layer entry to the single secret writer; every file that may hold key material is written through it (threat model §5 "File modes").

**Inputs & Assumptions:** `path` trusted (built by callers from `Vault__Storage` accessors or `sg_dir` joins); `data` str or bytes.

**Outputs & Effects:** Delegates entirely. `Vault__Secret_File.write` (read in full, `sgit_ai/crypto/Vault__Secret_File.py:L14-L35`): `makedirs(dirname)` (L21), `tempfile.mkstemp(dir=folder, prefix='.tmp-secret-')` (L23 — mkstemp creates 0600 with `O_EXCL`), write + flush + fsync (L26-L28), `os.replace(tmp, path)` (L29), unlink of the temp on any failure (L30-L35). Postconditions: the final file has mode 0600 regardless of umask; a pre-existing file's mode is replaced; a symlink **at `path`** is replaced not followed (`os.replace` replaces the link entry). A symlink in a **directory component** of `path` is followed by `makedirs`/`mkstemp`/`replace` — `nothing found` that checks the parent chain; callers pass `.sg_vault/local/...` (the `.sg_vault` symlink case noted under `create_bare_structure`).

**Cross-Function Dependencies:**
- Callers (all checked): `write_local_config` L137; `Vault__Bare.extract` L44 (vault key); `Vault__Sync.init` L125 (vault key); `Vault__Attach` L74 (vault key), L82 (clone_mode.json with read key); `Vault__Sync__Lifecycle` L136 (config), L170 (VAULT-KEY from backup zip), L173 (`local/*.pem` from backup zip); `Vault__Backup` L76 (the backup zip itself); `Step__Clone__Setup_Local_Config` L36, `Step__Clone__Headless__Setup_Config` L41, `Step__Clone__ReadOnly__Setup_Config` L42 (clone_mode.json); `Step__Move__Build_Temp_Vault` L446, L511; `CLI__Token_Store` L134 (token); `Secrets__Store` L64; `Vault__Key_Manager.store_private_key_locally` L61 (signing key, via `Vault__Secret_File` directly); `Vault__Reflog._trim` L69 (reflog, via `Vault__Secret_File` directly — not a secret, used for its atomic rename).
- Not through it (plain `open(..., 'w')` into `.sg_vault/local`): `Vault__Sync__Push._save_push_state` L754-L759 (write then `chmod` 0600 — the pre-10/09 pattern the threat model says was replaced "everywhere"; `push_state.json` holds `vault_id`, `clone_commit_id`, `remote_url`, no key), `Vault__Remote_Manager._save_remotes` L122 (remotes.json), `Vault__Merge__State.write` L34, `Vault__Cache_Manager.save_tombstones` L279, `Vault__Ignore._emit_github_migration_notice_once` L169 (notices.json), `Vault__Sync__Base.fetch_tree_lazy` L661 (lazy-fetch.log), `Vault__Reflog.append` L42 (append), `CLI__Token_Store` L160 (base_url), `Vault__Stash` L67 (stash meta). None of these holds key material by their names; `remotes.json` may hold a remote URL with embedded credentials — not checked here.
- Tests: `tests/security/test_Security__Fixed__Symlinks_And_Local.py::Test_Fixed__Secret_Files` (`test_clone_and_read_only_clone_write_their_keys_owner_only`, `test_a_secret_write_never_goes_through_a_planted_link`, `test_uninit_then_restore_keeps_signing_and_the_key_private`), `::test_vault_writes_key_bearing_files_owner_only`.

**Open Questions:**
- Whether `push_state.json` (L754) should count as a secret-bearing file is a judgement for the hunting phase; recorded here only that it is the one `.sg_vault/local` writer still using write-then-chmod.
