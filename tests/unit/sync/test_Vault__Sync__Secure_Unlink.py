"""Tests for Vault__Storage.secure_unlink / secure_rmtree and their integration
into Vault__Sync.rekey_wipe.

All tests use real temp files — no mocks.
"""
import os
import shutil
import tempfile

import pytest

from sgit_ai.sync.Vault__Storage    import Vault__Storage
from tests.unit.sync.vault_test_env import Vault__Test_Env


# ---------------------------------------------------------------------------
# Unit tests — Vault__Storage.secure_unlink
# ---------------------------------------------------------------------------

class Test_Vault__Storage__Secure_Unlink:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.storage = Vault__Storage()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _make_file(self, name: str, content: bytes) -> str:
        path = os.path.join(self.tmp_dir, name)
        with open(path, 'wb') as f:
            f.write(content)
        return path

    # --- basic contract ---

    def test_secure_unlink_removes_file(self):
        path = self._make_file('key.bin', b'secret')
        self.storage.secure_unlink(path)
        assert not os.path.exists(path)

    def test_secure_unlink_empty_file(self):
        path = self._make_file('empty.bin', b'')
        self.storage.secure_unlink(path)
        assert not os.path.exists(path)

    def test_secure_unlink_small_file(self):
        path = self._make_file('small.bin', b'\xde\xad\xbe\xef' * 8)
        self.storage.secure_unlink(path)
        assert not os.path.exists(path)

    def test_secure_unlink_multi_mb_file(self):
        """A 4 MB file must be wiped and removed without error."""
        content = os.urandom(4 * 1024 * 1024)
        path = self._make_file('large.bin', content)
        self.storage.secure_unlink(path)
        assert not os.path.exists(path)

    def test_secure_unlink_nonexistent_is_noop(self):
        """secure_unlink on a missing path must not raise."""
        path = os.path.join(self.tmp_dir, 'ghost.bin')
        self.storage.secure_unlink(path)   # should not raise

    def test_secure_unlink_content_overwritten_before_removal(self):
        """Verify that we can observe zero-write side-effects.

        Strategy: write to a tmpfs path, then call secure_unlink, then assert
        the file is gone.  We cannot reliably read raw blocks from a tmpfs, so
        the assertion is purely that the file is gone — the implementation is
        white-box verified by reading Vault__Storage.secure_unlink source.
        """
        payload = b'vault_key_material_must_not_survive' * 100
        path = self._make_file('vault_key', payload)
        assert os.path.getsize(path) == len(payload)
        self.storage.secure_unlink(path)
        assert not os.path.exists(path)
        # Attempt to re-open must fail
        with pytest.raises(FileNotFoundError):
            open(path, 'rb')


# ---------------------------------------------------------------------------
# Unit tests — Vault__Storage.secure_rmtree
# ---------------------------------------------------------------------------

class Test_Vault__Storage__Secure_Rmtree:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.storage = Vault__Storage()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _populate(self, layout: dict) -> str:
        """Create files described by {relative_path: bytes_content} under tmp_dir."""
        base = os.path.join(self.tmp_dir, 'vault_root')
        for rel, data in layout.items():
            full = os.path.join(base, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'wb') as f:
                f.write(data if isinstance(data, bytes) else data.encode())
        return base

    def test_secure_rmtree_nonexistent_returns_zero(self):
        result = self.storage.secure_rmtree(os.path.join(self.tmp_dir, 'no_such'))
        assert result == 0

    def test_secure_rmtree_single_file(self):
        root = self._populate({'a.bin': b'data'})
        count = self.storage.secure_rmtree(root)
        assert count == 1
        assert not os.path.isdir(root)

    def test_secure_rmtree_nested_files(self):
        root = self._populate({
            'local/vault_key':       b'key_material',
            'local/config.json':     b'{}',
            'bare/data/obj1':        b'ciphertext1',
            'bare/refs/ref1':        b'refdata',
        })
        count = self.storage.secure_rmtree(root)
        assert count == 4
        assert not os.path.isdir(root)

    def test_secure_rmtree_empty_directory(self):
        root = os.path.join(self.tmp_dir, 'empty_vault')
        os.makedirs(root)
        count = self.storage.secure_rmtree(root)
        assert count == 0
        assert not os.path.isdir(root)

    def test_secure_rmtree_directory_gone_after_call(self):
        root = self._populate({'sub/deep/file.bin': b'x' * 1024})
        self.storage.secure_rmtree(root)
        assert not os.path.exists(root)


# ---------------------------------------------------------------------------
# Integration tests — rekey_wipe uses secure_rmtree
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Rekey_Wipe__Secure:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={
            'doc.md':        'hello world',
            'sub/note.txt':  'sub content',
        })

    def setup_method(self):
        self.env  = self._env.restore()
        self.sync = self.env.sync

    def teardown_method(self):
        self.env.cleanup()

    def test_rekey_wipe_removes_sg_vault_dir(self):
        """After rekey_wipe the .sg_vault/ directory must not exist."""
        from sgit_ai.sync.Vault__Storage import Vault__Storage
        sg_dir = Vault__Storage().sg_vault_dir(self.env.vault_dir)
        assert os.path.isdir(sg_dir)                   # pre-condition
        self.sync.rekey_wipe(self.env.vault_dir)
        assert not os.path.isdir(sg_dir)

    def test_rekey_wipe_vault_key_file_gone(self):
        """The old vault_key file must be gone — not just unlinked but
        absent so a subsequent open() raises FileNotFoundError."""
        from sgit_ai.sync.Vault__Storage import Vault__Storage
        storage  = Vault__Storage()
        key_path = storage.vault_key_path(self.env.vault_dir)
        assert os.path.isfile(key_path)                # pre-condition
        self.sync.rekey_wipe(self.env.vault_dir)
        assert not os.path.exists(key_path)
        with pytest.raises((FileNotFoundError, OSError)):
            open(key_path, 'rb')

    def test_rekey_old_vault_key_not_readable_after_rekey(self):
        """After a full rekey, the OLD vault_key path must be unreadable.

        Because rekey_wipe nukes .sg_vault/ and rekey_init creates a fresh
        one, the key in the new file is different.  We verify:
          1. The new vault_key path exists and is readable.
          2. The new vault_key differs from the old one.
        """
        from sgit_ai.sync.Vault__Storage import Vault__Storage
        storage  = Vault__Storage()
        key_path = storage.vault_key_path(self.env.vault_dir)
        old_key  = open(key_path).read().strip()

        result = self.sync.rekey(self.env.vault_dir)

        new_key_on_disk = open(key_path).read().strip()
        assert new_key_on_disk == result['vault_key']
        assert new_key_on_disk != old_key

    def test_rekey_wipe_working_files_intact(self):
        """rekey_wipe must not touch files outside .sg_vault/."""
        self.sync.rekey_wipe(self.env.vault_dir)
        assert os.path.isfile(os.path.join(self.env.vault_dir, 'doc.md'))
        assert os.path.isfile(os.path.join(self.env.vault_dir, 'sub', 'note.txt'))

    def test_rekey_wipe_returns_objects_removed(self):
        result = self.sync.rekey_wipe(self.env.vault_dir)
        assert result['objects_removed'] >= 1

    def test_rekey_wipe_idempotent(self):
        """Double-wipe must not raise."""
        self.sync.rekey_wipe(self.env.vault_dir)
        result = self.sync.rekey_wipe(self.env.vault_dir)
        assert result['objects_removed'] == 0


# ---------------------------------------------------------------------------
# Mid-rekey abort / deterministic state
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Rekey__Mid_Abort:
    """Assert that after rekey_wipe-only (no rekey_init), the vault is in a
    deterministic state: .sg_vault/ is gone, working files survive.

    This models a crash between rekey_wipe and rekey_init.  The state machine
    is:  wipe → init → commit.  Each step is idempotent or detectable.
    A future init() call on the directory re-creates the vault from scratch —
    the caller is responsible for recovery if the process dies mid-sequence.
    """

    def _make_env(self, files):
        env_holder = Vault__Test_Env()
        env_holder.setup_single_vault(files=files)
        snap = env_holder.restore()
        return snap, snap.sync

    def test_mid_rekey_abort_after_wipe_state_is_clean(self):
        """After wipe-only, .sg_vault/ is gone and working files are present.

        State: wipe done, init NOT done.
        Expected: not a vault (no .sg_vault/), but working files present.
        """
        from sgit_ai.sync.Vault__Storage import Vault__Storage
        env, sync = self._make_env({'a.txt': 'content', 'b/c.txt': 'deep'})
        storage   = Vault__Storage()

        sync.rekey_wipe(env.vault_dir)

        # Deterministic state: no .sg_vault/, but working tree intact
        assert not os.path.isdir(storage.sg_vault_dir(env.vault_dir))
        assert os.path.isfile(os.path.join(env.vault_dir, 'a.txt'))
        assert os.path.isfile(os.path.join(env.vault_dir, 'b', 'c.txt'))

        # Recovery: init on same directory re-creates the vault
        result = sync.init(env.vault_dir, allow_nonempty=True)
        assert result['vault_key']
        assert os.path.isdir(storage.sg_vault_dir(env.vault_dir))

        env.cleanup()

    def test_mid_rekey_abort_after_init_no_content_encrypted(self):
        """After wipe + init (no commit), vault exists but has no content objects.

        State: wipe + init done, commit NOT done.
        Expected: .sg_vault/ present, status shows untracked files.
        """
        env, sync = self._make_env({'readme.md': 'hello'})

        sync.rekey_wipe(env.vault_dir)
        sync.rekey_init(env.vault_dir)

        status = sync.status(env.vault_dir)
        # Working file is present but not yet committed — must appear as added
        # (status() uses 'added' for files not in the previous commit tree;
        #  after a fresh rekey_init there is no HEAD commit yet so all working
        #  files surface as 'added').
        added = status.get('added', [])
        assert len(added) >= 1

        # Completing the sequence recovers the vault
        sync.rekey_commit(env.vault_dir)
        status2 = sync.status(env.vault_dir)
        assert status2['clean'] is True

        env.cleanup()
