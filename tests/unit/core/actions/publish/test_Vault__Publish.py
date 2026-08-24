"""P2/P4 — sgit publish: the plaintext surface, and nothing else."""
import hashlib
import json
import os
import shutil
import tempfile

import pytest

from sgit_ai.crypto.Vault__Crypto                        import Vault__Crypto
from sgit_ai.core.Vault__Sync                            import Vault__Sync
from sgit_ai.core.actions.publish.Loader__Template       import LOADER_TEMPLATE
from sgit_ai.core.actions.publish.Vault__Publish         import Vault__Publish
from sgit_ai.network.api.Vault__API__In_Memory           import Vault__API__In_Memory
from sgit_ai.safe_types.Enum__Visibility                 import Enum__Visibility
from sgit_ai.schemas.publish.Schema__Published_Manifest  import Schema__Published_Manifest


def _tree_digest(directory, exclude_prefix):
    """Digest of every path+content in the tree, excluding one prefix."""
    digest = hashlib.sha256()
    for root, dirs, files in sorted(os.walk(directory)):
        for name in sorted(files):
            full = os.path.join(root, name)
            rel  = os.path.relpath(full, directory)
            if rel.startswith(exclude_prefix):
                continue
            digest.update(rel.encode())
            with open(full, 'rb') as f:
                digest.update(f.read())
    return digest.hexdigest()


def _dir_digest(directory):
    return _tree_digest(directory, exclude_prefix='\x00none')


class Test_Vault__Publish:

    def setup_method(self):
        self.crypto = Vault__Crypto()
        self.api    = Vault__API__In_Memory()
        self.api.setup()
        self.sync   = Vault__Sync(crypto=self.crypto, api=self.api)
        self.tmp    = tempfile.mkdtemp()
        self.vault  = os.path.join(self.tmp, 'vault')
        result      = self.sync.init(self.vault)
        self.vault_key = result['vault_key']
        self.vault_id  = result['vault_id']
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('published content')
        with open(os.path.join(self.vault, 'index.html'), 'w') as f:
            f.write('<html>THE VAULT\'S OWN SITE — ciphertext at publish time</html>')
        os.makedirs(os.path.join(self.vault, 'docs'))
        with open(os.path.join(self.vault, 'docs', 'page.md'), 'w') as f:
            f.write('# page')
        self.sync.commit(self.vault, 'initial')
        self.sync.push(self.vault)
        self.publisher = Vault__Publish(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _publish_dir(self):
        return os.path.join(self.vault, '.sg_vault', 'publish')

    def _surface_files(self):
        result = []
        for root, _dirs, files in os.walk(self._publish_dir()):
            for name in files:
                result.append(os.path.relpath(os.path.join(root, name),
                                              self._publish_dir()).replace(os.sep, '/'))
        return sorted(result)

    # --- P2 acceptance ------------------------------------------------------

    def test_only_publish_dir_changes_and_output_is_surface_only(self):
        # I6 with one documented nuance: recording the clone's visibility
        # choice (decision 5) lives in .sg_vault/local/config.json — local
        # state that is never pushed. Everything else must be byte-identical.
        def digest():
            d = hashlib.sha256()
            for root, dirs, files in sorted(os.walk(self.vault)):
                for name in sorted(files):
                    full = os.path.join(root, name)
                    rel  = os.path.relpath(full, self.vault).replace(os.sep, '/')
                    if rel.startswith('.sg_vault/publish/') or rel == '.sg_vault/local/config.json':
                        continue
                    d.update(rel.encode())
                    with open(full, 'rb') as f:
                        d.update(f.read())
            return d.hexdigest()
        before = digest()
        self.publisher.publish(self.vault)
        assert digest() == before                         # I6: nothing else changed
        assert self._surface_files() == ['cover.json', 'index.html', 'manifest.json']

    def test_no_ciphertext_and_size_independent_of_vault(self):
        with open(os.path.join(self.vault, 'big.bin'), 'wb') as f:
            f.write(os.urandom(2 * 1024 * 1024))
        self.sync.commit(self.vault, 'add a big file')
        self.sync.push(self.vault)
        self.publisher.publish(self.vault)
        assert not os.path.isdir(os.path.join(self._publish_dir(), 'api', 'vault'))
        assert not os.path.isdir(os.path.join(self._publish_dir(), 'bare'))
        total = sum(os.path.getsize(os.path.join(root, name))
                    for root, _d, files in os.walk(self._publish_dir()) for name in files)
        assert total < 64 * 1024                          # O(KB), whatever the vault weighs

    def test_push_after_publish_has_nothing_to_push(self):
        self.publisher.publish(self.vault)
        result = self.sync.push(self.vault)
        assert result['status'] == 'up_to_date'           # I6's push half

    def test_loader_is_the_bundled_template_even_when_vault_has_index_html(self):
        self.publisher.publish(self.vault)
        with open(os.path.join(self._publish_dir(), 'index.html'), 'rb') as f:
            emitted = f.read()
        assert emitted == LOADER_TEMPLATE.encode('utf-8')            # I4
        assert b'THE VAULT' not in emitted                           # no vault content, ever
        for path in self._surface_files():
            with open(os.path.join(self._publish_dir(), path), 'rb') as f:
                assert b"THE VAULT'S OWN SITE" not in f.read(), path

    def test_manifest_enumerates_store_and_walks_parents(self):
        self.publisher.publish(self.vault)
        with open(os.path.join(self._publish_dir(), 'manifest.json')) as f:
            manifest = Schema__Published_Manifest.from_json(json.load(f))
        assert str(manifest.schema)   == 'sgit_published_v1'
        assert str(manifest.vault_id) == self.vault_id
        sg_dir   = os.path.join(self.vault, '.sg_vault')
        on_disk  = []
        for root, _d, files in os.walk(os.path.join(sg_dir, 'bare')):
            for name in files:
                on_disk.append(os.path.relpath(os.path.join(root, name), sg_dir).replace(os.sep, '/'))
        assert sorted(str(o.file_id) for o in manifest.objects) == sorted(on_disk)
        for entry in manifest.objects:                    # ciphertext sha256 per object
            path = os.path.join(sg_dir, str(entry.file_id))
            with open(path, 'rb') as f:
                assert str(entry.sha256) == hashlib.sha256(f.read()).hexdigest()
            assert int(entry.size) == os.path.getsize(path)
        assert len(manifest.commits) >= 2                 # init commit + ours, via parents
        assert str(manifest.head) == str(manifest.commits[0])
        surface_paths = [str(e.path) for e in manifest.plaintext_surface]
        assert sorted(surface_paths) == ['cover.json', 'index.html', 'manifest.json']
        manifest_entry = next(e for e in manifest.plaintext_surface
                              if str(e.path) == 'manifest.json')
        assert manifest_entry.sha256 is None or str(manifest_entry.sha256) == ''

    def test_plaintext_surface_hashes_are_correct(self):
        self.publisher.publish(self.vault)
        with open(os.path.join(self._publish_dir(), 'manifest.json')) as f:
            manifest = Schema__Published_Manifest.from_json(json.load(f))
        for entry in manifest.plaintext_surface:
            if str(entry.path) == 'manifest.json':
                continue
            with open(os.path.join(self._publish_dir(), str(entry.path)), 'rb') as f:
                assert str(entry.sha256) == hashlib.sha256(f.read()).hexdigest()

    def test_publish_twice_is_byte_identical(self):
        self.publisher.publish(self.vault)
        first = _dir_digest(self._publish_dir())
        self.publisher.publish(self.vault)
        assert _dir_digest(self._publish_dir()) == first

    def test_publish_with_only_the_read_key(self):
        """A read-only clone can publish — what makes zero-secret CI work."""
        keys     = self.crypto.derive_keys_from_vault_key(self.vault_key)
        read_dir = os.path.join(self.tmp, 'ro_clone')
        self.sync.clone_read_only(self.vault_id, keys['read_key'], read_dir)
        assert not os.path.isfile(os.path.join(read_dir, '.sg_vault', 'local', 'vault_key'))
        result = self.publisher.publish(read_dir)
        assert result['vault_id'] == self.vault_id
        assert os.path.isfile(os.path.join(read_dir, '.sg_vault', 'publish', 'manifest.json'))

    def test_no_gitignore_written_and_root_gitignore_untouched(self):
        gitignore = os.path.join(self.vault, '.gitignore')
        with open(gitignore, 'w') as f:
            f.write('.sg_vault/local/\n')
        self.sync.commit(self.vault, 'track gitignore')
        self.sync.push(self.vault)
        self.publisher.publish(self.vault)
        assert not os.path.isfile(os.path.join(self._publish_dir(), '.gitignore'))
        with open(gitignore) as f:
            assert f.read() == '.sg_vault/local/\n'

    # --- P4: visibility -----------------------------------------------------

    def test_public_emits_the_public_key_file(self):
        keys = self.crypto.derive_keys_from_vault_key(self.vault_key)
        self.publisher.publish(self.vault, visibility=Enum__Visibility.PUBLIC)
        expected = f'sgit_public_read_{keys["read_key"]}'
        assert expected in self._surface_files()
        assert not any(name.startswith('sgit_private_') for name in self._surface_files())
        with open(os.path.join(self._publish_dir(), 'manifest.json')) as f:
            manifest = Schema__Published_Manifest.from_json(json.load(f))
        assert expected in [str(e.path) for e in manifest.plaintext_surface]

    def test_bare_emits_no_key_file_at_all(self):
        self.publisher.publish(self.vault, visibility=Enum__Visibility.BARE)
        assert not any('read' in name and 'sgit' in name for name in self._surface_files())

    def test_visibility_recorded_per_clone_and_downgrade_detected(self):
        self.publisher.publish(self.vault, visibility=Enum__Visibility.PUBLIC)
        pre = self.publisher.preflight(self.vault)                    # no explicit flag
        assert pre['stored']   == Enum__Visibility.PUBLIC             # this clone remembers
        assert pre['previous'] == Enum__Visibility.PUBLIC
        assert pre['is_downgrade'] is False                           # stored keeps it public
        fresh = self.publisher.preflight(self.vault, Enum__Visibility.PUBLIC)
        assert fresh['is_downgrade'] is False

    def test_fresh_clone_defaults_bare_and_would_downgrade(self):
        """The CI case (R3): a fresh clone resolves bare over a public output."""
        self.publisher.publish(self.vault, visibility=Enum__Visibility.PUBLIC)
        clone_dir = os.path.join(self.tmp, 'fresh_clone')
        self.sync.clone(self.vault_key, clone_dir)
        shutil.copytree(self._publish_dir(),
                        os.path.join(clone_dir, '.sg_vault', 'publish'))
        pre = self.publisher.preflight(clone_dir)
        assert pre['resolved']     == Enum__Visibility.BARE           # fresh clone: bare
        assert pre['is_downgrade'] is True

    # --- P3 support: staleness ----------------------------------------------

    def test_is_stale_reflects_ref_bytes(self):
        assert self.publisher.is_stale(self.vault) is True            # never published
        self.publisher.publish(self.vault)
        assert self.publisher.is_stale(self.vault) is False
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('changed content')
        self.sync.commit(self.vault, 'change')                        # moves a ref
        assert self.publisher.is_stale(self.vault) is True
        self.publisher.publish(self.vault)
        assert self.publisher.is_stale(self.vault) is False

    def test_fresh_init_vault_publishes_its_init_commit(self):
        """sgit init creates an init commit with an empty tree, so a fresh
        vault is already publishable — the parent walk must include it
        (walking a commit log would miss it)."""
        fresh = os.path.join(self.tmp, 'fresh_vault')
        self.sync.init(fresh)
        result = self.publisher.publish(fresh)
        assert result['n_commits'] >= 1

    def test_publish_outside_a_vault_fails_honestly(self):
        outside = os.path.join(self.tmp, 'not_a_vault')
        os.makedirs(outside)
        with pytest.raises(Exception):
            self.publisher.publish(outside)

    def test_publish_refuses_a_store_that_readers_would_refuse(self):
        """B2 (publish-side detection): a store whose content-addressed objects
        do not hash to their ids — the signature of a vault moved by an older
        sgit — would publish fine and then be refused by EVERY current-version
        reader, without the publisher knowing. Publish must refuse first,
        naming the remedy; the publisher holds the key and can normalise."""
        from sgit_ai.core.Vault__Errors import Vault__Integrity_Error
        data_dir = os.path.join(self.vault, '.sg_vault', 'bare', 'data')
        victim   = sorted(name for name in os.listdir(data_dir)
                          if name.startswith('obj-cas-imm-'))[0]
        with open(os.path.join(data_dir, victim), 'ab') as f:
            f.write(b'x')                       # id no longer matches the bytes
        with pytest.raises(Vault__Integrity_Error) as exc:
            self.publisher.publish(self.vault)
        message = str(exc.value)
        assert victim in message
        assert 'sgit vault move' in message     # the remedy is named
        assert not os.path.isdir(self._publish_dir())   # nothing was published
