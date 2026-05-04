"""Direct instantiation tests for Vault__Sync__GC_Ops (Tightening 5)."""
from sgit_ai.core.actions.gc.Vault__Sync__GC_Ops  import Vault__Sync__GC_Ops
from tests.unit.sync.vault_test_env    import Vault__Test_Env


class Test_Vault__Sync__GC_Ops__Direct:
    """Instantiate Vault__Sync__GC_Ops directly, not via the Vault__Sync facade."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'hello'})

    def setup_method(self):
        self.env    = self._env.restore()
        self.gc_ops = Vault__Sync__GC_Ops(crypto=self.env.crypto, api=self.env.api)

    def teardown_method(self):
        self.env.cleanup()

    def test_direct_instantiation(self):
        assert isinstance(self.gc_ops, Vault__Sync__GC_Ops)

    def test_gc_drain_returns_dict(self):
        result = self.gc_ops.gc_drain(self.env.vault_dir)
        assert isinstance(result, dict)

    def test_gc_drain_no_pending_returns_zero(self):
        result = self.gc_ops.gc_drain(self.env.vault_dir)
        assert result['drained'] == 0
        assert result['packs']   == []

    def test_create_change_pack_returns_pack_id(self):
        result = self.gc_ops.create_change_pack(
            self.env.vault_dir, {'new.txt': b'hello from change pack'})
        assert result['pack_id'].startswith('pack-')

    def test_create_change_pack_stores_all_files(self):
        result = self.gc_ops.create_change_pack(
            self.env.vault_dir,
            {'f1.txt': b'content 1', 'f2.txt': b'content 2', 'f3.txt': b'content 3'})
        assert len(result['file_ids']) == 3
        assert len(result['entries'])  == 3

    def test_gc_drain_after_change_pack_drains_one(self):
        self.gc_ops.create_change_pack(self.env.vault_dir, {'cp.txt': b'data'})
        result = self.gc_ops.gc_drain(self.env.vault_dir)
        assert result['drained'] == 1
