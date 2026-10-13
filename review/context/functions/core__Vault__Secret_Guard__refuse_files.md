## `refuse_files` in sgit_ai/core/Vault__Secret_Guard.py (L29-L62)

```python
# L36-L62
guard        = Vault__Path_Guard()
base         = os.path.abspath(directory)
allowed      = {self.normalise(directory, p) for p in (allowed or ())}
local_inodes = None
for rel_path in sorted(rel_paths):
    full = os.path.join(directory, rel_path)
    try:
        st = os.lstat(full)
    except OSError:
        continue
    if not _stat.S_ISREG(st.st_mode) or guard.has_link_component(base, os.path.abspath(full)):
        continue
    if st.st_nlink > 1:
        if local_inodes is None:
            local_inodes = self._local_inodes(directory)
        if (st.st_dev, st.st_ino) in local_inodes:
            raise Vault__Secret_In_Commit_Error(...)
    if rel_path in allowed:
        continue
    if self._looks_like_zip(full):
        content = guard.read_regular(full)
        if content is not None:
            self.refuse_bytes(rel_path, content)
```

**Purpose:** The last check before changed files enter a commit: refuse (a) a hard link to anything under `.sg_vault/local/` (vault key, signing `.pem`, token) and (b) a zip that contains a vault key or a private key — the two leaks a *name* cannot catch (module docstring L3-L10; reviews d3b8eef N1, L4; eed8084 F2, F5).

**Inputs & Assumptions:**
- `directory` (str): the vault root. Trusted.
- `rel_paths`: `changed` from `Vault__Sync__Commit.commit` L79-L81 — only paths whose content hash differs from the parent tree (so a file committed once with `--allow-secret-file` is not re-checked; F2). Trust: names are filesystem-derived (A6 can plant); the scan that produced them already dropped links and non-regular files (`_scan_local_directory` L438-L452).
- `allowed`: `--allow-secret-file` paths from the CLI; normalised (L40) so `x`, `./x`, absolute all match (docstring L32-L34). Covers the **zip check only** (L57-L58): the hard-link check runs before and is never bypassed (eed8084 F2; `tests/security/test_Security__Fixed__Secrets_In_Commits.py::test_naming_a_hard_link_to_the_vault_key_does_not_commit_it`).
- Implicit: live filesystem; inode numbers (`st_dev, st_ino`).

**Outputs & Effects:** Pure read; raises `Vault__Secret_In_Commit_Error` (`Vault__Errors.py:L106`) — the commit aborts before any object is written (caller L82 precedes tree building). Files that vanish or cannot be `lstat`ed are skipped here (L44-L47) — the earlier scan is what decides whether they are "unreadable" (B2).

**Block-by-Block:**

```python
# L43-L49  lstat; skip non-regular or under-a-link
```
- **What:** Never opens a link, FIFO or device, nor a regular file reached through a link directory (F5: a link to a FIFO hung commit; a link to a zip outside the tree was read).
- **Assumes:** `has_link_component(base, abspath(full))` and the later `_looks_like_zip`/`read_regular` see the same tree (TOCTOU as elsewhere; `read_regular`'s `O_NOFOLLOW` covers the leaf).

```python
# L50-L56  hard-link check
```
- **What:** Only for files with `st_nlink > 1`; lazily builds the `(dev, ino)` map of everything under `.sg_vault/local` (`_local_inodes` L124-L135) and refuses on a match.
- **Assumes:** (1) the secret and the link are on the same device (hard links cannot cross devices — holds); (2) `_local_inodes` lists the real secrets: it `os.walk`s `.sg_vault/local` **following nothing** (`os.walk` default) but `lstat`s each file — a *symlink* inside `local/` is recorded with the link's own inode, which is harmless. (3) The secret files are the only things a hard link could leak: a hard link to `.sg_vault/bare/data/<obj>` (ciphertext, not a secret) is not refused — fine. (4) A hard link to a secret **outside** `.sg_vault/local` (e.g. `~/.ssh/id_rsa`) is not this guard's job — `ALWAYS_IGNORED_FILES` catches that by name only; a hard link to `~/.ssh/id_rsa` named `notes.txt` is committed. `nothing found` that checks inodes against anything but `.sg_vault/local` (documented scope: "one of this clone's secrets", L56).
- **Establishes:** no committed regular file shares an inode with a `.sg_vault/local` file.

```python
# L57-L62  zip check
```
- **What:** 4-byte magic probe with `O_NOFOLLOW|O_NONBLOCK` (`_looks_like_zip` L111-L122), then the full read via `read_regular`, then `refuse_bytes`.
- **Assumes:** a secret-bearing archive starts with `PK\x03\x04` (L22). A zip with a prepended stub (self-extracting, or any leading bytes — `zipfile` itself tolerates a prefix by locating the end-of-central-directory record), a `.tar`, `.7z`, or a renamed `.tar.gz` of `.sg_vault` is **not** examined. `nothing found` beyond the magic check. The threat model's row is about "a backup under any name" — the backup `sgit` itself writes is always a plain zip (`Vault__Backup`), so the check covers sgit's own artefacts, not arbitrary archives.
- Empty-zip edge: `_looks_like_zip` reads 4 bytes; an empty zip starts with `PK\x05\x06`, not matched — contains nothing anyway.

**Cross-Function Dependencies:**
- Callees: `normalise` L105, `_local_inodes` L124, `_looks_like_zip` L111, `refuse_bytes` L64, `Vault__Path_Guard.has_link_component`, `Vault__Path_Guard.read_regular`.
- Caller: `Vault__Sync__Commit.commit` L82-L83 only. `sgit write` (`write_file`) does not call `refuse_files`; it calls `refuse_bytes(file_path, file_content)` directly at `Vault__Sync__Commit.py:L278` on the bytes it is about to commit — so the zip check applies there, the hard-link check does not (there is no on-disk file yet) and `--allow-secret-file` is not offered on that path (`tests/security/test_Security__Fixed__Secrets_In_Commits.py::test_write_file_refuses_a_backup_zip`).
- Tests: `tests/security/test_Security__Fixed__Secrets_In_Commits.py` (`test_a_renamed_backup_is_refused_by_content`, `test_a_zip_holding_a_signing_key_is_refused`, `test_an_ordinary_zip_is_committed`, `test_a_hard_link_to_the_vault_key_is_refused`, `Test_Fixed__Secret_Guard_Precision::*`, `Test_Fixed__Allow_Secret_File_Scope::*`).

**Open Questions:**
- Archive formats other than a magic-led zip (scope, not a bug claim).
