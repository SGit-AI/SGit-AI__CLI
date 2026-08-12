"""Vault__Path_Guard — contains attacker-influenced paths to a destination directory.

Vault tree-entry names and transfer-archive member names are chosen by whoever
authored the vault or sent the transfer, not by the receiving user. Writing them
with a bare ``os.path.join(dest, name)`` allows path traversal: an absolute path
discards ``dest`` entirely, and ``../`` segments escape it. This guard rejects
both and verifies the resolved target stays under ``dest``, so a hostile name can
never overwrite files outside the working copy.
"""
import os
from   osbot_utils.type_safe.Type_Safe   import Type_Safe
from   sgit_ai.core.Vault__Errors         import Vault__Unsafe_Path_Error


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
        component, and any path whose resolved location is not inside base_dir.
        Returns the absolute, contained path on success.
        """
        norm = (rel_path or '').replace('\\', '/').strip()
        if not norm:
            raise Vault__Unsafe_Path_Error(f'refusing empty path: {rel_path!r}')
        if norm.startswith('/') or os.path.isabs(norm) or os.path.isabs(rel_path):
            raise Vault__Unsafe_Path_Error(f'refusing absolute path: {rel_path!r}')

        parts = norm.split('/')
        if any(part == '..' for part in parts):
            raise Vault__Unsafe_Path_Error(f'refusing parent-directory traversal: {rel_path!r}')

        base_abs = os.path.abspath(base_dir)
        full     = os.path.abspath(os.path.join(base_abs, norm))
        if full != base_abs and not full.startswith(base_abs + os.sep):
            raise Vault__Unsafe_Path_Error(
                f'refusing path escaping destination {base_dir!r}: {rel_path!r}')
        return full
