"""Same content on both sides is not a conflict (phase 0: design__00 F4/B3).

Blobs are encrypted with a random IV, so two clones writing the same bytes get two
blob ids. three_way_merge compared ids only, so that was reported as a conflict, in
pull, branch merge, revert --as-commit and the rewind re-apply. Given the store and
the read key, equal content_hash and size select candidates and the decrypted bytes
decide."""
import os
import shutil
import tempfile

from sgit_ai.core.actions.merge.Vault__Merge     import Vault__Merge
from sgit_ai.crypto.Vault__Crypto                import Vault__Crypto
from sgit_ai.safe_types.Safe_Str__Vault_Path     import Safe_Str__Vault_Path
from sgit_ai.storage.Vault__Object_Store         import Vault__Object_Store
from tests.unit.sync.vault_test_env              import Vault__Test_Env

READ_KEY = bytes(range(32))


class Test_Vault__Merge__Same_Content:

    def setup_method(self):
        self.tmp    = tempfile.mkdtemp()
        self.crypto = Vault__Crypto()
        self.store  = Vault__Object_Store(vault_path=Safe_Str__Vault_Path(os.path.join(self.tmp, '.sg_vault')),
                                          crypto=self.crypto)
        self.merger = Vault__Merge(crypto=self.crypto)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def entry(self, text: str, claimed_hash: str = None) -> dict:
        data = text.encode()
        return dict(blob_id      = self.store.store(self.crypto.encrypt(READ_KEY, data)),     # a fresh IV every time
                    size         = len(data),
                    content_hash = claimed_hash or self.crypto.content_hash(data))

    def merge(self, base, ours, theirs, with_store=True):
        if with_store:
            return self.merger.three_way_merge(base, ours, theirs, obj_store=self.store, read_key=READ_KEY)
        return self.merger.three_way_merge(base, ours, theirs)

    def test_same_bytes_get_different_blob_ids(self):
        assert self.entry('x')['blob_id'] != self.entry('x')['blob_id']

    def test_both_change_to_the_same_content(self):
        base, ours, theirs = {'f': self.entry('v1')}, {'f': self.entry('v2')}, {'f': self.entry('v2')}
        result = self.merge(base, ours, theirs)
        assert result['conflicts'] == []
        assert result['merged_map']['f'] == ours['f']

    def test_both_add_the_same_content(self):
        ours, theirs = {'new': self.entry('same')}, {'new': self.entry('same')}
        result = self.merge({}, ours, theirs)
        assert result['conflicts'] == []
        assert result['merged_map']['new'] == ours['new']

    def test_theirs_rewrote_the_base_bytes_and_ours_changed(self):
        base, ours, theirs = {'f': self.entry('v1')}, {'f': self.entry('mine')}, {'f': self.entry('v1')}
        result = self.merge(base, ours, theirs)
        assert result['conflicts'] == []
        assert result['merged_map']['f'] == ours['f']

    def test_ours_rewrote_the_base_bytes_and_theirs_deleted(self):
        base, ours = {'f': self.entry('v1')}, {'f': self.entry('v1')}
        result = self.merge(base, ours, {})
        assert result['conflicts'] == []
        assert result['deleted']   == ['f']

    def test_different_content_still_conflicts(self):
        base, ours, theirs = {'f': self.entry('v1')}, {'f': self.entry('mine')}, {'f': self.entry('theirs')}
        assert self.merge(base, ours, theirs)['conflicts'] == ['f']

    def test_a_claimed_hash_alone_never_decides(self):
        """A writer controls the content_hash it records; the bytes decide."""
        mine   = self.entry('mine')
        forged = self.entry('something else', claimed_hash=mine['content_hash'])
        forged['size'] = mine['size']
        assert self.merge({'f': self.entry('v1')}, {'f': mine}, {'f': forged})['conflicts'] == ['f']

    def test_an_unreadable_blob_is_not_the_same(self):
        ours, theirs = {'new': self.entry('same')}, {'new': self.entry('same')}
        os.remove(self.store.object_path(theirs['new']['blob_id']))
        assert self.merge({}, ours, theirs)['conflicts'] == ['new']

    def test_without_the_store_ids_decide_as_before(self):
        base, ours, theirs = {'f': self.entry('v1')}, {'f': self.entry('v2')}, {'f': self.entry('v2')}
        assert self.merge(base, ours, theirs, with_store=False)['conflicts'] == ['f']


class Test_Vault__Merge__Same_Content__Pull:
    """End to end: Alice pushes the same bytes Bob then commits; Bob's pull merges."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'base.txt': 'base'})

    def setup_method(self):
        self.env  = self._env.restore()
        self.sync = self.env.sync

    def teardown_method(self):
        self.env.cleanup()

    def test_pull_merges_without_a_conflict(self):
        for directory, other in ((self.env.alice_dir, 'alice.txt'), (self.env.bob_dir, 'bob.txt')):
            with open(os.path.join(directory, 'shared.txt'), 'w') as f:
                f.write('the same words')
            with open(os.path.join(directory, other), 'w') as f:             # each side changes something else too
                f.write(other)
            self.sync.commit(directory, message=other)
            if directory == self.env.alice_dir:
                self.sync.push(directory)
        result = self.sync.pull(self.env.bob_dir)
        assert result['status'] == 'merged'                                   # a three-way merge, not up to date
        assert not os.path.isfile(os.path.join(self.env.bob_dir, 'shared.txt.conflict'))
        assert os.path.isfile(os.path.join(self.env.bob_dir, 'alice.txt'))
