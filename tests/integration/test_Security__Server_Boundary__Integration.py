"""Security boundary on a REAL server (sgraph-ai-app-send, in-memory storage).

The threat model's read-key-holder risks (TM-R01..R03, tests/security) all need the
host's help, because the write key is the only thing that stops a reader writing to
the store, and only the server checks it. These tests prove that check holds on the
real server, op by op, so the "by design" rows stay conditional on a hostile host:

  * a reader (read key, wrong write key) cannot move the named ref, by a plain
    write, a batch write, or a batch compare-and-swap;
  * a reader cannot delete objects (vandalism) or upload new ones;
  * after all of that a fresh clone still gets the honest head.
"""
import base64
import os

import pytest

from sgit_ai.core.Vault__Sync              import Vault__Sync
from sgit_ai.crypto.Vault__Crypto          import Vault__Crypto
from sgit_ai.safe_types.Enum__Batch_Op     import Enum__Batch_Op

READER_WRITE_KEY = 'b' * 64                                    # what a reader without the write key can send


def _write(d, rel, content):
    path = os.path.join(d, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)


class Test_Security__Server_Boundary:

    @pytest.fixture(autouse=True)
    def _vault(self, vault_api, temp_dir):
        self.api    = vault_api
        self.crypto = Vault__Crypto()
        self.sync   = Vault__Sync(crypto=self.crypto, api=vault_api)
        self.tmp    = temp_dir
        self.key    = self.sync.generate_vault_key()
        self.alice  = os.path.join(temp_dir, 'alice')
        self.sync.init(self.alice, vault_key=self.key)
        _write(self.alice, 'policy.md', 'pay alice')
        self.head   = self.sync.commit(self.alice, message='initial')['commit_id']
        self.sync.push(self.alice)
        keys          = self.crypto.derive_keys_from_vault_key(self.key)
        self.vault_id = keys['vault_id']
        self.read_key = keys['read_key_bytes']
        c             = self.sync._init_components(self.alice)
        index         = c.branch_manager.load_branch_index(self.alice, c.branch_index_file_id, c.read_key)
        self.ref_id   = str(c.branch_manager.get_branch_by_name(index, 'current').head_ref_id)
        self.forged   = self.crypto.encrypt(self.read_key, b'{"commit_id": "obj-cas-imm-000000000000"}')

    def _assert_honest_clone(self):
        dest = os.path.join(self.tmp, f'check-{len(os.listdir(self.tmp))}')
        self.sync.clone(self.key, dest)
        with open(os.path.join(dest, 'policy.md')) as f:
            assert f.read() == 'pay alice'

    def test_reader_cannot_move_the_named_ref_by_plain_write(self):
        with pytest.raises(Exception, match='40[13]'):
            self.api.write(self.vault_id, f'bare/refs/{self.ref_id}', READER_WRITE_KEY, self.forged)
        self._assert_honest_clone()

    @pytest.mark.parametrize('op', [Enum__Batch_Op.WRITE.value, Enum__Batch_Op.WRITE_IF_MATCH.value])
    def test_reader_cannot_move_the_named_ref_by_batch(self, op):
        current = self.api.read(self.vault_id, f'bare/refs/{self.ref_id}')
        entry   = dict(op=op, file_id=f'bare/refs/{self.ref_id}', data=base64.b64encode(self.forged).decode('ascii'))
        if op == Enum__Batch_Op.WRITE_IF_MATCH.value:                       # a correct match: only the write key is wrong
            entry['match'] = base64.b64encode(current).decode('ascii')
        try:
            result = self.api.batch(self.vault_id, READER_WRITE_KEY, [entry])
        except Exception as error:
            assert '40' in str(error)                                       # refused outright (401/403)
        else:
            statuses = [r.get('status') for r in (result or {}).get('results', [])] + [(result or {}).get('status')]
            assert 'ok' not in statuses, f'server accepted a reader batch: {result}'
        assert self.api.read(self.vault_id, f'bare/refs/{self.ref_id}') == current
        self._assert_honest_clone()

    def test_reader_cannot_delete_or_add_objects(self):
        blob = next(fid for fid in self.api.list_files(self.vault_id, 'bare/data/') if fid)
        with pytest.raises(Exception, match='40[13]'):
            self.api.delete(self.vault_id, blob if blob.startswith('bare/') else f'bare/data/{blob}', READER_WRITE_KEY)
        planted = self.crypto.encrypt(self.read_key, b'planted')
        with pytest.raises(Exception, match='40[13]'):
            self.api.write(self.vault_id, f'bare/data/{self.crypto.compute_object_id(planted)}', READER_WRITE_KEY, planted)
        self._assert_honest_clone()
