"""Vault__Path_Guard — contains attacker-influenced paths to a destination directory.

Vault tree-entry names and transfer-archive member names are chosen by whoever
authored the vault, not by the receiving user. Writing them with a bare
``os.path.join(dest, name)`` allows path traversal: an absolute path discards
``dest`` entirely, and ``../`` segments escape it. This guard rejects both and
verifies the resolved target stays under ``dest``, so a hostile name can never
overwrite files outside the working copy.

Lives in the storage layer (with its exception) so both storage and core can
use it without breaking the storage-must-not-import-core dependency rule.
"""
import os
from   osbot_utils.type_safe.Type_Safe   import Type_Safe


class Vault__Unsafe_Path_Error(Exception):
    """Raised when a vault- or archive-supplied path would escape the working directory."""

    def __init__(self, message: str = 'refusing path that escapes the destination directory'):
        super().__init__(message)


class Vault__Path_Guard(Type_Safe):

    def is_safe(self, base_dir: str, rel_path: str) -> bool:
        """True if rel_path stays within base_dir; never raises."""
        try:
            self.safe_join(base_dir, rel_path)
            return True
        except Vault__Unsafe_Path_Error:
            return False

    def safe_join(self, base_dir: str, rel_path: str) -> str:
        """Join rel_path onto base_dir, or raise Vault__Unsafe_Path_Error.

        Rejects: empty paths, absolute paths (POSIX or Windows), any '..'
        component (checked against BOTH separators, so a Windows-style
        '..\\..\\x' is caught on POSIX too), and any path whose resolved
        location is not inside base_dir. Returns the absolute, contained path.

        The join uses the ORIGINAL rel_path, never a separator-normalised copy:
        on POSIX a backslash is a legal filename character, so rewriting '\\'
        to '/' would silently turn the file 'weird\\name.txt' into the
        directory 'weird/name.txt'. Normalisation is used only for detection.
        """
        raw = '' if rel_path is None else str(rel_path)
        if not raw.strip():
            raise Vault__Unsafe_Path_Error(f'refusing empty path: {rel_path!r}')
        if raw.startswith('/') or raw.startswith('\\') or os.path.isabs(raw):
            raise Vault__Unsafe_Path_Error(f'refusing absolute path: {rel_path!r}')

        # Detection only — split on both separators so traversal is caught on any platform.
        if any(part == '..' for part in raw.replace('\\', '/').split('/')):
            raise Vault__Unsafe_Path_Error(f'refusing parent-directory traversal: {rel_path!r}')

        base_abs = os.path.abspath(base_dir)
        full     = os.path.abspath(os.path.join(base_abs, raw))   # original path, not normalised
        if full != base_abs and not full.startswith(base_abs + os.sep):
            raise Vault__Unsafe_Path_Error(
                f'refusing path escaping destination {base_dir!r}: {rel_path!r}')
        return full
