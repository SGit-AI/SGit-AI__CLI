"""Vault__Secret_Guard — the last check before a file's bytes go into a commit.

A vault's own secrets must never become vault content: once pushed, every read-key
holder has them. The path guard keeps the known names out (.sg_vault/, backup zips);
this catches what a name cannot (review d3b8eef N1, L4):

  * a zip that holds a vault key or a signing key (a backup under any name: renamed,
    copied, or written by an older sgit as <vault-id>__<ts>__uninit.zip)
  * a hard link to a file under .sg_vault/local/ (vault_key, *.pem, token): the link
    has its own name, so neither the path guard nor the symlink ban sees it
"""
import io
import os
import re
import zipfile
from osbot_utils.type_safe.Type_Safe     import Type_Safe
from sgit_ai.core.Vault__Errors          import Vault__Secret_In_Commit_Error

SECRET_ENTRY = re.compile(r'(^|/)VAULT-KEY$|(^|/)(\.sg_vault/)?local/vault_key$')        # always this vault's key
TOKEN_ENTRY  = re.compile(r'(^|/)(\.sg_vault/)?local/token$')                             # a secret inside sgit's layout
PEM_ENTRY    = re.compile(r'(^|/)(\.sg_vault/)?local/[^/]+\.pem$')                        # a secret only if it is private
ZIP_MAGIC    = b'PK\x03\x04'
PEM_MAX_READ = 64 * 1024


class Vault__Secret_Guard(Type_Safe):

    def refuse_files(self, directory: str, rel_paths, allowed=()) -> None:
        """Only regular files that are not links and not under a link are looked at: a
        tracked path held as a link to a FIFO made `commit` hang, and a link to a zip
        outside the tree was read (review 0a0707d F5). `allowed` names paths the user
        said to commit anyway (`commit --allow-secret-file PATH`, F4)."""
        import stat as _stat
        from sgit_ai.storage.Vault__Path_Guard import Vault__Path_Guard
        guard        = Vault__Path_Guard()
        base         = os.path.abspath(directory)
        allowed      = {str(p).replace(os.sep, '/') for p in (allowed or ())}
        local_inodes = None
        for rel_path in sorted(rel_paths):
            if rel_path in allowed:
                continue
            full = os.path.join(directory, rel_path)
            try:
                st = os.lstat(full)
            except OSError:
                continue
            if not _stat.S_ISREG(st.st_mode) or guard.has_link_component(base, os.path.abspath(full)):
                continue                                         # links, FIFOs, devices: never opened
            if st.st_nlink > 1:
                if local_inodes is None:
                    local_inodes = self._local_inodes(directory)
                if (st.st_dev, st.st_ino) in local_inodes:
                    raise Vault__Secret_In_Commit_Error(
                        f'refusing to commit {rel_path}: it is a hard link to {local_inodes[(st.st_dev, st.st_ino)]}, '
                        f'one of this clone\'s secrets. Remove the link.')
            if self._looks_like_zip(full):
                content = guard.read_regular(full)               # O_NOFOLLOW, never blocks (L4, F5)
                if content is not None:
                    self.refuse_bytes(rel_path, content)

    def refuse_bytes(self, rel_path: str, content: bytes) -> None:
        if not content.startswith(ZIP_MAGIC):
            return
        entry = self._secret_entry(content)
        if entry:
            raise Vault__Secret_In_Commit_Error(
                f'refusing to commit {rel_path}: it is a zip holding {entry} (a vault backup carries the '
                f'plaintext vault key or a signing key). Move it out of the vault folder; '
                f'`sgit init --restore` finds backups named .vault__*.zip, which are never committed. '
                f'If it is not a secret of this vault: sgit commit --allow-secret-file {rel_path}')

    def _secret_entry(self, content: bytes) -> str:
        """The first entry that is a secret of a vault, or ''. A `.pem` counts only when it
        holds a private key, and `local/token` only inside sgit's own layout: a bundle of
        public certificates is ordinary content (review 0a0707d F4)."""
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                names  = [n.replace('\\', '/') for n in zf.namelist()]
                layout = any(n.startswith(('bare/', '.sg_vault/')) or n in ('manifest.json', 'VAULT-KEY') for n in names)
                for raw, name in zip(zf.namelist(), names):
                    if SECRET_ENTRY.search(name) or (layout and TOKEN_ENTRY.search(name)):
                        return name
                    if PEM_ENTRY.search(name):
                        with zf.open(raw) as f:
                            if b'PRIVATE KEY' in f.read(PEM_MAX_READ):
                                return name
        except (zipfile.BadZipFile, OSError, ValueError, RuntimeError):
            return ''
        return ''

    def _looks_like_zip(self, full: str) -> bool:
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)
        try:
            fd = os.open(full, flags)                              # the same flags as read_regular (L4)
        except OSError:
            return False
        try:
            return os.read(fd, 4) == ZIP_MAGIC
        except OSError:
            return False
        finally:
            os.close(fd)

    def _local_inodes(self, directory: str) -> dict:
        local  = os.path.join(directory, '.sg_vault', 'local')
        result = {}
        for root, _, files in os.walk(local):
            for name in files:
                path = os.path.join(root, name)
                try:
                    st = os.lstat(path)
                except OSError:
                    continue
                result[(st.st_dev, st.st_ino)] = os.path.relpath(path, directory)
        return result
