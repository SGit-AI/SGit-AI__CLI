## `commit` in sgit_ai/core/actions/commit/Vault__Sync__Commit.py (L32-L183)

**Purpose:** Turn the working copy into a tree + a (signed) commit on this clone's branch. In this slice: where the secret guard runs, how working-copy files are read, how links are handled, and how a file is decided deleted.

**Inputs & Assumptions:**
- `directory`, `message`, `allow_deletions` (sparse), `no_merge_commit`, `amend`, `allow_secret_files` (list of paths the user exempts from the zip check).
- Implicit: local config (`my_branch_id`, `sparse`, scope), the index, the clone ref, the working copy, `.sg_vault/local/<key>.pem`.

**Outputs & Effects:**
- Object store: blobs (`encrypt_or_reuse_blob`), trees, the commit (`create_commit` L164-L170).
- Clone ref ← new commit (L172, with reflog).
- Merge state deleted or rewritten (L174-L177).
- stderr warnings: skipped symlinks (`_scan_local_directory(warn_links=True)` L78 → L460-L464 of Base), unsigned commit (`_load_signing_key` L26-L29).
- Raises `Vault__Secret_In_Commit_Error`, `Vault__Scoped_Clone_Error`, `Vault__Unreadable_File_Error`, `RuntimeError('nothing to commit…')`.

**Block-by-Block:**

```python
# L78
new_file_map = self._scan_local_directory(directory, warn_links=True)
```
- **What:** `{rel: {size, content_hash}}` of the working copy.
- **Assumes/establishes (from `Vault__Sync__Base._scan_local_directory` L398-L465):** `.gitignore` + always-ignored dirs honoured (L411, L428-L436); symlinked dirs and files are **skipped** and collected (L430-L432, L438-L440), with a warning here; each file is read with `Vault__Path_Guard.read_regular` (L442: `O_NOFOLLOW|O_NONBLOCK`, lstat then fstat on the fd, FIFOs/sockets/devices → `None` + warning, ELOOP → `None`, any other `OSError` → `Vault__Unreadable_File_Error` **raised** on this path since `unreadable_out is None`, L443-L445); tracked paths hidden under a link, or that are FIFOs/devices, get their **committed** entry back (`_keep_tracked_under_links` L455-L459) so they read as unchanged, never deleted.
- So "deleted" = in `old_flat_entries` and not in `new_file_map`, where `new_file_map` cannot lose a file to a link, a FIFO, or an unreadable error; it *can* lose one to `.gitignore` (a newly ignored tracked file reads as deleted here — the "tracked-wins" grandfathering mentioned in `cmd_vault_ignore` L1633-L1635 is in `Vault__Ignore.load_tracked_from_vault`, L411 of Base, not traced).

```python
# L79-L83
changed = [p for p, e in new_file_map.items()
           if not (old_flat_entries.get(p) or {}).get('content_hash')
           or old_flat_entries[p]['content_hash'] != e.get('content_hash')]
Vault__Secret_Guard().refuse_files(directory, changed, allowed=allow_secret_files or ())
```
- **What:** The secret guard runs on files this commit **adds or changes** only (F2: a file committed once with `--allow-secret-file` is not refused again).
- **Why here:** after the scan, before any blob is encrypted.
- **Assumes (from `Vault__Secret_Guard.refuse_files` L29-L63):** regular, non-linked files only (L48-L49); a hard link (`st_nlink > 1`) whose inode matches a file under `.sg_vault/local/` refuses regardless of `allowed` (L50-L56, L57-L58 — "never the hard-link one"); a file whose first 4 bytes are `PK\x03\x04` is opened (`read_regular`) and refused if the zip holds `VAULT-KEY`/`local/vault_key`, a `local/token` inside sgit's layout, or a `local/*.pem` with `PRIVATE KEY` (L75-L90, L92-L103). The comparison `old hash != new hash` relies on the **author's** `content_hash` in HEAD, which is this clone's own earlier commit — trusted.
- **Establishes:** no changed file is a backup zip with a key, nor a hard link to this clone's secrets.
- **Depended on by:** everything that encrypts content below.
- Tests: `tests/security/test_Security__Fixed__Secrets_In_Commits.py::test_a_renamed_backup_is_refused_by_content`, `::test_a_hard_link_to_the_vault_key_is_refused`, `::test_naming_a_hard_link_to_the_vault_key_does_not_commit_it`, `::test_a_file_committed_on_purpose_does_not_block_later_commits`; `tests/security/test_Security__Fixed__Symlinks_And_Local.py::test_K1__a_link_to_the_vault_key_is_never_committed`, `::test_a_tracked_file_replaced_by_a_link_keeps_its_committed_version`.

```python
# L94-L120 (sparse, no --allow-deletions)
merged_flat = dict(old_flat_entries)
for rel_path in new_file_map:
    if os.path.islink(full_path) or not os.path.isfile(full_path) or has_link_component(...): continue
    content = Vault__Path_Guard().read_regular(full_path, rel_path)
    if content is None: continue
    blob_id, is_large, file_hash = sub_tree.encrypt_or_reuse_blob(content, old_flat_entries.get(rel_path), read_key)
    merged_flat[rel_path] = ...
root_tree_id = sub_tree.build_from_flat(merged_flat, read_key, opaque=opaque)
```
- **What:** Sparse: start from HEAD's entries, overlay what is on disk — nothing is ever deleted. Each file is re-read via `read_regular` (second read after the scan; a link swapped in between is refused by `O_NOFOLLOW`, L4).
- **Assumes:** `encrypt_or_reuse_blob` (`Vault__Sub_Tree.py:L216-L228`) reuses the old blob when `content_hash` matches the **old entry's claim** — for this clone's own history that is its own claim.

```python
# L121-L129 (full)
root_tree_id = sub_tree.build(directory, new_file_map, read_key, old_flat_entries=old_flat_entries, opaque=opaque)
```
- **What:** `Vault__Sub_Tree.build` (L26-L67) re-reads every file: a path with a link component keeps its committed entry (L48-L50); `read_regular` (L51) raises on unreadable (B2) or returns `None` for a link/FIFO swapped in since the scan, in which case the committed entry is kept (L52-L54). Deleted = absent from `new_file_map` (so absent from `_populate_dir_contents`, L38-L39).

```python
# L146, L164-L172
signing_key = self._load_signing_key(key_manager, branch_meta, storage, directory)
commit_id   = vault_commit.create_commit(..., signing_key=signing_key, author_key_id=str(branch_meta.public_key_id) if (signing_key and branch_meta.public_key_id) else None)
ref_manager.write_ref(ref_id, commit_id, read_key)
```
- **What:** Sign with this clone's local private key (or warn and commit unsigned); move the clone ref.
- **Assumes:** `branch_meta.public_key_id` names the key pair `create_clone_branch` made; `_load_signing_key` reads `local/<id>.pem` (`load_private_key_locally`, plaintext PEM on disk, 0600).

**Cross-Function Dependencies:**
- Callees: `_scan_local_directory`, `Vault__Secret_Guard.refuse_files`, `Vault__Sub_Tree.build`/`build_from_flat`/`encrypt_or_reuse_blob`, `Vault__Path_Guard.read_regular`/`has_link_component`, `_load_signing_key`, `Vault__Commit.create_commit`, `Vault__Ref_Manager.write_ref`, `_amend_plan` (out of slice).
- Callers: `CLI__Vault.cmd_commit` (L782+, not read), `cmd_init` L401 ("Commit all existing files now?"), `Vault__Sync.rekey_commit`, `Vault__Ignore__Apply` does its own commit.
- Shared state: clone ref, object store, merge state.

**Open Questions:**
- unclear; `refuse_files` runs on `changed` computed from `new_file_map`, but the sparse path re-reads files individually and the full path re-reads inside `build` — a file replaced *between* the guard and the read (TOCTOU) would be committed unguarded. `read_regular`'s `O_NOFOLLOW` closes the link variant; a plain file swap is not addressed by anything found. Same-user attacker only (A6 can plant files; threat model §3).
