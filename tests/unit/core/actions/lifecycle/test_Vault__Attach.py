"""P9 — sgit vault attach: bind a key to an existing bare/ checkout."""
import json
import os
import shutil
import tempfile

import pytest

from sgit_ai.crypto.Vault__Crypto                    import Vault__Crypto
from sgit_ai.core.Vault__Sync                        import Vault__Sync
from sgit_ai.core.actions.lifecycle.Vault__Attach    import Vault__Attach
from sgit_ai.core.actions.publish.Vault__Publish     import Vault__Publish
from sgit_ai.network.api.Vault__API__In_Memory       import Vault__API__In_Memory
from sgit_ai.schemas.Schema__Clone_Mode              import Schema__Clone_Mode


class Test_Vault__Attach:

    def setup_method(self):
        self.crypto = Vault__Crypto()
        self.api    = Vault__API__In_Memory()
        self.api.setup()
        self.sync   = Vault__Sync(crypto=self.crypto, api=self.api)
        self.tmp    = tempfile.mkdtemp()
        origin      = os.path.join(self.tmp, 'origin')
        result      = self.sync.init(origin)
        self.vault_key = result['vault_key']
        self.vault_id  = result['vault_id']
        with open(os.path.join(origin, 'hello.txt'), 'w') as f:
            f.write('hi')
        self.sync.commit(origin, 'initial')
        self.sync.push(origin)
        self.keys = self.crypto.derive_keys_from_vault_key(self.vault_key)
        # the fresh-git-clone shape: work tree + bare/, NO local/
        self.checkout = os.path.join(self.tmp, 'checkout')
        os.makedirs(self.checkout)
        with open(os.path.join(self.checkout, 'hello.txt'), 'w') as f:
            f.write('hi')
        shutil.copytree(os.path.join(origin, '.sg_vault', 'bare'),
                        os.path.join(self.checkout, '.sg_vault', 'bare'))
        self.attach = Vault__Attach(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _local(self, name):
        return os.path.join(self.checkout, '.sg_vault', 'local', name)

    def test_read_only_attach_writes_schema_exact_clone_mode(self):
        result = self.attach.attach(self.checkout, read_key=self.keys['read_key'],
                                    vault_id=self.vault_id)
        assert result['mode'] == 'read-only'
        with open(self._local('clone_mode.json')) as f:
            raw = json.load(f)
        clone_mode = Schema__Clone_Mode.from_json(raw)     # the shipped guard's parser
        assert clone_mode.json() == raw                    # F6b: schema-exact or refused
        assert str(clone_mode.vault_id)    == self.vault_id
        assert str(clone_mode.branch_name) == 'current'
        assert not os.path.isfile(self._local('vault_key'))

    def test_read_write_attach_writes_vault_key(self):
        result = self.attach.attach(self.checkout, vault_key=self.vault_key)
        assert result['mode'] == 'read-write'
        assert os.path.isfile(self._local('vault_key'))
        assert not os.path.isfile(self._local('clone_mode.json'))

    def test_attach_is_mode_exclusive_both_directions(self):
        self.attach.attach(self.checkout, read_key=self.keys['read_key'],
                           vault_id=self.vault_id)
        self.attach.attach(self.checkout, vault_key=self.vault_key)      # RO -> RW
        assert os.path.isfile(self._local('vault_key'))
        assert not os.path.isfile(self._local('clone_mode.json'))        # F6a
        self.attach.attach(self.checkout, read_key=self.keys['read_key'],
                           vault_id=self.vault_id)                       # RW -> RO
        assert os.path.isfile(self._local('clone_mode.json'))
        assert not os.path.isfile(self._local('vault_key'))

    def test_wrong_key_refused_with_nothing_written(self):
        wrong = 'sgit_private_vault_wrongpassphrase123456:' + self.vault_id
        with pytest.raises(RuntimeError) as exc:
            self.attach.attach(self.checkout, vault_key=wrong)
        message = str(exc.value)
        assert 'not found in bare/refs' in message
        assert 'wrong key for this store' in message
        assert 'Nothing written.' in message                             # load-bearing string
        assert not os.path.isdir(os.path.join(self.checkout, '.sg_vault', 'local'))

    def test_not_a_vault_checkout_refused(self):
        empty = os.path.join(self.tmp, 'not_a_vault')
        os.makedirs(empty)
        with pytest.raises(RuntimeError) as exc:
            self.attach.attach(empty, vault_key=self.vault_key)
        assert 'no bare/refs' in str(exc.value)

    def test_after_attach_status_publish_and_serve_work(self):
        self.attach.attach(self.checkout, vault_key=self.vault_key)
        status = self.sync.status(self.checkout)
        assert status['clean'] is True
        publish = Vault__Publish(crypto=self.crypto, api=self.api).publish(self.checkout)
        assert publish['vault_id'] == self.vault_id
        from sgit_ai.core.serve.Vault__Static_Server import Vault__Static_Server
        from sgit_ai.safe_types.Safe_UInt__Port import Safe_UInt__Port
        server = Vault__Static_Server(
            root_dir=os.path.join(self.checkout, '.sg_vault', 'publish'),
            bare_dir=os.path.join(self.checkout, '.sg_vault', 'bare'),
            vault_id=self.vault_id, port=Safe_UInt__Port(0), quiet=True)
        port = server.start()
        try:
            import urllib.request
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/manifest.json',
                                        timeout=10) as response:
                assert response.status == 200
        finally:
            server.stop()

    def test_read_only_attach_gives_read_only_clone_semantics(self):
        self.attach.attach(self.checkout, read_key=self.keys['read_key'],
                           vault_id=self.vault_id)
        status = self.sync.status(self.checkout)
        assert status['clean'] is True
        with pytest.raises(Exception):
            self.sync.write_file(self.checkout, 'x.txt', b'nope')       # no write credential
