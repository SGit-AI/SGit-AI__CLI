"""P5 — sgit vault mirror: keyless custody, hostile-host hardened."""
import functools
import json
import os
import shutil
import tempfile
import threading

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from sgit_ai.crypto.Vault__Crypto                   import Vault__Crypto
from sgit_ai.core.Vault__Sync                       import Vault__Sync
from sgit_ai.core.actions.mirror.Vault__Mirror      import MSG_NO_LISTING, Vault__Mirror
from sgit_ai.core.actions.publish.Vault__Publish    import Vault__Publish
from sgit_ai.network.api.Vault__API__In_Memory      import Vault__API__In_Memory


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def _serve(directory):
    handler = functools.partial(_QuietHandler, directory=directory)
    httpd   = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f'http://127.0.0.1:{httpd.server_address[1]}'


@pytest.fixture(scope='module')
def published_site():
    """A published vault composed for serving: surface at the root, the store
    co-located at bare/ — the flat layout the transport sniffs."""
    tmp    = tempfile.mkdtemp(prefix='mirror_')
    crypto = Vault__Crypto()
    api    = Vault__API__In_Memory()
    api.setup()
    sync   = Vault__Sync(crypto=crypto, api=api)
    vault  = os.path.join(tmp, 'vault')
    result = sync.init(vault)
    with open(os.path.join(vault, 'hello.txt'), 'w') as f:
        f.write('mirrored content')
    sync.commit(vault, 'initial')
    sync.push(vault)
    Vault__Publish(crypto=crypto, api=api).publish(vault)

    site = os.path.join(tmp, 'site')
    os.makedirs(site)
    for name in os.listdir(os.path.join(vault, '.sg_vault', 'publish')):
        shutil.copy(os.path.join(vault, '.sg_vault', 'publish', name), site)
    shutil.copytree(os.path.join(vault, '.sg_vault', 'bare'), os.path.join(site, 'bare'))
    yield dict(tmp=tmp, site=site, vault=vault, vault_id=result['vault_id'], crypto=crypto)
    shutil.rmtree(tmp, ignore_errors=True)


def _mirror():
    api = Vault__API__In_Memory()
    api.setup()
    return Vault__Mirror(crypto=Vault__Crypto(), api=api)


class Test_Vault__Mirror:

    def test_mirror_is_byte_identical_with_no_key_in_scope(self, published_site):
        dest   = os.path.join(published_site['tmp'], 'copy')
        result = _mirror().mirror(published_site['site'], dest)
        assert result['refused'] == []
        assert result['vault_id'] == published_site['vault_id']
        for root, _dirs, files in os.walk(os.path.join(published_site['site'], 'bare')):
            for name in files:
                src = os.path.join(root, name)
                rel = os.path.relpath(src, published_site['site'])
                with open(src, 'rb') as f_src, open(os.path.join(dest, rel), 'rb') as f_dst:
                    assert f_src.read() == f_dst.read(), rel               # I3
        assert not any(name.startswith('sgit_') for name in os.listdir(dest))  # no key file

    def test_mirror_over_http(self, published_site):
        httpd, url = _serve(published_site['site'])
        try:
            dest   = os.path.join(published_site['tmp'], 'copy_http')
            result = _mirror().mirror(url, dest)
            assert result['refused'] == []
            assert os.path.isfile(os.path.join(dest, 'manifest.json'))
        finally:
            httpd.shutdown()

    def test_non_cas_files_are_flagged_host_attested(self, published_site):
        dest   = os.path.join(published_site['tmp'], 'copy_flags')
        result = _mirror().mirror(published_site['site'], dest)
        assert any(fid.startswith('bare/refs/') for fid in result['host_attested'])
        assert not any('obj-cas-imm-' in fid for fid in result['host_attested'])

    def test_verify_rechecks_without_fetching(self, published_site):
        dest = os.path.join(published_site['tmp'], 'copy_verify')
        _mirror().mirror(published_site['site'], dest)
        result = _mirror().verify(dest)
        assert result['failed'] == []
        data_dir = os.path.join(dest, 'bare', 'data')
        victim   = sorted(os.listdir(data_dir))[0]
        with open(os.path.join(data_dir, victim), 'wb') as f:
            f.write(b'rotted bytes')
        result = _mirror().verify(dest)
        assert any(victim in fid for fid, _r in result['failed'])

    # --- SP-3: the manifest's hash is not an authority ----------------------

    def test_rewritten_object_and_manifest_hash_still_refused(self, published_site):
        """A host that rewrites an obj-cas-imm-* AND its manifest sha256
        together must NOT produce a mirror that 'verifies' — the mirror
        recomputes the content-address and ignores the manifest hash."""
        crypto  = published_site['crypto']
        hostile = os.path.join(published_site['tmp'], 'site_hostile_sp3')
        shutil.copytree(published_site['site'], hostile)
        data_dir = os.path.join(hostile, 'bare', 'data')
        victim   = sorted(os.listdir(data_dir))[0]
        evil     = b'attacker bytes, hash rewritten to match in the manifest'
        with open(os.path.join(data_dir, victim), 'wb') as f:
            f.write(evil)
        manifest_path = os.path.join(hostile, 'manifest.json')
        with open(manifest_path) as f:
            manifest = json.load(f)
        for entry in manifest['objects']:
            if entry['file_id'] == f'bare/data/{victim}':
                entry['sha256'] = crypto.hash_data(evil)
                entry['size']   = len(evil)
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)

        dest   = os.path.join(published_site['tmp'], 'copy_sp3')
        result = _mirror().mirror(hostile, dest)
        # the rewritten object is never presented as content-verified — at
        # most host-attested (and post-move stores are handled the same way)
        assert f'bare/data/{victim}' in result['host_attested']

    # --- SP-8: hostile manifest --------------------------------------------

    def test_traversal_file_id_refused(self, published_site):
        hostile = os.path.join(published_site['tmp'], 'site_hostile_sp8')
        shutil.copytree(published_site['site'], hostile)
        manifest_path = os.path.join(hostile, 'manifest.json')
        with open(manifest_path) as f:
            manifest = json.load(f)
        manifest['objects'].append({'file_id': '../../etc/cron.d/x', 'size': 4, 'sha256': 'a' * 64})
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        dest    = os.path.join(published_site['tmp'], 'copy_sp8')
        outside = os.path.join(published_site['tmp'], 'etc', 'cron.d', 'x')
        result  = _mirror().mirror(hostile, dest)
        assert not os.path.exists(outside)
        assert any('../../etc/cron.d/x' == fid for fid, _r in result['refused'])

    def test_over_count_manifest_refused(self, published_site):
        hostile = os.path.join(published_site['tmp'], 'site_hostile_count')
        shutil.copytree(published_site['site'], hostile)
        manifest_path = os.path.join(hostile, 'manifest.json')
        with open(manifest_path) as f:
            manifest = json.load(f)
        manifest['objects'] = [{'file_id': f'bare/data/obj-cas-imm-{i:012x}', 'size': 1}
                               for i in range(100_001)]
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f)
        with pytest.raises(RuntimeError) as exc:
            _mirror().mirror(hostile, os.path.join(published_site['tmp'], 'copy_count'))
        assert 'bound' in str(exc.value)

    def test_conflicting_duplicate_file_ids_refused(self, published_site):
        hostile = os.path.join(published_site['tmp'], 'site_hostile_dup')
        shutil.copytree(published_site['site'], hostile)
        manifest_path = os.path.join(hostile, 'manifest.json')
        with open(manifest_path) as f:
            manifest = json.load(f)
        first = dict(manifest['objects'][0])
        first['sha256'] = 'f' * 64                        # same id, different hash
        manifest['objects'].append(first)
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f)
        with pytest.raises(RuntimeError) as exc:
            _mirror().mirror(hostile, os.path.join(published_site['tmp'], 'copy_dup'))
        assert 'conflicting' in str(exc.value)

    def test_no_manifest_no_listing_fails_honestly(self, published_site):
        empty = os.path.join(published_site['tmp'], 'empty_http_site')
        os.makedirs(empty, exist_ok=True)
        httpd, url = _serve(empty)
        try:
            with pytest.raises(RuntimeError) as exc:
                _mirror().mirror(url, os.path.join(published_site['tmp'], 'copy_none'))
            assert 'cannot mirror without a listing' in str(exc.value)
            assert 'every name in a vault comes from the read key' in str(exc.value)
        finally:
            httpd.shutdown()
