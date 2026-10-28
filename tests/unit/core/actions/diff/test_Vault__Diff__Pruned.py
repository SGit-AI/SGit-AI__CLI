"""The pruned diff (F9, design__04 step 3): `history show / diff / log --patch` read only
what changed. The same files, statuses, sizes, hashes and binary flags as the full
decrypt it replaces; only the changed blobs are decrypted; the patch text is
`git diff`'s, byte for byte (git as the oracle)."""
import os
import random
import shutil
import subprocess

import pytest

from sgit_ai.core.Vault__Sync__Base             import Vault__Sync__Base
from sgit_ai.core.actions.diff.Vault__Diff      import Vault__Diff
from sgit_ai.crypto.Vault__Crypto               import Vault__Crypto
from tests.unit.sync.vault_test_env             import Vault__Test_Env

GIT   = shutil.which('git')
FIELDS = ('path', 'status', 'is_binary', 'size_before', 'size_after', 'hash_before', 'hash_after')


def lines(*rows) -> str:
    return ''.join(f'{r}\n' for r in rows)


class Test_Vault__Diff__Pruned:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={f'docs/n{i}.md': f'note {i}\n' for i in range(30)} |
                                          {'src/app.py': lines('def main():', '    a = 1', '    b = 2', '    return a'),
                                           'bin/logo.png': '\x89PNG\x00\x01', 'top.txt': 'top'})

    def setup_method(self):
        self.env  = self._env.restore()
        self.sync = self.env.sync
        self.dir  = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    def write(self, rel, data):
        full = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'wb') as f:
            f.write(data if isinstance(data, bytes) else data.encode())

    def history(self) -> list:
        """A few commits touching folders, a binary file, a missing final newline, deletions."""
        ids = [self.sync.resolve_revision(self.dir, 'HEAD')]
        self.write('src/app.py', lines('def main():', '    a = 10', '    b = 2', '    return a'))
        self.write('top.txt', 'top changed')
        ids.append(self.sync.commit(self.dir, message='edit')['commit_id'])
        os.remove(os.path.join(self.dir, 'docs/n3.md'))
        self.write('docs/new/n.md', 'new\n')
        self.write('bin/logo.png', b'\x89PNG\x00\x02')
        ids.append(self.sync.commit(self.dir, message='move things')['commit_id'])
        return ids

    def old_diff(self, diff, c, new_id, old_id) -> list:
        new = diff._flatten_commit(c, new_id)
        old = diff._flatten_commit(c, old_id) if old_id else {}
        return [f for f in diff.diff_files(new, old) if str(f.status) != 'unchanged']

    def rows(self, files) -> list:
        return [tuple(str(getattr(f, name)) for name in FIELDS) for f in files]

    def test_show_gives_the_same_files_as_the_full_decrypt_and_reads_only_changes(self):
        ids  = self.history()
        diff = Vault__Diff(crypto=Vault__Crypto())
        c    = Vault__Sync__Base(crypto=self.sync.crypto, api=self.sync.api)._init_components(self.dir)
        for parent, cid in zip(ids, ids[1:]):
            info, result = diff.show_commit(self.dir, cid)
            assert self.rows(result.files) == self.rows(self.old_diff(diff, c, cid, parent))
            expected_reads = sum(2 if f.status == 'modified' else 1 for f in result.files)
            assert int(diff.blobs_read) == expected_reads < 30                       # not the whole tree
        result = diff.diff_commits(self.dir, ids[0], ids[-1])
        assert self.rows(result.files) == self.rows(self.old_diff(diff, c, ids[-1], ids[0]))

    def test_log_patch_and_diff_range_use_it(self):
        ids    = self.history()
        diff   = Vault__Diff(crypto=Vault__Crypto())
        log    = diff.log_range_with_details(self.dir, ids[0], ids[-1], include_files=True, include_patch=True)
        last   = log.commits[-1]
        assert sorted(map(str, last.files_added)) == ['docs/new/n.md'] and list(map(str, last.files_deleted)) == ['docs/n3.md']
        ranged = diff.diff_range(self.dir, ids[0], ids[-1])
        assert '--- a/src/app.py\n+++ b/src/app.py\n@@ -1,4 +1,4 @@\n def main():\n-    a = 1\n+    a = 10\n' in str(ranged.patch)

    def test_the_first_commit_diffs_against_nothing(self):
        first = self.sync.resolve_revision(self.dir, 'HEAD')
        while True:
            info, _ = Vault__Diff(crypto=Vault__Crypto()).show_commit(self.dir, first)
            if not info['parent_id']:
                break
            first = info['parent_id']
        _, result = Vault__Diff(crypto=Vault__Crypto()).show_commit(self.dir, first)
        assert all(str(f.status) == 'added' for f in result.files)


@pytest.mark.skipif(GIT is None, reason='git is the oracle')
class Test_Vault__Diff__Patch_Git_Oracle:

    VECTORS = {
        'one line'              : (lines('a', 'b', 'c'), lines('a', 'B', 'c')),
        'no final newline, old' : ('a\nb', 'a\nB\n'),
        'no final newline, both': ('a\nb', 'a\nc'),
        'crlf'                  : ('a\r\nb\r\nc\r\n', 'a\r\nX\r\nc\r\n'),
        'funcname'              : (lines('class A:', *[f'  x{i}' for i in range(12)]),
                                   lines('class A:', *[f'  x{i}' for i in range(11)], '  changed')),
        'empty to text'         : ('', lines('new', 'file')),
        'text to empty'         : (lines('gone'), ''),
    }

    def git_patch(self, tmp_path, before: bytes, after: bytes) -> str:
        repo = tmp_path / 'repo'
        if repo.exists():
            shutil.rmtree(repo)
        (repo / 'dir').mkdir(parents=True)
        (repo / 'dir' / 'f.txt').write_bytes(before)
        git = [GIT, '-C', str(repo), '-c', 'core.autocrlf=false']
        subprocess.run(git[:3] + ['init', '-q'], check=True)
        subprocess.run(git + ['add', '.'], check=True)
        (repo / 'dir' / 'f.txt').write_bytes(after)
        out = subprocess.run(git + ['diff', '--no-color', '--no-ext-diff', 'dir/f.txt'], capture_output=True,
                             check=True).stdout.decode()
        return out[out.index('--- '):] if '--- ' in out else ''

    @pytest.mark.parametrize('name', sorted(VECTORS))
    def test_vectors_equal_git_diff(self, tmp_path, name):
        before, after = (v.encode() for v in self.VECTORS[name])
        assert Vault__Diff(crypto=Vault__Crypto())._unified_diff('dir/f.txt', before, after) == \
               self.git_patch(tmp_path, before, after)

    @pytest.mark.parametrize('seed', range(25))
    def test_random_edits_equal_git_diff(self, tmp_path, seed):
        rng    = random.Random(seed)
        before = [f'line {i}' for i in rng.sample(range(400), 60)]
        after  = list(before)
        for _ in range(rng.randrange(1, 8)):
            k = rng.randrange(len(after))
            op = rng.random()
            if op < 0.3:
                del after[k]
            elif op < 0.6:
                after.insert(k, f'new {rng.randrange(10 ** 6)}')
            else:
                after[k] = f'chg {rng.randrange(10 ** 6)}'
        b, a = lines(*before).encode(), lines(*after).encode()
        assert Vault__Diff(crypto=Vault__Crypto())._unified_diff('dir/f.txt', b, a) == self.git_patch(tmp_path, b, a)
