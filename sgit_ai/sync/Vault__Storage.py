import os
import stat
from osbot_utils.type_safe.Type_Safe             import Type_Safe
from sgit_ai.safe_types.Safe_Str__Vault_Path import Safe_Str__Vault_Path

SG_VAULT_DIR   = '.sg_vault'
BARE_DIR       = 'bare'
LOCAL_DIR      = 'local'
BARE_DATA      = 'data'
BARE_REFS      = 'refs'
BARE_KEYS      = 'keys'
BARE_INDEXES   = 'indexes'
BARE_PENDING   = 'pending'
BARE_BRANCHES  = 'branches'
VAULT_KEY_FILE = 'vault_key'


class Vault__Storage(Type_Safe):
    vault_path : Safe_Str__Vault_Path = None

    def sg_vault_dir(self, directory: str) -> str:
        return os.path.join(directory, SG_VAULT_DIR)

    def bare_dir(self, directory: str) -> str:
        return os.path.join(directory, SG_VAULT_DIR, BARE_DIR)

    def local_dir(self, directory: str) -> str:
        return os.path.join(directory, SG_VAULT_DIR, LOCAL_DIR)

    def bare_data_dir(self, directory: str) -> str:
        return os.path.join(self.bare_dir(directory), BARE_DATA)

    def bare_refs_dir(self, directory: str) -> str:
        return os.path.join(self.bare_dir(directory), BARE_REFS)

    def bare_keys_dir(self, directory: str) -> str:
        return os.path.join(self.bare_dir(directory), BARE_KEYS)

    def bare_indexes_dir(self, directory: str) -> str:
        return os.path.join(self.bare_dir(directory), BARE_INDEXES)

    def bare_pending_dir(self, directory: str) -> str:
        return os.path.join(self.bare_dir(directory), BARE_PENDING)

    def bare_branches_dir(self, directory: str) -> str:
        return os.path.join(self.bare_dir(directory), BARE_BRANCHES)

    def create_bare_structure(self, directory: str) -> str:
        sg_dir = self.sg_vault_dir(directory)
        for sub_dir in [self.bare_data_dir(directory),
                        self.bare_refs_dir(directory),
                        self.bare_keys_dir(directory),
                        self.bare_indexes_dir(directory),
                        self.bare_pending_dir(directory),
                        self.bare_branches_dir(directory),
                        self.local_dir(directory)]:
            os.makedirs(sub_dir, exist_ok=True)
        return sg_dir

    def is_vault(self, directory: str) -> bool:
        return os.path.isdir(self.bare_dir(directory))

    @classmethod
    def find_vault_root(cls, directory: str) -> str:
        """Walk up from directory until a .sg_vault dir is found. Returns vault root or original abs path."""
        path = os.path.abspath(directory)
        while True:
            if os.path.isdir(os.path.join(path, SG_VAULT_DIR)):
                return path
            parent = os.path.dirname(path)
            if parent == path:
                return os.path.abspath(directory)
            path = parent

    def vault_key_path(self, directory: str) -> str:
        return os.path.join(self.local_dir(directory), VAULT_KEY_FILE)

    def local_config_path(self, directory: str) -> str:
        return os.path.join(self.local_dir(directory), 'config.json')

    def remotes_path(self, directory: str) -> str:
        return os.path.join(self.local_dir(directory), 'remotes.json')

    def tracking_path(self, directory: str) -> str:
        return os.path.join(self.local_dir(directory), 'tracking.json')

    def push_state_path(self, directory: str) -> str:
        return os.path.join(self.local_dir(directory), 'push_state.json')

    def clone_mode_path(self, directory: str) -> str:
        return os.path.join(self.local_dir(directory), 'clone_mode.json')

    def object_path(self, directory: str, object_id: str) -> str:
        return os.path.join(self.bare_data_dir(directory), object_id)

    def ref_path(self, directory: str, ref_id: str) -> str:
        return os.path.join(self.bare_refs_dir(directory), ref_id)

    def key_path(self, directory: str, key_id: str) -> str:
        return os.path.join(self.bare_keys_dir(directory), key_id)

    def index_path(self, directory: str, index_id: str) -> str:
        return os.path.join(self.bare_indexes_dir(directory), index_id)

    def chmod_local_file(self, path: str) -> None:
        """Restrict a .sg_vault/local/ file to owner-read/write only (0600)."""
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    def secure_unlink(self, path: str) -> None:
        """Overwrite a file's content with zero bytes then unlink it.

        Rationale: plain os.unlink / shutil.rmtree only removes the inode
        reference; the file blocks remain on disk and are recoverable with
        raw-device or undelete tools.  Best-effort overwrite + fsync reduces
        that window before the kernel hands the blocks back to the allocator.

        Residual risk: SSDs with TRIM may reallocate blocks independently of
        this call.  That risk is documented in AppSec finding F02 and is not
        addressable from userspace.

        Zero bytes are used (not os.urandom) because the goal is to destroy
        the *key material pattern*, not to pass a DoD wipe standard — and
        zeros are faster on large files with no security trade-off here.
        """
        try:
            size = os.path.getsize(path)
            with open(path, 'r+b') as fh:
                if size > 0:
                    fh.write(b'\x00' * size)
                    fh.flush()
                    os.fsync(fh.fileno())
            os.unlink(path)
        except OSError:
            pass

    def secure_rmtree(self, directory: str) -> int:
        """Secure-unlink every file under *directory*, then remove empty dirs.

        Returns the number of files wiped.  If *directory* does not exist the
        call is a no-op (returns 0).
        """
        if not os.path.isdir(directory):
            return 0
        count = 0
        # Walk bottom-up so that directories are empty when we rmdir them.
        for root, dirs, files in os.walk(directory, topdown=False):
            for fname in files:
                self.secure_unlink(os.path.join(root, fname))
                count += 1
            for dname in dirs:
                try:
                    os.rmdir(os.path.join(root, dname))
                except OSError:
                    pass
        try:
            os.rmdir(directory)
        except OSError:
            pass
        return count
