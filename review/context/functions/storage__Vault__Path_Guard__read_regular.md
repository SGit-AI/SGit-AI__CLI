## `read_regular` in sgit_ai/storage/Vault__Path_Guard.py (L183-L227)

```python
# L194-L227
rel_path = rel_path or full_path
try:
    mode = os.lstat(full_path).st_mode
except FileNotFoundError:
    return None
except OSError as error:
    raise Vault__Unreadable_File_Error(rel_path, ...)
if _stat.S_ISSOCK(mode) or _stat.S_ISFIFO(mode) or _stat.S_ISCHR(mode) or _stat.S_ISBLK(mode):
    self.warn_not_regular(rel_path); return None
flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)
try:
    fd = os.open(full_path, flags)
except FileNotFoundError:
    return None
except OSError as error:
    if error.errno == errno.ELOOP or self.is_link(full_path): return None
    if error.errno == errno.ENXIO: self.warn_not_regular(rel_path); return None
    raise Vault__Unreadable_File_Error(rel_path, ...)
try:
    if not _stat.S_ISREG(os.fstat(fd).st_mode):
        self.warn_not_regular(rel_path); return None
    with os.fdopen(fd, 'rb') as f:
        fd = None
        return f.read()
except OSError as error:
    raise Vault__Unreadable_File_Error(rel_path, ...)
finally:
    if fd is not None: os.close(fd)
```

**Purpose:** The one way working-copy bytes are read for hashing, committing, stashing, diffing and secret-scanning. Returns the bytes of a regular file; `None` for "nothing to record" (gone, a link, a FIFO/socket/device); raises `Vault__Unreadable_File_Error` for anything else so an unreadable file is never recorded as deleted (docstring L184-L191; review B2, L4, 3e099ee N1).

**Inputs & Assumptions:**
- `full_path` (str): absolute path from a walk or a join. Trust: name is filesystem-derived (A6).
- `rel_path` (str, optional): for messages; defaults to `full_path` (L194).
- Implicit: live filesystem; `O_NOFOLLOW`/`O_NONBLOCK` availability (`getattr(os, ..., 0)` → on a platform without them the flags are 0 and the protections silently vanish; Windows has neither, so there the link check degrades to the `is_link` fallback at L210).
- Precondition: none.

**Outputs & Effects:**
- Returns bytes, or `None` (L198, L203, L208, L211, L214, L219).
- Raises `Vault__Unreadable_File_Error` (L200, L215, L224).
- Side effect: one stderr warning per `rel_path` per process via `warn_not_regular` (L202, L213, L218).
- Postcondition on bytes: they were read from a descriptor whose `fstat` said regular (L217), opened without following a final-component link (L204).

**Block-by-Block:**

```python
# L195-L200  lstat
```
- **What:** Pre-check of the type at the path without following.
- **Why here:** A socket cannot even be opened (`ENXIO`), and a FIFO opened without `O_NONBLOCK` would block; identifying them first gives the right message (L201-L203).
- **Assumes:** `FileNotFoundError` means "deleted since the listing" (L198) — recorded as deletion downstream. Any other `OSError` (EACCES, EIO, Windows sharing violation) is "unreadable", refused (L200).

```python
# L204-L215  open with O_NOFOLLOW | O_NONBLOCK
```
- **What:** Opens the path itself, not a link; never blocks on a FIFO.
- **Why here:** Closes the check-then-open race for reads: a link swapped in between L196 and L206 gets `ELOOP` (L210) → `None`.
- **Assumes:** `O_NOFOLLOW` applies to the final component only (POSIX); a link in a *directory* component is followed by the kernel. Callers handle that: `Vault__Sub_Tree.make_entry` L48 and `Vault__Secret_Guard.refuse_files` L48 call `has_link_component` first; `Vault__Sync__Base._scan_local_directory` prunes link dirs from the walk (L430-L432); `Vault__Revert` L142, `Vault__Branch_Switch` L431/L454, `Vault__Diff` L819, `Vault__Stash` L213, `Vault__Bare` L113 filter files only — their directory pruning is `should_ignore_dir`, which does not test links, and `os.walk` default `followlinks=False` does not descend into link dirs, so a link directory is simply not walked. `Vault__Sync__Push._upload_bare_to_server` L795 walks `.sg_vault/bare` (not the working copy).
- `ENXIO` (L212): a socket/device swapped in since the lstat → warn, `None`.
- Any other error → refuse (L215).

```python
# L216-L227  fstat on the open fd, then read
```
- **What:** Confirms regular on the *same* file the descriptor names; reads; ownership of `fd` passes to `fdopen` (L221 sets `fd = None` so `finally` does not double-close).
- **Assumes:** nothing further.

**Cross-Function Dependencies:**
- Callee `is_link` L172 (internal) at L210 — fallback classification on platforms without `ELOOP`.
- Callee `warn_not_regular` L229 (internal).
- Callers: `Vault__Sync__Base._scan_local_directory` L442 (status/commit/push scan: `Unreadable` propagates for commit, is collected for status, L443-L448); `Vault__Sub_Tree.make_entry` L51 (commit tree build; a `None` keeps the committed entry, L52-L54); `Vault__Sync__Commit` L102 (sparse commit); `Vault__Stash` L63, L233; `Vault__Revert` L152; `Vault__Branch_Switch` L464; `Vault__Diff` L829; `Vault__Sync__Scope` L96; `Vault__Secret_Guard.refuse_files` L60; `Vault__Sync__Push._upload_bare_to_server` L795 (bare store files, `None` skipped L796-L797 — a link or FIFO planted in `.sg_vault/bare` is silently not uploaded).
- Tests: `tests/security/test_Security__Fixed__Symlinks_And_Local.py::Test_Fixed__No_Follow_Reads` (both tests); `tests/unit/review/test_Review__eed8084.py` B2 group (`test_status_lists_it_as_unreadable_not_deleted`, `test_commit_refuses_naming_the_file_and_changes_nothing`, `test_an_io_error_is_refused_the_same_way`, `test_a_fifo_at_a_tracked_path_keeps_the_committed_version`, `test_a_deleted_file_is_still_deleted`, `test_an_untracked_socket_does_not_block_commit`, `test_a_socket_at_a_tracked_path_keeps_the_committed_version`) and the source-grep `test_no_plain_open_of_working_copy_files_is_left` (L389-L396: asserts no `open((full_path|local_path|local_file), 'rb')` remains in five action modules — a textual net, not a dynamic one).
- Invariant coupling: "a file sgit cannot read is never recorded as deleted" (B2) is enforced here plus at each caller's handling of the exception; `Vault__Sync__Base` L443-L448 is the one that decides raise-vs-collect by `unreadable_out`.

**Open Questions:**
- On Windows (`O_NOFOLLOW` absent): a link swapped in between `lstat` and `open` would be opened and read; L210's `is_link` fallback runs only when `open` fails. Not covered by the hermetic suite (POSIX CI).
- `Vault__Ignore.load_gitignore` (L78-L80) and `Vault__Repo_Ignore` (L53, L56) open `.gitignore` with plain `open()`, not this function — a `.gitignore` that is a FIFO or a link is read/followed. The eed8084 grep test does not cover `sgit_ai/core/Vault__Ignore.py`.
