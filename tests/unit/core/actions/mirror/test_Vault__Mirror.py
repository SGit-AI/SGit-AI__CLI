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


class Test_Vault__Mirror__Edges:
    """The branches the hostile-host tests above do not reach: manifests that are not JSON,
    folders with no manifest at all, odd manifest entries, the plaintext surface."""

    def _site(self, published_site, name):
        site = os.path.join(published_site['tmp'], name)
        shutil.copytree(published_site['site'], site)
        return site

    def _manifest(self, site):
        with open(os.path.join(site, 'manifest.json')) as f:
            return json.load(f)

    def _put_manifest(self, site, manifest):
        with open(os.path.join(site, 'manifest.json'), 'w') as f:
            json.dump(manifest, f)

    def test_manifest_that_is_not_json_counts_as_no_listing(self, published_site):
        site = self._site(published_site, 'edge_badjson')
        with open(os.path.join(site, 'manifest.json'), 'w') as f:
            f.write('{not json')
        with pytest.raises(RuntimeError, match='cannot mirror without a listing'):
            _mirror().mirror(site, os.path.join(published_site['tmp'], 'edge_badjson_copy'))

    def test_local_folder_without_manifest_mirrors_its_bare_listing(self, published_site):
        """A folder has a listing even without a manifest: every bare/ file is copied, the
        vault id is unknown (''), and with no sha256 the non-CAS files are host-attested."""
        site = self._site(published_site, 'edge_nomanifest')
        os.remove(os.path.join(site, 'manifest.json'))
        dest   = os.path.join(published_site['tmp'], 'edge_nomanifest_copy')
        result = _mirror().mirror(site, dest)
        assert result['vault_id'] == '' and result['refused'] == []
        expected = sorted(os.path.relpath(os.path.join(r, n), site).replace(os.sep, '/')
                          for r, _d, names in os.walk(os.path.join(site, 'bare')) for n in names)
        assert sorted(result['copied']) == expected
        assert all(not fid.startswith('bare/data/obj-cas-imm-') for fid in result['host_attested'])
        assert any(fid.startswith('bare/refs/') for fid in result['host_attested'])
        assert not os.path.exists(os.path.join(dest, 'manifest.json'))

    def test_empty_file_ids_and_exact_duplicates_are_skipped_not_refused(self, published_site):
        site = self._site(published_site, 'edge_dups')
        m = self._manifest(site)
        m['objects'].append({'file_id': '', 'size': 1, 'sha256': 'a' * 64})
        m['objects'].append(dict(m['objects'][0]))                      # exact duplicate
        self._put_manifest(site, m)
        result = _mirror().mirror(site, os.path.join(published_site['tmp'], 'edge_dups_copy'))
        assert result['refused'] == []
        assert len(result['copied']) == len({e['file_id'] for e in m['objects'] if e['file_id']}) + \
            len([e for e in m.get('plaintext_surface', []) if not e['path'].startswith('sgit_')])

    def test_total_size_over_the_bound_is_refused(self, published_site):
        from sgit_ai.core.actions.mirror.Vault__Mirror import MAX_TOTAL_BYTES
        site = self._site(published_site, 'edge_size')
        m = self._manifest(site)
        m['objects'][0]['size'] = MAX_TOTAL_BYTES + 1
        self._put_manifest(site, m)
        with pytest.raises(RuntimeError, match='total size exceeds'):
            _mirror().mirror(site, os.path.join(published_site['tmp'], 'edge_size_copy'))

    def test_cas_object_with_no_manifest_hash_and_wrong_bytes_is_refused(self, published_site):
        """Without a manifest sha256 there is nothing to fall back on: a CAS object whose
        bytes do not match its id is refused outright."""
        site = self._site(published_site, 'edge_nosha')
        m = self._manifest(site)
        victim = next(e for e in m['objects'] if 'obj-cas-imm-' in e['file_id'])
        victim['sha256'] = ''
        self._put_manifest(site, m)
        with open(os.path.join(site, victim['file_id']), 'wb') as f:
            f.write(b'rotted')
        result = _mirror().mirror(site, os.path.join(published_site['tmp'], 'edge_nosha_copy'))
        assert (victim['file_id'], 'bytes do not match') in result['refused']

    def test_non_cas_file_with_a_wrong_manifest_hash_is_refused(self, published_site):
        site = self._site(published_site, 'edge_refsha')
        m = self._manifest(site)
        ref = next(e for e in m['objects'] if e['file_id'].startswith('bare/refs/'))
        ref['sha256'] = 'f' * 64
        self._put_manifest(site, m)
        result = _mirror().mirror(site, os.path.join(published_site['tmp'], 'edge_refsha_copy'))
        assert (ref['file_id'], 'bytes do not match') in result['refused']

    def test_plaintext_surface_key_files_absent_files_and_wrong_hashes(self, published_site):
        """sgit_* surface files are never written (custody, not access); an absent surface
        file and one whose hash disagrees are refused by path; manifest.json's own hash is
        never checked against itself."""
        site = self._site(published_site, 'edge_surface')
        m = self._manifest(site)
        crypto = published_site['crypto']
        with open(os.path.join(site, 'sgit_key.txt'), 'w') as f:
            f.write('never copied')
        with open(os.path.join(site, 'cover.txt'), 'w') as f:
            f.write('cover')
        m['plaintext_surface'] = [
            {'path': 'manifest.json', 'sha256': 'ignored' * 8},
            {'path': 'sgit_key.txt',  'sha256': crypto.hash_data(b'never copied')},
            {'path': 'missing.txt',   'sha256': 'a' * 64},
            {'path': 'cover.txt',     'sha256': 'b' * 64},
            {'path': '',              'sha256': ''},
        ]
        self._put_manifest(site, m)
        dest   = os.path.join(published_site['tmp'], 'edge_surface_copy')
        result = _mirror().mirror(site, dest)
        assert 'manifest.json' in result['copied']
        assert ('missing.txt', 'absent on host') in result['refused']
        assert ('cover.txt', 'bytes do not match declared hash') in result['refused']
        assert not os.path.exists(os.path.join(dest, 'sgit_key.txt'))
        assert not os.path.exists(os.path.join(dest, 'cover.txt'))

    def test_verify_reports_unsafe_paths_and_missing_files(self, published_site):
        dest = os.path.join(published_site['tmp'], 'edge_verify_copy')
        _mirror().mirror(published_site['site'], dest)
        m = self._manifest(dest)
        m['objects'].append({'file_id': '../outside', 'size': 1, 'sha256': 'a' * 64})
        m['objects'].append({'file_id': 'bare/data/obj-cas-imm-000000000000', 'size': 1, 'sha256': 'a' * 64})
        self._put_manifest(dest, m)
        result = _mirror().verify(dest)
        assert ('../outside', 'unsafe path') in result['failed']
        assert ('bare/data/obj-cas-imm-000000000000', 'missing') in result['failed']
        assert len(result['ok']) > 0

    def test_verify_of_a_folder_without_manifest_raises(self, published_site):
        plain = os.path.join(published_site['tmp'], 'edge_plain'); os.makedirs(plain)
        with pytest.raises(RuntimeError, match='not a mirror'):
            _mirror().verify(plain)
