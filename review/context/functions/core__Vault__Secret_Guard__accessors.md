# Helper methods in sgit_ai/core/Vault__Secret_Guard.py

## `_holds_private_key` (L92-L103)
Streams one zip entry in `PEM_CHUNK` (64 KiB) pieces; returns True on the first chunk where `PEM_MARKER` appears in `tail + chunk` (`tail` is the last `len(marker)-1` bytes of the previous chunk, L103, so a marker split across the boundary is found). Reads to EOF otherwise. No size cap (see `_secret_entry`). Exceptions from `zf.open`/`read` propagate to `_secret_entry`'s `except`.

## `normalise` (L105-L109)
`relpath(abspath(path or directory/path), abspath(directory)).replace(os.sep, '/')` — so `x`, `./x`, `/abs/vault/x` all become `x`, matching the scan's spelling. A path outside the vault becomes `../…` and simply never matches a `rel_path`. Caller: `refuse_files` L40. Test: `test_dot_slash_and_absolute_paths_name_the_file`.

## `_looks_like_zip` (L111-L122)
`os.open(full, O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_BINARY)` then `os.read(fd, 4) == b'PK\x03\x04'`; any `OSError` → False (so a FIFO, link, or unreadable file is "not a zip" and skipped by this check — the unreadable case was already decided by the scan). Same flags as `read_regular` (L114 comment). Caller: `refuse_files` L59.

## `_local_inodes` (L124-L135)
`os.walk(<directory>/.sg_vault/local)`; `lstat` each file; map `(st_dev, st_ino) → relpath`. Missing dir → `os.walk` yields nothing → `{}`. Built lazily and once per `refuse_files` call (L50-L52). Includes every file under `local/` — vault_key, `*.pem`, token, but also `config.json`, `reflog.jsonl`, `push_state.json`, `notices.json`, `remotes.json`, stash zips under `local/stash/` if that is where `_stash_dir` points (not read) — so a hard link to any of those is refused with the message "one of this clone's secrets" (L55-L56). Caller: `refuse_files` L52.
