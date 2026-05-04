"""Shared vault test environment with class-level snapshot/restore.

Usage in a test class:

    class Test_Something:
        _env = None

        @classmethod
        def setup_class(cls):
            cls._env = Vault__Test_Env()
            cls._env.setup_single_vault()   # or setup_two_clones()

        def setup_method(self):
            self.env = self._env.restore()

        def teardown_method(self):
            self.env.cleanup()

Each call to restore() returns a fresh Vault__Test_Env_Snapshot whose
directories are independent shutil.copytree copies of the snapshot, and
whose API contains a deep copy of the snapshot store dict.  This gives
~3 ms restore time vs ~400 ms full vault init.
"""
import copy
import os
import shutil
import tempfile

from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.sync.Vault__Sync          import Vault__Sync


class Vault__Test_Env_Snapshot:
    """A single test's isolated copy of vault state, returned by restore()."""

    def __init__(self):
        self.tmp_dir    = None   # base temp dir for this snapshot's copies
        self.api        = None   # Vault__API__In_Memory with snapshot store
        self.crypto     = None   # shared Vault__Crypto instance
        self.sync       = None   # Vault__Sync(crypto, api)
        self.vault_dir  = None   # single-vault path (setup_single_vault)
        self.alice_dir  = None   # Alice's clone path (setup_two_clones)
        self.bob_dir    = None   # Bob's clone path   (setup_two_clones)
        self.vault_key  = None   # vault key string
        self.commit_id  = None   # HEAD commit id after setup

    def cleanup(self):
        if self.tmp_dir and os.path.isdir(self.tmp_dir):
            shutil.rmtree(self.tmp_dir, ignore_errors=True)


class Vault__Test_Env:
    """Class-level shared vault environment; call setup_* once, restore() per test."""

    # ------------------------------------------------------------------ #
    # Internal snapshot storage
    # ------------------------------------------------------------------ #

    def __init__(self):
        self._snapshot_dir   = None   # the golden directory tree
        self._snapshot_store = None   # deep copy of API._store at snapshot time
        self._vault_key      = None
        self._commit_id      = None
        self._mode           = None   # 'single' or 'two_clones'
        self._alice_sub      = None   # subdir name for alice within snapshot_dir
        self._bob_sub        = None   # subdir name for bob within snapshot_dir
        self._vault_sub      = None   # subdir name for vault within snapshot_dir

    # ------------------------------------------------------------------ #
    # Setup methods — call ONCE per class
    # ------------------------------------------------------------------ #

    def setup_single_vault(self, files=None, vault_key=None):
        """Init a vault, write files (if any), commit, push; snapshot result."""
        crypto = Vault__Crypto()
        api    = Vault__API__In_Memory()
        api.setup()
        sync   = Vault__Sync(crypto=crypto, api=api)

        snap_dir  = tempfile.mkdtemp()
        vault_dir = os.path.join(snap_dir, 'vault')

        init_result = sync.init(vault_dir, vault_key=vault_key)
        vk = init_result['vault_key']

        if files:
            for rel_path, content in files.items():
                full = os.path.join(vault_dir, rel_path)
                parent = os.path.dirname(full)
                if parent and not os.path.isdir(parent):
                    os.makedirs(parent, exist_ok=True)
                mode = 'wb' if isinstance(content, bytes) else 'w'
                with open(full, mode) as fh:
                    fh.write(content)
            commit_result = sync.commit(vault_dir, message='initial commit')
            sync.push(vault_dir)
            commit_id = commit_result['commit_id']
        else:
            # Push the bare skeleton so remote has the branch refs
            sync.push(vault_dir)
            commit_id = None

        # Snapshot
        self._snapshot_dir   = snap_dir
        self._snapshot_store = copy.deepcopy(api._store)
        self._vault_key      = vk
        self._commit_id      = commit_id
        self._mode           = 'single'
        self._vault_sub      = 'vault'

    def setup_two_clones(self, files=None):
        """Init a vault as Alice (commit+push), then clone as Bob; snapshot both."""
        crypto = Vault__Crypto()
        api    = Vault__API__In_Memory()
        api.setup()
        alice_sync = Vault__Sync(crypto=crypto, api=api)
        bob_sync   = Vault__Sync(crypto=crypto, api=api)

        snap_dir  = tempfile.mkdtemp()
        alice_dir = os.path.join(snap_dir, 'alice')
        bob_dir   = os.path.join(snap_dir, 'bob')

        init_result = alice_sync.init(alice_dir)
        vk          = init_result['vault_key']

        # Always write at least a seed file so the vault has content
        seed_files = files or {'init.txt': 'init'}
        for rel_path, content in seed_files.items():
            full = os.path.join(alice_dir, rel_path)
            parent = os.path.dirname(full)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent, exist_ok=True)
            mode = 'wb' if isinstance(content, bytes) else 'w'
            with open(full, mode) as fh:
                fh.write(content)

        commit_result = alice_sync.commit(alice_dir, message='initial commit')
        alice_sync.push(alice_dir)
        commit_id = commit_result['commit_id']

        bob_sync.clone(vk, bob_dir)

        # Snapshot
        self._snapshot_dir   = snap_dir
        self._snapshot_store = copy.deepcopy(api._store)
        self._vault_key      = vk
        self._commit_id      = commit_id
        self._mode           = 'two_clones'
        self._alice_sub      = 'alice'
        self._bob_sub        = 'bob'

    # ------------------------------------------------------------------ #
    # restore() — returns a fresh isolated snapshot for one test
    # ------------------------------------------------------------------ #

    def restore(self):
        """Return a fresh Vault__Test_Env_Snapshot (~3 ms)."""
        snap = Vault__Test_Env_Snapshot()
        snap.tmp_dir   = tempfile.mkdtemp()
        snap.crypto    = Vault__Crypto()
        snap.vault_key = self._vault_key
        snap.commit_id = self._commit_id

        # Restore API state
        snap.api = Vault__API__In_Memory()
        snap.api.setup()
        snap.api._store = copy.deepcopy(self._snapshot_store)

        # Rebuild a sync pointing at the restored API
        snap.sync = Vault__Sync(crypto=snap.crypto, api=snap.api)

        # Copy directory trees
        if self._mode == 'single':
            src = os.path.join(self._snapshot_dir, self._vault_sub)
            dst = os.path.join(snap.tmp_dir, self._vault_sub)
            shutil.copytree(src, dst)
            snap.vault_dir = dst

        elif self._mode == 'two_clones':
            alice_src = os.path.join(self._snapshot_dir, self._alice_sub)
            bob_src   = os.path.join(self._snapshot_dir, self._bob_sub)
            alice_dst = os.path.join(snap.tmp_dir, self._alice_sub)
            bob_dst   = os.path.join(snap.tmp_dir, self._bob_sub)
            shutil.copytree(alice_src, alice_dst)
            shutil.copytree(bob_src,   bob_dst)
            snap.alice_dir = alice_dst
            snap.bob_dir   = bob_dst

        return snap

    # ------------------------------------------------------------------ #
    # Cleanup the golden snapshot (call in teardown_class if desired)
    # ------------------------------------------------------------------ #

    def cleanup_snapshot(self):
        if self._snapshot_dir and os.path.isdir(self._snapshot_dir):
            shutil.rmtree(self._snapshot_dir, ignore_errors=True)
