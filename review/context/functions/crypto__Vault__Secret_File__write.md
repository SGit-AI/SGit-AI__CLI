## `write` in sgit_ai/crypto/Vault__Secret_File.py (L14-L35)

```python
# L20-L35
folder = os.path.dirname(path) or '.'
os.makedirs(folder, exist_ok=True)
payload = data.encode() if isinstance(data, str) else data
fd, tmp = tempfile.mkstemp(dir=folder, prefix='.tmp-secret-')
try:
    with os.fdopen(fd, 'wb') as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())                     # on disk before the rename makes it the file
    os.replace(tmp, path)
except BaseException:
    try:
        os.unlink(tmp)
    except OSError:
        pass
    raise
```

**Purpose:** "The one way a secret reaches disk" (module docstring L1-L5). Vault key, read-only `clone_mode.json`, access token, clone signing `.pem`s, PKI private PEMs, the credential store, keyed backups, `config.json`, `remote_heads.json` and the reflog all go through it, directly or via `Vault__Storage.write_private` (`sgit_ai/storage/Vault__Storage.py:L128-L131`). The threat model's "File modes" row (§5) and TM-F05/F16 rest on this function.

**Inputs & Assumptions:**
- `path` (str): destination. Trust: trusted (built from `.sg_vault/local/...`, `~/.sg-send/...`, or a user-chosen `--output` at `CLI__PKI.py:L197-L204`).
- `data` (str or bytes): the secret.
- Implicit: filesystem semantics — `mkstemp` creates with mode 0600 and `O_EXCL` (stdlib guarantee, relied on by docstring L15-L16); `os.replace` is atomic on POSIX.
- Precondition: `folder` is a real directory we own. `os.makedirs` creates it with the process umask (so `.sg_vault/local` is typically 0755: TM-R15 "names visible, contents 0600"). If `folder` is a symlink, both the temp file and the rename land in its target: the function refuses a link AT `path` (replaced by `os.replace`), not a link ABOVE it. **nothing found** here; threat model §5 "Symlinks" accepts links above the vault root.

**Outputs & Effects:**
- Creates/replaces `path` atomically with a 0600 file (`tests/security/test_Security__Fixed__Symlinks_And_Local.py::test_vault_writes_key_bearing_files_owner_only` under umask 022; `::test_a_secret_write_never_goes_through_a_planted_link` — target untouched, link replaced).
- An existing file's mode and inode are NOT inherited: a hard link elsewhere keeps the OLD content (TM-F18 mentions a hard link to the backup), and the old inode's bytes are not zeroed (contrast `Vault__Storage.secure_unlink` L146-L163, used only on `rekey_wipe`).
- Durability: the file is fsynced (L28) but the DIRECTORY is not, so the rename itself may not survive a crash — a durability, not a secrecy, property.
- On any exception the temp file is unlinked and the exception re-raised (L30-L35); `path` is untouched.
- On Windows the 0600 is not enforced (docstring L18-L19).
- Returns nothing.

**Block-by-Block:**

```python
# L20-L21
folder = os.path.dirname(path) or '.'; os.makedirs(folder, exist_ok=True)
```
- **What:** Ensure the parent exists.
- **Assumes:** creating parents with default mode is acceptable (see TM-R15).

```python
# L23
fd, tmp = tempfile.mkstemp(dir=folder, prefix='.tmp-secret-')
```
- **What:** Unique 0600 file in the SAME directory so the later rename is same-filesystem.
- **Establishes:** no window in which the bytes are readable by others; no dependence on umask or chmod.
- **Depended on by:** every test that asserts 0600 (`tests/unit/sync/test_Vault__Sync__File_Modes.py`, `test_Vault__Key_Manager__Permissions.py`).

```python
# L25-L29
write, flush, fsync, os.replace(tmp, path)
```
- **What:** Publish only a complete file.
- **Establishes:** readers never see a half-written vault key / config (`Vault__Storage.write_local_config` L133-L137 cites review F10).

**Cross-Function Dependencies:**
- Callees: `tempfile.mkstemp`, `os.replace`, `os.fsync` (external, stdlib).
- Callers: `Vault__Storage.write_private` (L130-L131) and through it `CLI__Token_Store.save_token` L134, `Secrets__Store._save_all` L64, `Vault__Sync.py:L125` (vault key), `Vault__Bare.py:L44`, `Vault__Attach.py:L74,L82`, `Vault__Backup.py:L76`, `Vault__Sync__Lifecycle.py:L136,L170,L173`, clone steps (`Step__Clone__Setup_Local_Config.py:L36`, `Step__Clone__ReadOnly__Setup_Config.py:L42`, `Step__Clone__Headless__Setup_Config.py:L41`), move (`Step__Move__Build_Temp_Vault.py:L446,L511`); directly: `Vault__Key_Manager.store_private_key_locally` L61, `PKI__Key_Store.generate_and_store` L24,L27, `CLI__PKI.cmd_decrypt` L204, `Vault__Sync__Base.py:L197` (baselines), `Vault__Reflog.py:L69`.
- NOT used by: `CLI__Token_Store.save_base_url` (open+chmod, L160-L165), `CLI__Credential_Store._touch_activity` (L75-L80), `Vault__Key_Manager.store_public_key`/`store_private_key` (plain `open`), `PKI__Key_Store` public PEMs and metadata, `PKI__Keyring.add_contact`, `CLI__Main._save_debug_flag` (open+chmod). Of these only `store_private_key` holds private material (and it has no production caller).

**Open Questions:**
- unclear; whether any caller passes a `path` whose parent is user-controlled beyond `--output` in `sgit pki decrypt` (`CLI__PKI.py:L196`). There, `makedirs` on an arbitrary parent and a write into it are what the user asked for.
