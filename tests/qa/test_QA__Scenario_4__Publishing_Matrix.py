"""QA Scenario 4: the static-publishing matrix (P7).

The 7 invariants from 04__invariants-and-tests.md, asserted via a shared
harness, plus every cell of the 14-cell matrix that is buildable without a
live server or a browser:

  cell 1  baseline (publish → serve → read, end to end)
  cell 2  local folder needs serve (file:// has an opaque origin)
  cell 3  zip target — unpack → serve
  cell 4  object storage — a dumb HTTP host stands in (asserts I1)
  cell 7  key-classification parity (CLI side)
  cell 9  cover-only: the keyless visitor's first view
  cell 11 custody without access (= I3) + the no-manifest failure
  cell 13 generic browsing (no vault app — the loader is self-sufficient)
  cell 14 fork = clone + rekey + republish (the acceptance test)

Cells needing a real remote host (5, 10), a browser (8), or the deferred
expansion command (6, 12 → P8) are integration/Web-team scope and noted in
the phase report rather than silently skipped.

Self-contained: Vault__API__In_Memory + stdlib HTTP servers.
"""
import functools
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import urllib.request
import zipfile

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytestmark = pytest.mark.qa

from sgit_ai.crypto.Vault__Crypto                    import Vault__Crypto
from sgit_ai.core.Vault__Sync                        import Vault__Sync
from sgit_ai.core.Vault__Repo_Ignore                 import (CANONICAL_REPO_GITIGNORE,
                                                             Vault__Repo_Ignore)
from sgit_ai.core.actions.mirror.Vault__Mirror       import Vault__Mirror
from sgit_ai.core.actions.publish.Loader__Template   import LOADER_TEMPLATE
from sgit_ai.core.actions.publish.Vault__Publish     import Vault__Publish
from sgit_ai.core.serve.Vault__Static_Server         import Vault__Static_Server
from sgit_ai.network.api.Vault__API__In_Memory       import Vault__API__In_Memory
from sgit_ai.network.api.Vault__API__Static          import Vault__API__Static
from sgit_ai.safe_types.Enum__Key_Kind               import Enum__Key_Kind
from sgit_ai.safe_types.Enum__Visibility             import Enum__Visibility
from sgit_ai.safe_types.Safe_UInt__Port              import Safe_UInt__Port


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def _serve_dir(directory):
    handler = functools.partial(_QuietHandler, directory=directory)
    httpd   = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f'http://127.0.0.1:{httpd.server_address[1]}'


def _compose_site(vault_dir, dest, vault_id, layout='flat'):
    """The deployment step: surface + store, keyless copy (01 §3)."""
    publish_dir = os.path.join(vault_dir, '.sg_vault', 'publish')
    os.makedirs(dest, exist_ok=True)
    for root, _dirs, files in os.walk(publish_dir):
        for name in files:
            src = os.path.join(root, name)
            rel = os.path.relpath(src, publish_dir)
            target = os.path.join(dest, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy(src, target)
    bare = os.path.join(vault_dir, '.sg_vault', 'bare')
    if layout == 'flat':
        shutil.copytree(bare, os.path.join(dest, 'bare'))
    else:
        shutil.copytree(bare, os.path.join(dest, 'api', 'vault', 'read', vault_id, 'bare'))
    return dest


@pytest.fixture(scope='module')
def estate():
    """One published vault, PUBLIC visibility, composed both ways."""
    tmp    = tempfile.mkdtemp(prefix='sg_qa_scenario4_')
    crypto = Vault__Crypto()
    api    = Vault__API__In_Memory().setup()
    sync   = Vault__Sync(crypto=crypto, api=api)
    vault  = os.path.join(tmp, 'vault')
    result = sync.init(vault)
    with open(os.path.join(vault, 'handbook.md'), 'w') as f:
        f.write('# ACME Employee Handbook\nthe published truth\n')
    with open(os.path.join(vault, 'index.html'), 'w') as f:
        f.write('<html>THE VAULT SITE</html>')
    os.makedirs(os.path.join(vault, 'docs'))
    with open(os.path.join(vault, 'docs', 'policy.md'), 'w') as f:
        f.write('policy body\n')
    sync.commit(vault, 'initial')
    sync.push(vault)
    keys = crypto.derive_keys_from_vault_key(result['vault_key'])
    Vault__Publish(crypto=crypto, api=api).publish(vault, visibility=Enum__Visibility.PUBLIC)

    flat_site = _compose_site(vault, os.path.join(tmp, 'site_flat'), result['vault_id'], 'flat')
    api_site  = _compose_site(vault, os.path.join(tmp, 'site_api'),  result['vault_id'], 'api-path')

    yield dict(tmp=tmp, crypto=crypto, api=api, sync=sync, vault=vault,
               vault_key=result['vault_key'], vault_id=result['vault_id'],
               read_key=keys['read_key'], flat_site=flat_site, api_site=api_site,
               publish_dir=os.path.join(vault, '.sg_vault', 'publish'))
    shutil.rmtree(tmp, ignore_errors=True)


class Test_QA__Invariants:
    """The seven invariants — most risk per line (04 §1)."""

    def test_I1_served_ciphertext_is_byte_identical_to_the_store(self, estate):
        bare = os.path.join(estate['vault'], '.sg_vault', 'bare')
        for site, prefix in ((estate['flat_site'], 'bare'),
                            (estate['api_site'],
                             f'api/vault/read/{estate["vault_id"]}/bare')):
            httpd, url = _serve_dir(site)
            try:
                for root, _dirs, files in os.walk(bare):
                    for name in files:
                        rel = os.path.relpath(os.path.join(root, name), bare).replace(os.sep, '/')
                        with urllib.request.urlopen(f'{url}/{prefix}/{rel}', timeout=10) as resp:
                            served = resp.read()
                        with open(os.path.join(root, name), 'rb') as f:
                            assert served == f.read(), f'{prefix}/{rel}'
            finally:
                httpd.shutdown()

    def test_I2_no_request_ever_contains_the_key(self, estate):
        """Asserted on the RECORDED requests, not the source code."""
        import re
        httpd, url = _serve_dir(estate['flat_site'])
        try:
            transport = Vault__API__Static(base_url=url, record_requests=True)
            transport.setup()
            dest = os.path.join(estate['tmp'], 'clone_i2')
            Vault__Sync(crypto=estate['crypto'], api=transport).clone(estate['vault_key'], dest)
            assert transport.recorded_requests
            for location in transport.recorded_requests:
                assert 'sgit_private' not in location
                assert not re.search(r'[0-9a-f]{64}', location), location
                assert '?' not in location                     # no query strings at all
        finally:
            httpd.shutdown()

    def test_I3_keyless_client_takes_custody(self, estate):
        dest   = os.path.join(estate['tmp'], 'mirror_i3')
        mirror = Vault__Mirror(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())
        result = mirror.mirror(estate['flat_site'], dest)
        assert result['refused'] == []
        bare = os.path.join(estate['vault'], '.sg_vault', 'bare')
        for root, _dirs, files in os.walk(bare):
            for name in files:
                rel = os.path.relpath(os.path.join(root, name), bare).replace(os.sep, '/')
                with open(os.path.join(root, name), 'rb') as f_src, \
                     open(os.path.join(dest, 'bare', rel), 'rb') as f_dst:
                    assert f_src.read() == f_dst.read(), rel
        for root, _dirs, files in os.walk(dest):
            for name in files:
                assert not name.startswith('sgit_'), 'a mirror must write no key file'

    def test_I4_loader_is_byte_identical_across_vaults(self, estate):
        """Two more vaults — one holding its own root index.html — publish the
        SAME loader bytes, equal to the bundled template."""
        hashes = {hashlib.sha256(
            open(os.path.join(estate['publish_dir'], 'index.html'), 'rb').read()).hexdigest()}
        for own_index in (True, False):
            other = os.path.join(estate['tmp'], f'vault_i4_{own_index}')
            estate['sync'].init(other)
            with open(os.path.join(other, 'data.txt'), 'w') as f:
                f.write(f'different vault {own_index}')
            if own_index:
                with open(os.path.join(other, 'index.html'), 'w') as f:
                    f.write('<html>ANOTHER VAULT SITE</html>')
            estate['sync'].commit(other, 'initial')
            estate['sync'].push(other)
            Vault__Publish(crypto=estate['crypto'], api=estate['api']).publish(other)
            with open(os.path.join(other, '.sg_vault', 'publish', 'index.html'), 'rb') as f:
                hashes.add(hashlib.sha256(f.read()).hexdigest())
        assert len(hashes) == 1
        assert hashes == {hashlib.sha256(LOADER_TEMPLATE.encode('utf-8')).hexdigest()}

    def test_I5_publish_emits_no_vault_content(self, estate):
        """Expansion (P8) is deferred, so I5's enforceable half today is that
        the publish output holds nothing from the vault at any visibility."""
        emitted = []
        for root, _dirs, files in os.walk(estate['publish_dir']):
            for name in files:
                emitted.append(os.path.join(root, name))
        for path in emitted:
            with open(path, 'rb') as f:
                data = f.read()
            assert b'THE VAULT SITE' not in data
            assert b'the published truth' not in data
            assert b'policy body' not in data

    def test_I6_publishing_changes_nothing_but_the_publish_dir(self, estate):
        def tree_digest():
            digest = hashlib.sha256()
            for root, _dirs, files in sorted(os.walk(estate['vault'])):
                for name in sorted(files):
                    full = os.path.join(root, name)
                    rel  = os.path.relpath(full, estate['vault']).replace(os.sep, '/')
                    if rel.startswith('.sg_vault/publish/') or rel == '.sg_vault/local/config.json':
                        continue                      # config: per-clone visibility (decision 5)
                    digest.update(rel.encode())
                    with open(full, 'rb') as f:
                        digest.update(f.read())
            return digest.hexdigest()
        before = tree_digest()
        Vault__Publish(crypto=estate['crypto'], api=estate['api']).publish(
            estate['vault'], visibility=Enum__Visibility.PUBLIC)
        assert tree_digest() == before
        push = estate['sync'].push(estate['vault'])
        assert push['status'] == 'up_to_date'          # zero objects, head unchanged

    def test_I7_reader_writes_no_object_it_has_not_verified(self, estate):
        hostile = os.path.join(estate['tmp'], 'site_hostile_i7')
        shutil.copytree(estate['flat_site'], hostile)
        data_dir = os.path.join(hostile, 'bare', 'data')
        victim   = sorted(os.listdir(data_dir),
                          key=lambda n: os.path.getsize(os.path.join(data_dir, n)))[0]
        with open(os.path.join(data_dir, victim), 'wb') as f:
            f.write(b'hostile bytes that cannot hash to the id')
        httpd, url = _serve_dir(hostile)
        try:
            dest      = os.path.join(estate['tmp'], 'clone_i7')
            transport = Vault__API__Static(base_url=url)
            transport.setup()
            Vault__Sync(crypto=estate['crypto'], api=transport).clone(estate['vault_key'], dest)
            assert not os.path.exists(os.path.join(dest, '.sg_vault', 'bare', 'data', victim))
        finally:
            httpd.shutdown()

    def test_I7_object_swap_is_refused(self, estate):
        """Review A1, closed by option 3: two AUTHENTIC objects swapped between
        their ids decrypt fine but no longer hash to the ids they are served
        under, so both are refused and the substituted content never reaches the
        working copy. (Before, the key-fallback accepted them silently — that
        fallback existed only because `sgit vault move` kept stale ids, which it
        no longer does.)"""
        swap_site = os.path.join(estate['tmp'], 'site_i7_swap')
        shutil.copytree(estate['flat_site'], swap_site)
        data_dir = os.path.join(swap_site, 'bare', 'data')
        blobs    = sorted(os.listdir(data_dir),
                          key=lambda n: os.path.getsize(os.path.join(data_dir, n)))
        a, b = blobs[0], blobs[1]
        ba = open(os.path.join(data_dir, a), 'rb').read()
        bb = open(os.path.join(data_dir, b), 'rb').read()
        open(os.path.join(data_dir, a), 'wb').write(bb)
        open(os.path.join(data_dir, b), 'wb').write(ba)

        warnings = []
        httpd, url = _serve_dir(swap_site)
        try:
            transport = Vault__API__Static(base_url=url)
            transport.setup()
            dest = os.path.join(estate['tmp'], 'clone_i7_swap')
            Vault__Sync(crypto=estate['crypto'], api=transport).clone(
                estate['vault_key'], dest,
                on_progress=lambda ev, msg, detail='': warnings.append(msg) if ev == 'warning' else None)
            dest_data = os.path.join(dest, '.sg_vault', 'bare', 'data')
            written   = set(os.listdir(dest_data)) if os.path.isdir(dest_data) else set()
            assert a not in written and b not in written        # neither swap landed
            assert any('content-address' in w for w in warnings)
        finally:
            httpd.shutdown()


class Test_QA__Matrix_Cells:

    def test_cell_1_baseline_publish_serve_read(self, estate):
        server = Vault__Static_Server(root_dir=estate['publish_dir'],
                                      bare_dir=os.path.join(estate['vault'], '.sg_vault', 'bare'),
                                      vault_id=estate['vault_id'],
                                      port=Safe_UInt__Port(0), quiet=True)
        port = server.start()
        try:
            base = f'http://127.0.0.1:{port}'
            with urllib.request.urlopen(f'{base}/', timeout=10) as resp:
                assert b'Encrypted vault' in resp.read()                 # the loader
            with urllib.request.urlopen(f'{base}/manifest.json', timeout=10) as resp:
                manifest = json.loads(resp.read())
            assert manifest['vault_id'] == estate['vault_id']
            first = manifest['objects'][0]['file_id']
            with urllib.request.urlopen(
                    f'{base}/api/vault/read/{estate["vault_id"]}/{first}', timeout=10) as resp:
                assert resp.status == 200                                # composed virtually
        finally:
            server.stop()

    def test_cell_2_local_folder_requires_serve(self, estate):
        # file:// gives an opaque origin; the CLI says so, and serve fixes it.
        from sgit_ai.cli.CLI__Serve import CLI__Serve
        import argparse
        server = CLI__Serve(block=False).cmd_serve(argparse.Namespace(
            directory=estate['publish_dir'], port=0, bind='127.0.0.1', open=False))
        try:
            with urllib.request.urlopen(server.url() + 'cover.json', timeout=10) as resp:
                assert resp.status == 200
        finally:
            server.stop()

    def test_cell_3_zip_target_unpack_then_serve(self, estate):
        zip_path = os.path.join(estate['tmp'], 'site.zip')
        with zipfile.ZipFile(zip_path, 'w') as bundle:
            for root, _dirs, files in os.walk(estate['flat_site']):
                for name in files:
                    full = os.path.join(root, name)
                    bundle.write(full, os.path.relpath(full, estate['flat_site']))
        unpacked = os.path.join(estate['tmp'], 'site_unzipped')
        with zipfile.ZipFile(zip_path) as bundle:
            bundle.extractall(unpacked)
        transport = Vault__API__Static(base_url=unpacked)
        transport.setup()
        dest = os.path.join(estate['tmp'], 'clone_cell3')
        Vault__Sync(crypto=estate['crypto'], api=transport).clone(estate['vault_key'], dest)
        assert open(os.path.join(dest, 'handbook.md')).read().startswith('# ACME')

    def test_cell_4_object_storage_stand_in(self, estate):
        httpd, url = _serve_dir(estate['api_site'])                      # dumb host, api-path
        try:
            transport = Vault__API__Static(base_url=url)
            transport.setup()
            dest = os.path.join(estate['tmp'], 'clone_cell4')
            Vault__Sync(crypto=estate['crypto'], api=transport).clone(estate['vault_key'], dest)
            assert open(os.path.join(dest, 'docs', 'policy.md')).read() == 'policy body\n'
        finally:
            httpd.shutdown()

    def test_cell_7_key_classification_parity(self, estate):
        crypto = estate['crypto']
        assert crypto.classify_key('sgit_private_vault_x:y') == Enum__Key_Kind.VAULT
        assert crypto.classify_key('sgit_private_read_' + 'a' * 64) == Enum__Key_Kind.READ_PRIVATE
        assert crypto.classify_key('sgit_public_read_' + 'a' * 64)  == Enum__Key_Kind.READ_PUBLIC
        assert crypto.classify_key('a' * 64) == Enum__Key_Kind.UNKNOWN   # by declaration, never shape
        # the published key FILE round-trips through the classifier
        key_files = [name for name in os.listdir(estate['publish_dir'])
                     if name.startswith('sgit_public_read_')]
        assert len(key_files) == 1
        assert crypto.classify_key(key_files[0]) == Enum__Key_Kind.READ_PUBLIC

    def test_cell_9_cover_only_first_view(self, estate):
        httpd, url = _serve_dir(estate['flat_site'])
        try:
            with urllib.request.urlopen(f'{url}/cover.json', timeout=10) as resp:
                cover = json.loads(resp.read())
            assert cover['title']
            assert cover['public'] is True
            assert cover['updated']                                       # head-commit time
        finally:
            httpd.shutdown()

    def test_cell_11_custody_without_access_and_honest_failure(self, estate):
        mirror = Vault__Mirror(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())
        dest   = os.path.join(estate['tmp'], 'mirror_cell11')
        result = mirror.mirror(estate['flat_site'], dest)
        assert result['vault_id'] == estate['vault_id']
        empty = os.path.join(estate['tmp'], 'cell11_empty')
        os.makedirs(empty, exist_ok=True)
        httpd, url = _serve_dir(empty)
        try:
            with pytest.raises(RuntimeError) as exc:
                mirror.mirror(url, os.path.join(estate['tmp'], 'mirror_cell11_none'))
            assert 'cannot mirror without a listing' in str(exc.value)
        finally:
            httpd.shutdown()

    def test_cell_13_generic_browsing_without_vault_app(self, estate):
        """No vault app: the emitted loader alone must be self-sufficient —
        a complete HTML document that names the way in."""
        with open(os.path.join(estate['publish_dir'], 'index.html')) as f:
            loader = f.read()
        assert loader.startswith('<!doctype html>')
        assert 'sgit clone' in loader
        assert 'read key' in loader

    def test_cell_14_fork_round_trip(self, estate):
        """THE acceptance test: clone from a published target → rekey →
        publish to a different target → read it back with the NEW key."""
        crypto = estate['crypto']
        httpd, url = _serve_dir(estate['flat_site'])
        try:
            transport = Vault__API__Static(base_url=url)
            transport.setup()
            fork = os.path.join(estate['tmp'], 'fork')
            Vault__Sync(crypto=crypto, api=transport).clone(estate['vault_key'], fork)
        finally:
            httpd.shutdown()

        fork_api  = Vault__API__In_Memory().setup()                       # a different backend
        fork_sync = Vault__Sync(crypto=crypto, api=fork_api)
        rekeyed   = fork_sync.rekey(fork)
        assert rekeyed['vault_id'] != estate['vault_id']                  # unlinkable fork
        fork_sync.push(fork)                                              # advance the named ref

        Vault__Publish(crypto=crypto, api=fork_api).publish(fork, visibility=Enum__Visibility.PUBLIC)
        fork_site = _compose_site(fork, os.path.join(estate['tmp'], 'fork_site'),
                                  rekeyed['vault_id'], 'flat')
        httpd, url = _serve_dir(fork_site)
        try:
            transport = Vault__API__Static(base_url=url)
            transport.setup()
            readback = os.path.join(estate['tmp'], 'fork_readback')
            Vault__Sync(crypto=crypto, api=transport).clone(rekeyed['vault_key'], readback)
            assert open(os.path.join(readback, 'handbook.md')).read().startswith('# ACME')
        finally:
            httpd.shutdown()


class Test_QA__Repo_Side_Guards:
    """04 §4: the canonical repo-side ignore set, asserted literally."""

    def test_canonical_set_is_exactly_three_lines(self):
        assert CANONICAL_REPO_GITIGNORE == ('.sg_vault/local/',
                                            '.sg_vault/backups/',
                                            '.sg_vault_new/')

    def test_keyed_backup_never_staged_with_canonical_set(self, estate):
        """The r10 cell: keyed backup in the one-repo pattern, then
        `git add -A` — nothing under .sg_vault/backups/ is staged."""
        repo = os.path.join(estate['tmp'], 'one_repo')
        os.makedirs(repo)
        api  = Vault__API__In_Memory().setup()
        sync = Vault__Sync(crypto=Vault__Crypto(), api=api)
        sync.init(repo)
        with open(os.path.join(repo, 'file.txt'), 'w') as f:
            f.write('content')
        sync.commit(repo, 'initial')
        with open(os.path.join(repo, '.gitignore'), 'w') as f:
            f.write('\n'.join(CANONICAL_REPO_GITIGNORE) + '\n')
        subprocess.run(['git', 'init', '-q', repo], check=True)
        backups_dir = os.path.join(repo, '.sg_vault', 'backups')
        os.makedirs(backups_dir)
        with open(os.path.join(backups_dir, 'backup-with-VAULT-KEY.zip'), 'wb') as f:
            f.write(b'zip bytes standing in for a keyed backup')
        subprocess.run(['git', '-C', repo, 'add', '-A'], check=True)
        staged = subprocess.run(['git', '-C', repo, 'diff', '--cached', '--name-only'],
                                capture_output=True, text=True, check=True).stdout
        assert '.sg_vault/backups' not in staged
        assert '.sg_vault/local'   not in staged
        assert 'file.txt' in staged                       # ordinary content IS staged

    def test_missing_lines_detection_and_ensure(self, estate):
        repo_ignore = Vault__Repo_Ignore()
        tmp = os.path.join(estate['tmp'], 'ignore_check')
        os.makedirs(tmp, exist_ok=True)
        with open(os.path.join(tmp, '.gitignore'), 'w') as f:
            f.write('.sg_vault/local/\n')                 # tabletop 10's insufficient set
        missing = repo_ignore.missing_lines(tmp)
        assert '.sg_vault/backups/' in missing            # the line that guards the key
        assert '.sg_vault_new/'     in missing
        added = repo_ignore.ensure(tmp)
        assert added == missing
        assert repo_ignore.missing_lines(tmp) == []
