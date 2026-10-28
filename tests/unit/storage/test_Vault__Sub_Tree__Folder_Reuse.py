"""build_from_flat keeps unchanged folders; apply_changes (phase 0: design__00 F3/B7).

A merge, a `sgit write` of one file and (later) every replayed or picked commit built
the tree with build_from_flat, which rebuilt and re-encrypted every folder: the cost
of the whole vault for a one-file change. Given the previous head's flat entries and
folder ids, a folder whose entries are all exactly the old ones keeps its id. The
invariant: the root id is exactly what a full build gives."""
import os
import random
import shutil
import tempfile

import pytest

from sgit_ai.crypto.Vault__Crypto                import Vault__Crypto
from sgit_ai.safe_types.Safe_Str__Vault_Path     import Safe_Str__Vault_Path
from sgit_ai.storage.Vault__Object_Store         import Vault__Object_Store
from sgit_ai.storage.Vault__Sub_Tree             import Vault__Sub_Tree
from tests.unit.sync.vault_test_env              import Vault__Test_Env

READ_KEY = bytes(range(32))


class Counting_Object_Store(Vault__Object_Store):
    """A real store that also counts the objects handed to it (trees, here)."""
    stored : int = 0

    def store(self, ciphertext: bytes) -> str:
        self.stored += 1
        return super().store(ciphertext)


class Test_Vault__Sub_Tree__Folder_Reuse:

    def setup_method(self):
        self.tmp      = tempfile.mkdtemp()
        self.crypto   = Vault__Crypto()
        self.store    = Counting_Object_Store(vault_path=Safe_Str__Vault_Path(os.path.join(self.tmp, '.sg_vault')),
                                              crypto=self.crypto)
        self.sub_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=self.store)
        self.rng      = random.Random(20261028)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def entry(self, text: str) -> dict:
        data = text.encode()
        return dict(blob_id=self.store.store(self.crypto.encrypt(READ_KEY, data)), size=len(data),
                    content_hash=self.crypto.content_hash(data), content_type='text/plain', large=False)

    def vault(self, folders=6, depth=3, files=4) -> dict:
        flat = {}
        for f in range(folders):
            for d in range(depth):
                prefix = '/'.join(f'f{f}d{i}' for i in range(d + 1))
                for n in range(files):
                    flat[f'{prefix}/file{n}.txt'] = self.entry(f'{prefix}/{n}')
        flat['root.txt'] = self.entry('root')
        return flat

    def full(self, flat: dict) -> str:
        return self.sub_tree.build_from_flat(flat, READ_KEY)

    def reused(self, flat: dict, old_flat: dict, old_root: str) -> str:
        return self.sub_tree.build_from_flat(flat, READ_KEY, old_flat_entries=old_flat,
                                             old_tree_ids=self.sub_tree.flatten_dirs(old_root, READ_KEY))

    def test_one_changed_file_builds_only_its_folders_and_gives_the_full_build_id(self):
        old      = self.vault()
        old_root = self.full(old)
        new      = dict(old)
        new['f2d0/f2d1/f2d2/file1.txt'] = self.entry('changed')
        before   = self.store.stored
        root     = self.reused(new, old, old_root)
        assert self.store.stored - before == 4                     # f2d0/f2d1/f2d2, f2d0/f2d1, f2d0, root
        assert root == self.full(new)

    @pytest.mark.parametrize('change', ['modify', 'add_file', 'delete_file', 'add_folder',
                                        'delete_folder', 'rename', 'nothing', 'type_only'])
    def test_every_kind_of_change_gives_the_full_build_id(self, change):
        old      = self.vault()
        old_root = self.full(old)
        new      = dict(old)
        paths    = sorted(old)
        if change == 'modify':
            for p in self.rng.sample(paths, 5):
                new[p] = self.entry(p + ' v2')
        elif change == 'add_file':
            new['f1d0/new.txt'] = self.entry('new')
        elif change == 'delete_file':
            del new['f3d0/f3d1/file0.txt']
        elif change == 'add_folder':
            new['f4d0/fresh/deep/x.txt'] = self.entry('x')
        elif change == 'delete_folder':
            for p in [p for p in paths if p.startswith('f5d0/f5d1/f5d2/')]:
                del new[p]
        elif change == 'rename':
            new['f0d0/renamed.txt'] = new.pop('f0d0/file0.txt')
        elif change == 'type_only':
            new['f1d0/file1.txt'] = dict(new['f1d0/file1.txt'], content_type='application/json')
        assert self.reused(new, old, old_root) == self.full(new)

    def test_apply_changes_matches_the_full_build(self):
        old      = self.vault()
        old_root = self.full(old)
        changes  = {'f0d0/file0.txt': self.entry('a'), 'f4d0/f4d1/file3.txt': None, 'brand/new.txt': self.entry('b')}
        new      = dict(old)
        for path, entry in changes.items():
            if entry is None:
                del new[path]
            else:
                new[path] = entry
        before = self.store.stored
        root   = self.sub_tree.apply_changes(old_root, changes, READ_KEY)
        built  = self.store.stored - before
        assert root == self.full(new)
        assert built == 5                                           # of 19: f0d0, f4d0/f4d1, f4d0, brand and the root

    def test_apply_changes_from_an_empty_tree(self):
        changes = {'a/b.txt': self.entry('b')}
        assert self.sub_tree.apply_changes('', changes, READ_KEY) == self.full(changes)

    def test_without_old_ids_everything_is_built_as_before(self):
        old    = self.vault()
        before = self.store.stored
        self.full(old)
        assert self.store.stored - before == 19                       # every folder: 6 chains of 3, and the root


class Test_Vault__Sub_Tree__Folder_Reuse__Write:
    """`sgit write` of one file builds the folders on its path, not the vault."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={f'docs/part{i}/note{j}.txt': f'{i}-{j}' for i in range(10) for j in range(3)})

    def setup_method(self):
        self.env = self._env.restore()

    def teardown_method(self):
        self.env.cleanup()

    def test_write_reuses_unchanged_folders(self):
        sync   = self.env.sync
        result = sync.write_file(self.env.vault_dir, 'docs/part3/note1.txt', b'rewritten')
        c      = sync._init_components(self.env.vault_dir)
        sub    = Vault__Sub_Tree(crypto=self.env.crypto, obj_store=c.obj_store)
        from sgit_ai.storage.Vault__Commit import Vault__Commit
        vc     = Vault__Commit(crypto=self.env.crypto, pki=c.pki, object_store=c.obj_store, ref_manager=c.ref_manager)
        new    = vc.load_commit(result['commit_id'], c.read_key)
        old    = vc.load_commit(self.env.commit_id, c.read_key)
        new_dirs, old_dirs = sub.flatten_dirs(str(new.tree_id), c.read_key), sub.flatten_dirs(str(old.tree_id), c.read_key)
        changed = sorted(d for d in new_dirs if new_dirs[d] != old_dirs.get(d))
        assert changed == ['', 'docs', 'docs/part3']
        assert str(new.tree_id) == sub.build_from_flat(sub.flatten(str(new.tree_id), c.read_key), c.read_key)
