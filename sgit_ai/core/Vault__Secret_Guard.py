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

SECRET_ENTRY = re.compile(r'(^|/)VAULT-KEY$|(^|/)(\.sg_vault/)?local/(vault_key|token|[^/]+\.pem)$')
ZIP_MAGIC    = b'PK\x03\x04'


class Vault__Secret_Guard(Type_Safe):

    def refuse_files(self, directory: str, rel_paths) -> None:
        local_inodes = None
        for rel_path in sorted(rel_paths):
            full = os.path.join(directory, rel_path)
            try:
                st = os.lstat(full)
            except OSError:
                continue
            if st.st_nlink > 1:
                if local_inodes is None:
                    local_inodes = self._local_inodes(directory)
                if (st.st_dev, st.st_ino) in local_inodes:
                    raise Vault__Secret_In_Commit_Error(
                        f'refusing to commit {rel_path}: it is a hard link to {local_inodes[(st.st_dev, st.st_ino)]}, '
                        f'one of this clone\'s secrets. Remove the link.')
            if self._looks_like_zip(full):
                with open(full, 'rb') as f:
                    self.refuse_bytes(rel_path, f.read())

    def refuse_bytes(self, rel_path: str, content: bytes) -> None:
        if not content.startswith(ZIP_MAGIC):
            return
        entry = self._secret_entry(content)
        if entry:
            raise Vault__Secret_In_Commit_Error(
                f'refusing to commit {rel_path}: it is a zip holding {entry} (a vault backup carries the '
                f'plaintext vault key or a signing key). Move it out of the vault folder; '
                f'`sgit init --restore` finds backups named .vault__*.zip, which are never committed.')

    def _secret_entry(self, content: bytes) -> str:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for name in zf.namelist():
                    if SECRET_ENTRY.search(name.replace('\\', '/')):
                        return name
        except (zipfile.BadZipFile, OSError, ValueError):
            return ''
        return ''

    def _looks_like_zip(self, full: str) -> bool:
        try:
            with open(full, 'rb') as f:
                return f.read(4) == ZIP_MAGIC
        except OSError:
            return False

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
