"""The locally-stored signing key is plaintext PEM, so its file mode is the only
thing protecting it from other local users. It must be 0600 regardless of umask."""
import os
import shutil
import stat
import tempfile

from sgit_ai.crypto.PKI__Crypto        import PKI__Crypto
from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.crypto.Vault__Key_Manager import Vault__Key_Manager


class Test_Vault__Key_Manager__Permissions:

    def setup_method(self):
        self.tmp   = tempfile.mkdtemp()
        self.km    = Vault__Key_Manager(vault_path=os.path.join(self.tmp, '.sg_vault'),
                                        crypto=Vault__Crypto(), pki=PKI__Crypto())
        self.local = os.path.join(self.tmp, '.sg_vault', 'local')

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _store_under_umask(self, umask_value: int) -> str:
        old = os.umask(umask_value)
        try:
            private_key, _ = self.km.generate_branch_key_pair()
            self.km.store_private_key_locally('key-rnd-imm-aabbccdd', private_key, self.local)
        finally:
            os.umask(old)
        return os.path.join(self.local, 'key-rnd-imm-aabbccdd.pem')

    def test_private_key_pem_is_0600(self):
        path = self._store_under_umask(0o022)
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode == 0o600, f'expected 0600, got {oct(mode)}'

    def test_private_key_pem_is_0600_even_under_permissive_umask(self):
        # umask 000 would otherwise yield a world-readable 0666 file
        path = self._store_under_umask(0o000)
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode == 0o600, f'expected 0600 under permissive umask, got {oct(mode)}'
        assert not (mode & stat.S_IRGRP), 'signing key is group-readable'
        assert not (mode & stat.S_IROTH), 'signing key is world-readable'

    def test_key_still_loads_after_permission_hardening(self):
        path = self._store_under_umask(0o022)
        assert os.path.isfile(path)
        loaded = self.km.load_private_key_locally('key-rnd-imm-aabbccdd', self.local)
        assert loaded is not None
