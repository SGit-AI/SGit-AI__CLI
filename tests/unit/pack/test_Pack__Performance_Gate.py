"""Synthetic performance gates for pack mode, measured in requests and bytes on the
counted in-memory host (deterministic, so a regression fails the build; wall time
is recorded in the report but not asserted — CI machines differ).

The vault: COMMITS commits, each adding FILES_PER_COMMIT prose-like files of ~2 KB,
on a normal vault and on a pack vault with the same content. The claims gated:

  clone   a pack clone is a handful of requests whatever the history; a loose clone
          grows with the object count
  pull    N pushes behind: a pack pull is two listings and one batch; a loose pull
          grows with the objects fetched
  push    one commit: a pack push makes no more requests than a loose push
  bytes   the host holds less than 70 % of the loose bytes (deflate on the blobs)

Set SGIT_PACK_PERF_REPORT=<path> to write the measurements as JSON.
"""
import json
import os
import time

import pytest

from sgit_ai.core.actions.pack.Vault__Packs import Vault__Packs
from tests._helpers.pack_env                import Pack__Env, Host__Counting
from tests._helpers.vault_test_env          import TEST_VAULT_KEYS

COMMITS          = 20
FILES_PER_COMMIT = 10
PULL_BEHIND      = 5


def _build(env, packs: bool, key: str) -> tuple:
    sync = env.sync(); d = env.path('pack' if packs else 'loose')
    sync.init(d, vault_key=key, packs=packs)
    for i in range(COMMITS):
        env.write(d, env.text_files(FILES_PER_COMMIT, prefix=f'c{i}/f', salt=f'commit {i} '))   # a folder per commit, as agents do
        sync.commit(d, message=f'commit {i}')
    sync.push(d)
    return sync, d


def _measure(env, fn) -> dict:
    env.api.reset_counts()
    t0 = time.monotonic()
    fn()
    return dict(requests=env.api.requests(), calls=dict(env.api.calls), seconds=round(time.monotonic() - t0, 3))


class Test_Pack__Performance_Gate:

    @classmethod
    def setup_class(cls):
        cls.env    = Pack__Env(Host__Counting().setup())
        cls.sync_l, cls.loose = _build(cls.env, False, TEST_VAULT_KEYS[0])
        cls.sync_p, cls.pack  = _build(cls.env, True,  TEST_VAULT_KEYS[1])
        cls.key_l = cls.sync_l._read_vault_key(cls.loose)
        cls.key_p = cls.sync_p._read_vault_key(cls.pack)
        cls.vid_l = cls.sync_l._init_components(cls.loose).vault_id
        cls.vid_p = cls.sync_p._init_components(cls.pack).vault_id
        cls.report = dict(commits=COMMITS, files=COMMITS * FILES_PER_COMMIT)

    @classmethod
    def teardown_class(cls):
        path = os.environ.get('SGIT_PACK_PERF_REPORT')
        if path:
            with open(path, 'w') as f:
                json.dump(cls.report, f, indent=2)

    def test_host_bytes_are_well_under_the_loose_bytes(self):
        loose_bytes = sum(len(v) for v in self.env.api.host_files(self.vid_l).values())
        pack_bytes  = sum(len(v) for v in self.env.api.host_files(self.vid_p).values())
        objects     = len(self.env.api.loose_objects(self.vid_l))
        self.report['host'] = dict(loose_bytes=loose_bytes, pack_bytes=pack_bytes, loose_objects=objects,
                                   ratio=round(loose_bytes / pack_bytes, 2))
        assert objects >= COMMITS * (FILES_PER_COMMIT + 2)
        assert self.env.api.loose_objects(self.vid_p) == []
        assert pack_bytes < 0.7 * loose_bytes, self.report['host']               # 1.58x measured on the comms vault
        from sgit_ai.core.actions.pack.Vault__Pack_Maintain import Vault__Pack_Maintain
        local = Vault__Pack_Maintain(crypto=self.sync_p.crypto, api=self.env.api).stats(self.pack)['local']
        self.report['blobs'] = local
        assert local['deflated'] == local['blobs'] and local['ratio'] >= 2.0, local   # prose: every blob deflated, 2x+

    def test_clone_requests_do_not_grow_with_the_history(self):
        loose = _measure(self.env, lambda: self.env.clone(self.key_l, 'loose-clone'))
        pack  = _measure(self.env, lambda: self.env.clone(self.key_p, 'pack-clone'))
        self.report['clone'] = dict(loose=loose, pack=pack)
        objects = len(self.env.api.loose_objects(self.vid_l))
        assert loose['requests'] >= objects / 50                                   # a batch is 50 objects: grows with the store
        assert pack['requests'] <= 8, pack                                         # index, meta, 2 listings, the pack: flat
        assert pack['requests'] < loose['requests'], (pack, loose)
        assert self.env.tree(os.path.join(self.env.root, 'loose-clone')) == self.env.tree(os.path.join(self.env.root, 'pack-clone'))

    def test_pull_behind_by_several_pushes_is_four_requests_on_a_pack_vault(self):
        sync_lc, lc = self.env.clone(self.key_l, 'loose-puller')
        sync_pc, pc = self.env.clone(self.key_p, 'pack-puller')
        for i in range(PULL_BEHIND):
            self.env.write(self.loose, self.env.text_files(FILES_PER_COMMIT, prefix=f'p{i}_', salt=f'push {i} '))
            self.sync_l.commit(self.loose, message=f'push {i}'); self.sync_l.push(self.loose)
            self.env.write(self.pack, self.env.text_files(FILES_PER_COMMIT, prefix=f'p{i}_', salt=f'push {i} '))
            self.sync_p.commit(self.pack, message=f'push {i}'); self.sync_p.push(self.pack)
        loose = _measure(self.env, lambda: sync_lc.pull(lc))
        pack  = _measure(self.env, lambda: sync_pc.pull(pc))
        self.report['pull'] = dict(behind=PULL_BEHIND, loose=loose, pack=pack)
        assert self.env.tree(lc) == self.env.tree(self.loose) and self.env.tree(pc) == self.env.tree(self.pack)
        assert pack['calls']['list_files'] == 3                                    # commits/, snapshots/, indexes/commits/
        pack_batches = [b for b in self.env.api.batch_reads if any('packs/' in f for f in b)]
        assert len(pack_batches) == 1 and len(pack_batches[0]) == 2 * PULL_BEHIND  # each pack with its index pack
        assert pack['requests'] <= 8, pack
        assert pack['requests'] < loose['requests'], (pack, loose)

    def test_push_of_one_commit_costs_no_more_than_a_loose_push(self):
        self.env.write(self.loose, self.env.text_files(FILES_PER_COMMIT, prefix='last_', salt='last '))
        self.sync_l.commit(self.loose, message='last')
        self.env.write(self.pack, self.env.text_files(FILES_PER_COMMIT, prefix='last_', salt='last '))
        self.sync_p.commit(self.pack, message='last')
        loose = _measure(self.env, lambda: self.sync_l.push(self.loose))
        pack  = _measure(self.env, lambda: self.sync_p.push(self.pack))
        self.report['push'] = dict(loose=loose, pack=pack)
        assert pack['requests'] <= loose['requests'] + 2, (pack, loose)          # + the two pack listings of the pull-first
        assert not [f for f in self.env.api.written_ids if f.startswith('bare/data/')]
        assert self.env.api.loose_objects(self.vid_p) == []

    def test_z_report(self):
        print(json.dumps(self.report, indent=1))
