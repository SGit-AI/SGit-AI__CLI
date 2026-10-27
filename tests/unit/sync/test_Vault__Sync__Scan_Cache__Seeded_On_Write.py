"""Newsroom field report, 26 Oct, item 1: the first status on a fresh 4.2 GB clone read
every file back (18 minutes on a cloud session's disk). Every working-copy write sgit
makes (clone, pull, read-only pull) now records the file in the scan cache under the
hash of the bytes it wrote, so the next scan stats it instead of reading it."""
import json
import os

from sgit_ai.crypto.Vault__Crypto      import Vault__Crypto
from sgit_ai.core.Vault__Sync          import Vault__Sync
from tests._helpers.pack_env           import Pack__Env
from tests._helpers.vault_test_env     import TEST_VAULT_KEY


class Crypto__Counting(Vault__Crypto):
    hashes : int = 0
    def content_hash(self, plaintext):
        self.hashes += 1
        return super().content_hash(plaintext)


def _cache(d):
    with open(os.path.join(d, '.sg_vault', 'local', 'scan-cache.json')) as f:
        return json.load(f)['files']


def _no_racy_window(fn):
    """Run fn with the racy window at zero: the files were written a moment ago."""
    import sgit_ai.core.Vault__Sync__Base as module
    was = module.SCAN_CACHE_RACE_NS
    module.SCAN_CACHE_RACE_NS = 0
    try:
        return fn()
    finally:
        module.SCAN_CACHE_RACE_NS = was


class Test_Seeded_On_Write:

    def setup_method(self):
        self.env   = Pack__Env()
        self.files = self.env.text_files(6)
        self.sync, self.a, self.key = self.env.normal_vault(self.files, vault_key=TEST_VAULT_KEY)

    def test_a_clone_writes_the_cache_for_every_file_and_the_flat_cache_for_the_head(self):
        sync_b, b = self.env.clone(self.key, 'b')
        cache = _cache(b)
        assert set(cache) == set(self.files)
        for rel, data in self.files.items():
            assert cache[rel][5] == Vault__Crypto().content_hash(data) and cache[rel][2] == len(data)
        assert os.listdir(os.path.join(b, '.sg_vault', 'local', 'flat-cache'))     # the head, flattened once
        counting = Vault__Sync(crypto=Crypto__Counting(), api=self.env.api)
        assert _no_racy_window(lambda: counting.status(b))['clean']
        assert counting.crypto.hashes == 0                                           # stat only: nothing read

    def test_a_pull_seeds_the_files_it_writes(self):
        sync_b, b = self.env.clone(self.key, 'b')
        first = sorted(self.files)[0]
        self.env.write(self.a, {'new/one.md': b'one\n', first: b'changed\n'})
        self.sync.commit(self.a, message='a'); self.sync.push(self.a)
        sync_b.pull(b)
        cache = _cache(b)
        assert cache['new/one.md'][5] == Vault__Crypto().content_hash(b'one\n')
        assert cache[first][5] == Vault__Crypto().content_hash(b'changed\n')
        counting = Vault__Sync(crypto=Crypto__Counting(), api=self.env.api)
        assert _no_racy_window(lambda: counting.status(b))['clean'] and counting.crypto.hashes == 0

    def test_a_scan_within_the_racy_window_keeps_a_seed_it_can_confirm(self):
        """Right after a clone every file is inside the racy window: the scan reads them,
        and keeps the seeded entry when the hash it computes is the seeded one."""
        sync_b, b = self.env.clone(self.key, 'b')
        before = _cache(b)
        assert self.sync.status(b)['clean']                                           # reads everything (racy)
        assert _cache(b) == before                                                    # and drops nothing

    def test_the_seed_holds_the_hash_of_the_bytes_written_not_the_entrys_claim(self):
        """The scan cache's hash is computed from the plaintext sgit wrote, so a tree
        entry carrying a wrong content_hash cannot make a status say "clean"."""
        sync_b, b = self.env.clone(self.key, 'b')
        counting = Vault__Sync(crypto=Crypto__Counting(), api=self.env.api)
        second = sorted(self.files)[1]
        with open(os.path.join(b, second), 'wb') as f:
            f.write(b'edited after the clone\n')
        st = _no_racy_window(lambda: counting.status(b))
        assert st['modified'] == [second] and counting.crypto.hashes == 1            # only the edited file read
