"""The working-tree scan keeps {path: [mtime_ns, ctime_ns, size, ino, dev, hash]} and
skips reading a file whose key is unchanged (and whose mtime is not within two seconds
of the scan's start), as git's index does. A change that keeps the size is seen through
the mtime or the ctime; a file touched just now is always read."""
import json
import os
import time

from sgit_ai.crypto.Vault__Crypto     import Vault__Crypto
from sgit_ai.core.Vault__Sync         import Vault__Sync
from tests._helpers.pack_env          import Pack__Env
from tests._helpers.vault_test_env    import TEST_VAULT_KEY


class Crypto__Counting(Vault__Crypto):
    hashes : int = 0
    def content_hash(self, plaintext):
        self.hashes += 1
        return super().content_hash(plaintext)


def _age(path, seconds=10):
    old = time.time() - seconds
    os.utime(path, (old, old))


class Test_Scan_Cache:

    def setup_method(self):
        self.env = Pack__Env()
        self.sync, self.d, _ = self.env.normal_vault({'a.txt': b'aaaa\n', 'b/c.txt': b'cccc\n'}, vault_key=TEST_VAULT_KEY)
        for rel in ('a.txt', 'b/c.txt'):
            _age(os.path.join(self.d, rel))
        self.crypto = Crypto__Counting()
        self.scan   = Vault__Sync(crypto=self.crypto, api=self.env.api)

    def test_unchanged_files_are_not_re_read_on_the_second_scan(self):
        first = self.scan._scan_local_directory(self.d)
        assert self.crypto.hashes == 2 and set(first) == {'a.txt', 'b/c.txt'}
        with open(os.path.join(self.d, '.sg_vault', 'local', 'scan-cache.json')) as f:
            cache = json.load(f)['files']
        assert set(cache) == {'a.txt', 'b/c.txt'} and cache['a.txt'][5] == first['a.txt']['content_hash']
        second = self.scan._scan_local_directory(self.d)
        assert self.crypto.hashes == 2 and second == first                 # nothing read again

    def test_a_same_size_edit_is_seen_through_the_mtime(self):
        self.scan._scan_local_directory(self.d)
        path = os.path.join(self.d, 'a.txt')
        with open(path, 'wb') as f:
            f.write(b'bbbb\n')                                              # same size
        _age(path, 5)                                                       # a different, old mtime
        second = self.scan._scan_local_directory(self.d)
        assert self.crypto.hashes == 3 and second['a.txt']['content_hash'] == Vault__Crypto().content_hash(b'bbbb\n')

    def test_a_file_touched_just_now_is_always_read(self):
        self.scan._scan_local_directory(self.d)
        path = os.path.join(self.d, 'a.txt')
        os.utime(path, None)                                                # now: inside the racy window
        self.scan._scan_local_directory(self.d)
        assert self.crypto.hashes == 3

    def test_a_corrupt_cache_file_is_ignored(self):
        self.scan._scan_local_directory(self.d)
        with open(os.path.join(self.d, '.sg_vault', 'local', 'scan-cache.json'), 'w') as f:
            f.write('{not json')
        second = self.scan._scan_local_directory(self.d)
        assert set(second) == {'a.txt', 'b/c.txt'} and self.crypto.hashes == 4

    def test_status_still_sees_an_edit_and_a_delete(self):
        assert self.sync.status(self.d)['clean']
        with open(os.path.join(self.d, 'a.txt'), 'wb') as f:
            f.write(b'zzzz\n')
        os.remove(os.path.join(self.d, 'b', 'c.txt'))
        st = self.sync.status(self.d)
        assert st['modified'] == ['a.txt'] and st['deleted'] == ['b/c.txt']
