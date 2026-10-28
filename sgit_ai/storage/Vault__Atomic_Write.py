"""Vault__Atomic_Write — a file another process sees whole or not at all.

Object files used to be written in place (`open(path, 'wb')`), so a second sgit
process on the same store (a worktree, a status beside a pull) could read half an
object, and the object store's compare-before-write could report a false id
collision. The bytes now go to a temp file that is renamed over the target.

The temp file lives in `.sg_vault/local/tmp/` when the caller passes it, not beside
the target: several commands walk `bare/` and upload every file they find, and a
temp file left by a crash must never be one of them. A rename across filesystems
(EXDEV) falls back to a temp file in the target's own folder.

No fsync: objects are content-addressed, so a crash can only leave an object
missing or truncated, which fails its GCM tag on decrypt and its address in fsck,
and is fetched again; an fsync per object would cost seconds on a 300,000-object
clone. Secrets are written by Vault__Secret_File, which does fsync.
"""
import errno
import os
import secrets
from   osbot_utils.type_safe.Type_Safe import Type_Safe

TMP_PREFIX = '.tmp-'


class Vault__Atomic_Write(Type_Safe):

    def write(self, path: str, data: bytes, tmp_dir: str = None) -> None:
        folder  = os.path.dirname(path) or '.'
        staging = tmp_dir or folder
        os.makedirs(folder,  exist_ok=True)
        os.makedirs(staging, exist_ok=True)
        tmp = self.write_temp(staging, data)
        try:
            os.replace(tmp, path)
        except OSError as error:
            self.discard(tmp)
            if error.errno != errno.EXDEV or staging == folder:
                raise
            tmp = self.write_temp(folder, data)
            try:
                os.replace(tmp, path)
            except BaseException:
                self.discard(tmp)
                raise

    def write_temp(self, folder: str, data: bytes) -> str:
        """A new file created with O_EXCL (never an existing file or a link) and mode
        0666 & ~umask, the mode `open(path, 'wb')` gave the object files before."""
        tmp   = os.path.join(folder, f'{TMP_PREFIX}{os.getpid()}-{secrets.token_hex(8)}')
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
        fd    = os.open(tmp, flags, 0o666)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
        except BaseException:
            self.discard(tmp)
            raise
        return tmp

    def discard(self, path: str) -> None:
        try:
            os.unlink(path)
        except OSError:
            pass

    def tmp_dir_of(self, sg_dir: str) -> str:
        """The staging folder for a `.sg_vault` folder: inside `local/`, which no
        store walk uploads."""
        return os.path.join(sg_dir, 'local', 'tmp')
