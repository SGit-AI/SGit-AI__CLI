# Trivial constructors in sgit_ai/storage/Vault__Path_Guard.py

## `Vault__Unsafe_Path_Error.__init__` (L55-L56)
Stores a message with a default `'refusing path that escapes the destination directory'`. Raised only by `safe_join` (L129, L132, L134, L138, L143, L146, L149), `Vault__Sync__Commit._write_targets` (L346, L350) and `Vault__Static_Server._resolve` (L123, NUL byte). Caught by: `is_safe` L86, `Vault__Verified_Write.save` L83, `Vault__Mirror` L93/L167. Messages embed `rel_path!r` — an attacker-chosen string reaches stderr/HTTP error bodies via `repr`, which escapes control characters.

## `Vault__Unreadable_File_Error.__init__` (L64-L68)
Stores `rel_path` as an attribute (used by `Vault__Sync__Base` L418-L422, L443-L448 to collect unreadable paths for status) and a fixed message. Raised only by `read_regular` (L200, L215, L224) and `Vault__Sync__Base.unlistable` (L420). Not a subclass of `OSError`, so a caller's generic `except OSError` does not swallow it; `except Exception` does (e.g. `Vault__Head_Paths.flat` L70, `Vault__Sync__Base._linked_tracked_paths` L500).
