"""0.19–0.21 features against a REAL SG/Send server (the User Lambda on a local
HTTP port, in-memory storage): branches, branch merge, signed tags, the format
gate with 128-bit ids, signatures-required with a late teammate, rewinds,
push --force-with-lease, signed merge commits. Nothing is mocked; each test
uses its own random vault on the shared server."""
import json
import os
import pytest

from sgit_ai.core.Vault__Sync                         import Vault__Sync
from sgit_ai.crypto.Vault__Crypto                     import Vault__Crypto
from sgit_ai.core.Vault__Errors                       import Vault__Ref_Rewind_Error, Vault__Push_Lease_Error
from sgit_ai.core.actions.branch.Vault__Branch_Switch import Vault__Branch_Switch
from sgit_ai.storage.Vault__Format                    import FEATURE_SIG_REQUIRED


def _write(d, rel, content):
    full = os.path.join(d, rel); os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as f: f.write(content)

def _read(d, rel):
    p = os.path.join(d, rel)
    return open(p).read() if os.path.exists(p) else None


class _Base:

    @pytest.fixture(autouse=True)
    def _vault(self, vault_api, temp_dir):
        self.api   = vault_api
        self.sync  = Vault__Sync(crypto=Vault__Crypto(), api=vault_api)
        self.tmp   = temp_dir
        self.key   = self.sync.generate_vault_key()
        self.alice = os.path.join(temp_dir, 'alice'); self.bob = os.path.join(temp_dir, 'bob')
        self.sync.init(self.alice, vault_key=self.key)
        self._push(self.alice, {'a.txt': 'main v1', 'shared.md': 'base'}, 'initial')
        self.sync.clone(self.key, self.bob)
        self.branches = Vault__Branch_Switch(crypto=Vault__Crypto())

    def _commit(self, d, files, message='m'):
        for rel, content in files.items(): _write(d, rel, content)
        return self.sync.commit(d, message=message)['commit_id']

    def _push(self, d, files, message='m'):
        self._commit(d, files, message); return self.sync.push(d)

    def _server_head(self, d, name):
        c     = self.sync._init_components(d)
        index = c.branch_manager.load_branch_index(d, c.branch_index_file_id, c.read_key)
        meta  = c.branch_manager.get_branch_by_name(index, name)
        found = self.api.batch_read(str(c.vault_id), [f'bare/refs/{meta.head_ref_id}'])
        raw   = found.get(f'bare/refs/{meta.head_ref_id}')
        return json.loads(self.sync.crypto.decrypt(c.read_key, raw))['commit_id'] if raw else None


class Test_Branches__Real_Server(_Base):

    def test_push_to_a_branch_switch_pull_and_merge_back(self):
        main_before = self._server_head(self.alice, 'current')
        self.branches.branch_new(self.alice, 'feature')
        pushed = self._push(self.alice, {'f.txt': 'feature'}, 'feature work')['commit_id']
        assert self._server_head(self.alice, 'feature') == pushed
        assert self._server_head(self.alice, 'current') == main_before

        self.sync.switch_branch(self.bob, 'feature')                    # a teammate's branch, fetched on switch
        assert _read(self.bob, 'f.txt') == 'feature'
        self._push(self.bob, {'g.txt': 'bob'}, 'bob on feature')
        self.sync.pull(self.alice)
        assert _read(self.alice, 'g.txt') == 'bob'

        self.sync.switch_branch(self.alice, 'current')
        assert _read(self.alice, 'f.txt') is None
        self._push(self.alice, {'a.txt': 'main moved'}, 'main moved')
        assert self.sync.merge_branch(self.alice, 'feature')['status'] == 'merged'
        self.sync.push(self.alice)
        self.sync.switch_branch(self.bob, 'current')
        assert _read(self.bob, 'f.txt') == 'feature' and _read(self.bob, 'a.txt') == 'main moved'
        rep = self.sync.verify_signatures(self.bob)
        assert rep['counts']['unsigned'] == 0 and rep['counts']['bad'] == 0 and rep['counts']['no-key'] == 0


class Test_Tags__Real_Server(_Base):

    def test_tag_create_verify_on_a_teammate_and_delete(self):
        head = self.sync.resolve_revision(self.alice, 'HEAD')
        self.sync.tag_create(self.alice, 'v1.0', message='first')
        tags = {t['name']: t for t in self.sync.tag_list(self.bob)}
        assert tags['v1.0']['status'] == 'verified' and tags['v1.0']['commit_id'] == head
        self.sync.tag_delete(self.alice, 'v1.0')
        assert 'v1.0' not in {t['name'] for t in self.sync.tag_list(self.bob)}


class Test_Format_Gate__Real_Server(_Base):

    def test_format_2_writes_128_bit_ids_the_server_accepts(self):
        self.sync.set_format(self.alice, format=2)
        self._push(self.alice, {'new.txt': 'after the raise'}, 'format 2')
        c     = self.sync._init_components(self.alice)
        names = self.api.list_files(str(c.vault_id), 'bare/data/')
        assert any(len(n.rsplit('/', 1)[-1]) == len('obj-cas-imm-') + 32 for n in names)
        self.sync.pull(self.bob)
        assert _read(self.bob, 'new.txt') == 'after the raise'
        assert self.sync.fsck(self.bob)['missing'] == []


class Test_Signatures__Real_Server(_Base):

    def test_signatures_required_accepts_a_teammate_who_joined_later(self):
        self.sync.set_format(self.alice, add_features=[FEATURE_SIG_REQUIRED])
        carol = os.path.join(self.tmp, 'carol')
        self.sync.clone(self.key, carol)
        self._push(carol, {'c.txt': 'carol'}, 'carol')
        assert self.sync.pull(self.alice)['status'] == 'merged'
        self.sync.set_format(self.alice, remove_features=[FEATURE_SIG_REQUIRED])
        self.sync.pull(self.bob)
        assert FEATURE_SIG_REQUIRED not in self.sync.format_info(self.bob)['features']


class Test_Rewind_And_Lease__Real_Server(_Base):

    def test_a_force_push_is_refused_then_accepted_and_the_lease_protects(self):
        c1 = self._push(self.bob, {'a.txt': 'one'}, 'one')['commit_id']
        self._push(self.bob, {'a.txt': 'two'}, 'two')
        self.sync.pull(self.alice)
        self.sync.reset(self.bob, c1)
        self.sync.push(self.bob, force=True, lease='')                 # bob saw the head it rewinds: allowed
        with pytest.raises(Vault__Ref_Rewind_Error):
            self.sync.pull(self.alice)
        r = self.sync.pull(self.alice, accept_rewind=True)
        assert r['rewound'] is True and _read(self.alice, 'a.txt') == 'one'
        assert self.sync.status(self.alice)['push_status'] == 'up_to_date'

        self._push(self.alice, {'a.txt': 'three'}, 'three')            # bob has not seen this one
        self.sync.reset(self.bob, 'HEAD~1')
        with pytest.raises(Vault__Push_Lease_Error):
            self.sync.push(self.bob, force=True, lease='')
        assert self._server_head(self.alice, 'current') == self.sync.resolve_revision(self.alice, 'HEAD')
