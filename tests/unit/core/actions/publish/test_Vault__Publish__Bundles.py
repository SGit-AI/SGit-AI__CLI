"""P6 — bundles: ZIP_STORED, immutable names, derived-never-authoritative."""
import os
import shutil
import tempfile
import zipfile

from sgit_ai.crypto.Vault__Crypto                          import Vault__Crypto
from sgit_ai.core.Vault__Sync                              import Vault__Sync
from sgit_ai.core.actions.publish.Vault__Publish           import Vault__Publish
from sgit_ai.core.actions.publish.Vault__Publish__Bundles  import Vault__Publish__Bundles
from sgit_ai.network.api.Vault__API__In_Memory             import Vault__API__In_Memory


class Test_Vault__Publish__Bundles:

    def setup_method(self):
        self.crypto = Vault__Crypto()
        self.api    = Vault__API__In_Memory()
        self.api.setup()
        self.sync   = Vault__Sync(crypto=self.crypto, api=self.api)
        self.tmp    = tempfile.mkdtemp()
        self.vault  = os.path.join(self.tmp, 'vault')
        result      = self.sync.init(self.vault)
        self.vault_key = result['vault_key']
        for i, content in enumerate(['one', 'two']):
            with open(os.path.join(self.vault, f'file_{i}.txt'), 'w') as f:
                f.write(content)
            self.sync.commit(self.vault, f'commit {content}')
        self.sync.push(self.vault)
        self.publisher = Vault__Publish(crypto=self.crypto, api=self.api)
        self.result    = self.publisher.publish(self.vault, bundles=True)
        self.bundles   = os.path.join(self.vault, '.sg_vault', 'publish', 'bundles')

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _sg_dir(self):
        return os.path.join(self.vault, '.sg_vault')

    def test_head_snapshot_and_per_commit_deltas_exist(self):
        names = sorted(os.listdir(self.bundles))
        head  = self.result['head']
        assert f'head-{head}.zip' in names
        assert f'{head}.zip'      in names
        assert not any(name == 'latest.zip' for name in names)     # immutable names only

    def test_zip_stored_never_deflate(self):
        for name in os.listdir(self.bundles):
            with zipfile.ZipFile(os.path.join(self.bundles, name)) as bundle:
                for info in bundle.infolist():
                    assert info.compress_type == zipfile.ZIP_STORED, f'{name}:{info.filename}'

    def test_union_of_deltas_reconstructs_bare_data_exactly(self):
        union = {}
        for name in os.listdir(self.bundles):
            if name.startswith('head-'):
                continue
            with zipfile.ZipFile(os.path.join(self.bundles, name)) as bundle:
                for member in bundle.namelist():
                    union[member] = bundle.read(member)
        data_dir = os.path.join(self._sg_dir(), 'bare', 'data')
        on_disk  = {f'bare/data/{n}': open(os.path.join(data_dir, n), 'rb').read()
                    for n in os.listdir(data_dir)
                    if n.startswith('obj-cas-imm-')}
        # every reachable object appears exactly once across the deltas
        assert union == {k: v for k, v in on_disk.items() if k in union}
        reachable = set(union)
        for member in on_disk:
            assert member in reachable, f'{member} missing from the delta union'

    def test_extraction_is_id_verified_and_corrupt_bundle_degrades(self):
        head_zip = os.path.join(self.bundles, f'head-{self.result["head"]}.zip')
        builder  = Vault__Publish__Bundles(crypto=self.crypto, api=self.api)
        clean    = os.path.join(self.tmp, 'clean_store')
        result   = builder.extract_verified(head_zip, clean)
        assert result['refused'] == []
        assert result['extracted'] > 0

        corrupt_zip = os.path.join(self.tmp, 'corrupt.zip')
        with zipfile.ZipFile(head_zip) as source, \
             zipfile.ZipFile(corrupt_zip, 'w', compression=zipfile.ZIP_STORED) as target:
            members = sorted(source.namelist())
            for i, member in enumerate(members):
                data = source.read(member) if i else b'tampered bytes'
                target.writestr(member, data)
        hostile = os.path.join(self.tmp, 'hostile_store')
        result  = builder.extract_verified(corrupt_zip, hostile)
        assert result['refused'] == [members[0]]                   # per object, not per run
        assert result['extracted'] == len(members) - 1
        refused_path = os.path.join(hostile, members[0])
        assert not os.path.exists(refused_path)                    # never written

    def test_bundles_are_deterministic(self):
        first = {}
        for name in os.listdir(self.bundles):
            with open(os.path.join(self.bundles, name), 'rb') as f:
                first[name] = f.read()
        self.publisher.publish(self.vault, bundles=True)
        for name, data in first.items():
            with open(os.path.join(self.bundles, name), 'rb') as f:
                assert f.read() == data, name
