"""design__04 step 2: content paths, Git's path quoting, the blob reader, path history."""
import os
import shutil
import subprocess

import pytest

from sgit_ai.core.Vault__Errors                         import Vault__Integrity_Error
from sgit_ai.core.Vault__Path_Quote                     import Vault__Path_Quote
from sgit_ai.core.Vault__Sync__Base                     import Vault__Sync__Base
from sgit_ai.core.actions.history.Vault__Blob_Reader    import Vault__Blob_Reader
from sgit_ai.core.actions.history.Vault__Path_History   import Vault__Path_History
from sgit_ai.safe_types.Safe_Str__Content_Path          import Safe_Str__Content_Path
from sgit_ai.storage.Vault__Commit                      import Vault__Commit
from sgit_ai.storage.Vault__Sub_Tree                    import Vault__Sub_Tree
from tests.unit.sync.vault_test_env                     import Vault__Test_Env

NAMES = ['plain.txt', 'tab\there.txt', 'quote"d.txt', 'back\\slash.txt', 'josé.md', 'new\nline.txt', 'bell\x07.txt']


class Test_Vault__Path_Quote:

    def test_plain_paths_are_printed_as_they_are(self):
        assert Vault__Path_Quote().quote('docs/a b.md') == 'docs/a b.md'

    def test_escapes(self):
        quote = Vault__Path_Quote()
        assert quote.quote('new\nline') == '"new\\nline"'
        assert quote.quote('josé.md') == '"jos\\303\\251.md"'
        assert Vault__Path_Quote(quote_non_ascii=False).quote('josé.md') == 'josé.md'
        assert Vault__Path_Quote(quote_non_ascii=False).quote('a\x1bb') == '"a\\033b"'

    @pytest.mark.skipif(shutil.which('git') is None, reason='git is the oracle')
    @pytest.mark.parametrize('quote_path', ['true', 'false'])
    def test_the_same_quoting_as_git_ls_files(self, tmp_path, quote_path):
        repo = tmp_path / 'repo'
        repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        for name in NAMES:
            (repo / name).write_text('x')
        subprocess.run(['git', '-C', str(repo), 'add', '-A'], check=True)
        listed = subprocess.run(['git', '-C', str(repo), '-c', f'core.quotePath={quote_path}', 'ls-files'],
                                capture_output=True, check=True).stdout.decode('utf-8').splitlines()
        ours   = sorted(Vault__Path_Quote(quote_non_ascii=quote_path == 'true').quote(n) for n in NAMES)
        assert sorted(listed) == ours


class Test_Safe_Str__Content_Path:

    def test_unicode_kept_and_control_characters_refused(self):
        assert Safe_Str__Content_Path('docs/josé – notes.md') == 'docs/josé – notes.md'
        assert Safe_Str__Content_Path(' trailing ') == ' trailing '
        with pytest.raises(ValueError):
            Safe_Str__Content_Path('a\nb')


class Test_Vault__Blob_Reader__And_Path_History:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'docs/deep/a.md': 'alpha\n', 'docs/b.md': 'beta\n', 'top.txt': 'top\n'})

    def setup_method(self):
        self.env  = self._env.restore()
        self.sync = self.env.sync
        self.dir  = self.env.vault_dir
        self.c    = Vault__Sync__Base(crypto=self.sync.crypto, api=self.sync.api)._init_components(self.dir)
        self.sub  = Vault__Sub_Tree(crypto=self.sync.crypto, obj_store=self.c.obj_store)
        self.vc   = Vault__Commit(crypto=self.sync.crypto, pki=self.c.pki, object_store=self.c.obj_store,
                                  ref_manager=self.c.ref_manager)

    def teardown_method(self):
        self.env.cleanup()

    def tree_of(self, rev='HEAD') -> str:
        return str(self.vc.load_commit(self.sync.resolve_revision(self.dir, rev), self.c.read_key).tree_id)

    def reader(self, **kw) -> Vault__Blob_Reader:
        return Vault__Blob_Reader(crypto=self.sync.crypto, obj_store=self.c.obj_store, read_key=self.c.read_key,
                                  vault_id=str(self.c.vault_id), sg_dir=str(self.c.sg_dir), **kw)

    def history(self) -> Vault__Path_History:
        return Vault__Path_History(sub_tree=self.sub, read_key=self.c.read_key)

    # --- blob reader --------------------------------------------------------------------

    def test_reads_and_memoises(self):
        reader = self.reader()
        entry  = self.history().entry_at(self.tree_of(), 'docs/deep/a.md')
        assert reader.content(entry) == b'alpha\n' and reader.content(entry) == b'alpha\n'
        assert int(reader.blobs_read) == 1

    def test_a_blob_not_in_the_clone_is_fetched_and_verified(self):
        entry = self.history().entry_at(self.tree_of(), 'docs/b.md')
        os.remove(self.c.obj_store.object_path(entry['blob_id']))
        assert self.reader().content(entry) is None                                    # no api: missing
        reader = self.reader(api=self.sync.api)
        assert reader.content(entry) == b'beta\n' and int(reader.blobs_fetched) == 1
        assert self.reader(api=self.sync.api, offline=True).content(dict(entry, blob_id=entry['blob_id'])) == b'beta\n'

    def test_a_substituted_blob_is_refused(self):
        entry  = self.history().entry_at(self.tree_of(), 'docs/b.md')
        other  = self.history().entry_at(self.tree_of(), 'top.txt')
        os.remove(self.c.obj_store.object_path(entry['blob_id']))
        key    = f'{self.c.vault_id}/bare/data/{entry["blob_id"]}'
        self.sync.api._store[key] = self.c.obj_store.load(other['blob_id'])          # the host swaps the content
        with pytest.raises(Vault__Integrity_Error):
            self.reader(api=self.sync.api).content(entry)

    def test_the_memo_is_bounded(self):
        reader = self.reader(memo_bytes=8)
        tree   = self.tree_of()
        for path in ('docs/deep/a.md', 'docs/b.md', 'top.txt'):
            reader.content(self.history().entry_at(tree, path))
        assert int(reader.memo_size) <= 8

    # --- path history -------------------------------------------------------------------

    def test_entry_at_reads_only_the_folders_on_the_path(self):
        history = self.history()
        entry   = history.entry_at(self.tree_of(), 'docs/deep/a.md')
        assert entry['size'] == 6 and len(history.tree_memo) == 3                     # root, docs, docs/deep
        assert history.entry_at(self.tree_of(), 'docs/nope.md') is None
        assert history.entry_at(self.tree_of(), 'docs') is None                        # a folder is not a file

    def test_same_at_across_commits(self):
        before = self.tree_of()
        with open(os.path.join(self.dir, 'top.txt'), 'w') as f:
            f.write('changed\n')
        self.sync.commit(self.dir, message='top')
        after = self.tree_of()
        assert self.history().same_at(before, after, 'docs/deep/a.md')               # stops at the equal folder
        assert not self.history().same_at(before, after, 'top.txt')

    def test_a_re_encryption_of_unchanged_content_is_not_a_change(self):
        tree  = self.tree_of()
        flat  = self.sub.flatten(tree, self.c.read_key)
        again = self.sync.crypto.encrypt(self.c.read_key, b'beta\n', deflate=True)    # what a web UI write does
        flat['docs/b.md'] = dict(flat['docs/b.md'], blob_id=self.c.obj_store.store(again))
        rebuilt = self.sub.build_from_flat(flat, self.c.read_key)
        assert rebuilt != tree
        assert self.history().same_at(tree, rebuilt, 'docs/b.md')
