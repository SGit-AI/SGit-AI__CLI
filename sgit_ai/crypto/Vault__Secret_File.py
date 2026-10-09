"""Vault__Secret_File — the one way a secret reaches disk.

Vault key, read key (clone_mode.json), access token, signing keys, backups that
carry a key. Lives in the crypto layer so both crypto (key stores) and storage can
use it without breaking the storage-must-not-be-imported-by-crypto rule.
"""
import os
import tempfile
from   osbot_utils.type_safe.Type_Safe import Type_Safe


class Vault__Secret_File(Type_Safe):

    def write(self, path: str, data) -> None:
        """Written to a fresh temp file created 0600 (O_EXCL) in the same folder, then
        renamed over the target: whatever the umask, the bytes are never readable by
        others, an existing file never keeps its old mode, and a symlink at the path
        is replaced, never written through. (On Windows the mode bits are not
        enforced; the folder's ACL applies.)"""
        folder = os.path.dirname(path) or '.'
        os.makedirs(folder, exist_ok=True)
        payload = data.encode() if isinstance(data, str) else data
        fd, tmp = tempfile.mkstemp(dir=folder, prefix='.tmp-secret-')
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())                     # on disk before the rename makes it the file
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
