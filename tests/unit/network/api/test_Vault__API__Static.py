"""P1 — the static read transport, exercised end-to-end with real clones
against a plain folder and a stdlib HTTP server (the sanctioned no-live-server
harness, 04 §4). Includes the F5 dead-host fixtures and the SP-1 hostile-host
fixture (an object whose bytes do not hash to its id)."""
import functools
import os
import shutil
import socket
import tempfile
import threading

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from sgit_ai.crypto.Vault__Crypto                   import Vault__Crypto
from sgit_ai.core.Vault__Sync                       import Vault__Sync
from sgit_ai.network.api.Vault__API__In_Memory      import Vault__API__In_Memory
from sgit_ai.network.api.Vault__API__Static         import Vault__API__Static
from sgit_ai.network.api.Vault__API__Auto           import Vault__API__Auto
from sgit_ai.network.api.Vault__Transport_Errors    import (Vault__Read_Only_Transport_Error,
                                                            Vault__Static_Transport_Error)
from sgit_ai.safe_types.Enum__Published_Layout      import Enum__Published_Layout
from sgit_ai.safe_types.Enum__Transport             import Enum__Transport


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def _serve(directory):
    handler = functools.partial(_QuietHandler, directory=directory)
    httpd   = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f'http://127.0.0.1:{httpd.server_address[1]}'


@pytest.fixture(scope='module')
def published_vault():
    """A committed vault (store complete locally — no push needed) plus the two
    serving layouts, built once for the module."""
    tmp    = tempfile.mkdtemp(prefix='static_transport_')
    crypto = Vault__Crypto()
    api    = Vault__API__In_Memory()
    api.setup()
    sync   = Vault__Sync(crypto=crypto, api=api)
    origin = os.path.join(tmp, 'origin')
    result = sync.init(origin)
    with open(os.path.join(origin, 'hello.txt'), 'w') as f:
        f.write('served over plain GET')
    os.makedirs(os.path.join(origin, 'docs'))
    with open(os.path.join(origin, 'docs', 'page.md'), 'w') as f:
        f.write('# Page\n')
    with open(os.path.join(origin, 'big.bin'), 'wb') as f:
        f.write(os.urandom(5 * 1024 * 1024))          # > LARGE_BLOB_THRESHOLD (4 MB)
    sync.commit(origin, 'initial')
    sync.push(origin)                                 # advance the NAMED ref clones follow

    flat = os.path.join(tmp, 'site_flat')             # bare/ at the web root
    shutil.copytree(os.path.join(origin, '.sg_vault'), flat)
    api_root = os.path.join(tmp, 'site_api')          # mirrors live-API paths
    api_like = os.path.join(api_root, 'api', 'vault', 'read', result['vault_id'])
    os.makedirs(os.path.dirname(api_like))
    shutil.copytree(os.path.join(origin, '.sg_vault'), api_like)

    yield dict(tmp=tmp, vault_key=result['vault_key'], vault_id=result['vault_id'],
               flat=flat, api_root=api_root)
    shutil.rmtree(tmp, ignore_errors=True)


def _clone(base_url, vault_key, dest):
    static = Vault__API__Static(base_url=base_url)
    static.setup()
    Vault__Sync(crypto=Vault__Crypto(), api=static).clone(vault_key, dest)
    return static


class Test_Vault__API__Static__Clone:

    def test_clone_from_local_folder(self, published_vault):
        dest   = os.path.join(published_vault['tmp'], 'clone_folder')
        static = _clone(published_vault['flat'], published_vault['vault_key'], dest)
        assert open(os.path.join(dest, 'hello.txt')).read()       == 'served over plain GET'
        assert open(os.path.join(dest, 'docs', 'page.md')).read() == '# Page\n'
        assert static.layout == Enum__Published_Layout.FLAT

    def test_clone_from_http_server_flat_layout(self, published_vault):
        httpd, url = _serve(published_vault['flat'])
        try:
            dest   = os.path.join(published_vault['tmp'], 'clone_http_flat')
            static = _clone(url, published_vault['vault_key'], dest)
            assert open(os.path.join(dest, 'hello.txt')).read() == 'served over plain GET'
            assert static.layout == Enum__Published_Layout.FLAT
        finally:
            httpd.shutdown()

    def test_clone_from_http_server_api_path_layout(self, published_vault):
        httpd, url = _serve(published_vault['api_root'])
        try:
            dest   = os.path.join(published_vault['tmp'], 'clone_http_api')
            static = _clone(url, published_vault['vault_key'], dest)
            assert open(os.path.join(dest, 'hello.txt')).read() == 'served over plain GET'
            assert static.layout == Enum__Published_Layout.API_PATH
        finally:
            httpd.shutdown()

    def test_large_blob_clone_over_http(self, published_vault):
        """> 4 MB blobs go through presigned_read_url — a size-dependent path
        that small fixtures never touch."""
        httpd, url = _serve(published_vault['flat'])
        try:
            dest = os.path.join(published_vault['tmp'], 'clone_http_large')
            _clone(url, published_vault['vault_key'], dest)
            assert os.path.getsize(os.path.join(dest, 'big.bin')) == 5 * 1024 * 1024
        finally:
            httpd.shutdown()

    def test_requests_never_contain_key_material(self, published_vault):
        """I2: assert on the recorded requests, not on the source code."""
        import re
        static = Vault__API__Static(base_url=published_vault['flat'], record_requests=True)
        static.setup()
        dest = os.path.join(published_vault['tmp'], 'clone_recorded')
        Vault__Sync(crypto=Vault__Crypto(), api=static).clone(published_vault['vault_key'], dest)
        assert len(static.recorded_requests) > 0
        for location in static.recorded_requests:
            assert 'sgit_private' not in location
            assert not re.search(r'[0-9a-f]{64}', location), f'64-hex string in request: {location}'


class Test_Vault__API__Static__Errors:

    def test_absent_object_is_none(self, published_vault):
        static = Vault__API__Static(base_url=published_vault['flat'])
        static.setup()
        assert static.read('anyvault', 'bare/data/obj-cas-imm-000000000000') is None

    def test_http_404_is_none(self, published_vault):
        httpd, url = _serve(published_vault['flat'])
        try:
            static = Vault__API__Static(base_url=url)
            static.setup()
            assert static.read('anyvault', 'bare/data/obj-cas-imm-000000000000') is None
        finally:
            httpd.shutdown()

    def test_dead_host_raises_naming_host_not_empty_vault(self):
        """F5: a closed port must raise loudly, naming the host — never
        diagnose as 'no branch index and no named ref'."""
        probe = socket.socket()
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
        probe.close()                                  # port now closed
        static = Vault__API__Static(base_url=f'http://127.0.0.1:{port}')
        static.setup()
        with pytest.raises(Vault__Static_Transport_Error) as exc:
            static.read('anyvault', 'bare/refs/ref-pid-muw-000000000000')
        message = str(exc.value)
        assert f'127.0.0.1:{port}' in message
        assert 'transport failure' in message
        assert 'no named ref' not in message

    def test_resetting_host_raises_transport_error(self):
        """F5 variant: a listener that accepts and immediately resets."""
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        port    = listener.getsockname()[1]
        stopped = threading.Event()

        def reset_all():
            while not stopped.is_set():
                try:
                    listener.settimeout(0.2)
                    conn, _addr = listener.accept()
                    conn.close()                       # reset before any response
                except socket.timeout:
                    continue
                except OSError:
                    return

        thread = threading.Thread(target=reset_all, daemon=True)
        thread.start()
        try:
            static = Vault__API__Static(base_url=f'http://127.0.0.1:{port}')
            static.setup()
            with pytest.raises(Vault__Static_Transport_Error):
                static.read('anyvault', 'bare/refs/ref-pid-muw-000000000000')
        finally:
            stopped.set()
            listener.close()

    def test_dead_host_aborts_batch_read_loudly(self):
        probe = socket.socket()
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
        probe.close()
        static = Vault__API__Static(base_url=f'http://127.0.0.1:{port}')
        static.setup()
        with pytest.raises(Vault__Static_Transport_Error):
            static.batch_read('anyvault', ['bare/refs/ref-pid-muw-000000000000'])

    def test_writes_raise_read_only_transport_error(self, published_vault):
        static = Vault__API__Static(base_url=published_vault['flat'])
        static.setup()
        with pytest.raises(Vault__Read_Only_Transport_Error) as exc:
            static.write('anyvault', 'bare/data/x', 'writekey', b'data')
        assert 'read-only' in str(exc.value)
        with pytest.raises(Vault__Read_Only_Transport_Error):
            static.delete('anyvault', 'bare/data/x', 'writekey')
        with pytest.raises(Vault__Read_Only_Transport_Error):
            static.batch('anyvault', 'writekey', [])

    def test_setup_requires_base_url(self):
        with pytest.raises(ValueError):
            Vault__API__Static().setup()

    def test_local_read_refuses_traversal_file_id(self, published_vault, tmp_path):
        """A4: a manifest-supplied file_id with ../ must not read outside the
        served folder — symmetric with mirror's write-side guard (SP-8)."""
        secret = tmp_path / 'secret.txt'
        secret.write_text('must never be read')
        served = tmp_path / 'served'
        served.mkdir()
        (served / 'bare').mkdir()
        static = Vault__API__Static(base_url=str(served))
        static.setup()
        assert static.read('anyvault', '../secret.txt')       is None
        assert static.read('anyvault', 'bare/../../secret.txt') is None

    def test_non_404_status_is_typed_and_fails_soft_in_batch(self):
        """A5: a per-object non-404 status is a typed Vault__Static_Object_Error
        and does not abort a batch_read — it is recorded and the run continues."""
        import functools, threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from sgit_ai.network.api.Vault__Transport_Errors import Vault__Static_Object_Error

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass
            def do_GET(self):
                if 'forbidden' in self.path:
                    self.send_response(403); self.end_headers()
                elif 'ok' in self.path:
                    self.send_response(200); self.end_headers(); self.wfile.write(b'DATA')
                else:
                    self.send_response(404); self.end_headers()

        httpd = ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{httpd.server_address[1]}'
        try:
            static = Vault__API__Static(base_url=url)
            static.setup()
            static.layout = Enum__Published_Layout.FLAT       # skip sniffing
            with pytest.raises(Vault__Static_Object_Error):   # a direct read surfaces it
                static.read('v', 'forbidden-object')
            failures = {}
            result   = static.batch_read('v', ['ok-object', 'forbidden-object'], failures=failures)
            assert result['ok-object']        == b'DATA'       # the run continued
            assert result['forbidden-object'] is None
            assert 'forbidden-object' in failures
        finally:
            httpd.shutdown()


class Test_Vault__API__Static__SP1_Integrity:

    def test_corrupt_object_is_skipped_not_written(self, published_vault):
        """SP-1 / I7: a served obj-cas-imm-* whose bytes do not hash to its id
        is rejected before the write, per object — the clone still completes."""
        hostile = os.path.join(published_vault['tmp'], 'site_hostile')
        if os.path.isdir(hostile):
            shutil.rmtree(hostile)
        shutil.copytree(published_vault['flat'], hostile)
        data_dir = os.path.join(hostile, 'bare', 'data')
        # tamper the SMALLEST data object (a blob) so the walk itself survives
        blobs = sorted(os.listdir(data_dir),
                       key=lambda name: os.path.getsize(os.path.join(data_dir, name)))
        victim = blobs[0]
        with open(os.path.join(data_dir, victim), 'wb') as f:
            f.write(b'tampered bytes that cannot hash to the id')

        dest   = os.path.join(published_vault['tmp'], 'clone_hostile')
        static = Vault__API__Static(base_url=hostile)
        static.setup()
        Vault__Sync(crypto=Vault__Crypto(), api=static).clone(published_vault['vault_key'], dest)

        cloned_path = os.path.join(dest, '.sg_vault', 'bare', 'data', victim)
        assert not os.path.exists(cloned_path)         # refused, never written

    def test_object_swap_is_surfaced_by_a_warning(self, published_vault):
        """A1 (review finding): two AUTHENTIC ciphertexts swapped between their
        ids both fail their content address but decrypt under the key. They are
        written (the content survives) BUT a warning must now be printed —
        the silent-substitution hole the review reproduced."""
        swap_site = os.path.join(published_vault['tmp'], 'site_swap')
        if os.path.isdir(swap_site):
            shutil.rmtree(swap_site)
        shutil.copytree(published_vault['flat'], swap_site)
        data_dir = os.path.join(swap_site, 'bare', 'data')
        blobs    = sorted(os.listdir(data_dir),
                          key=lambda name: os.path.getsize(os.path.join(data_dir, name)))
        a, b = blobs[0], blobs[1]
        ba = open(os.path.join(data_dir, a), 'rb').read()
        bb = open(os.path.join(data_dir, b), 'rb').read()
        open(os.path.join(data_dir, a), 'wb').write(bb)          # swap two authentic objects
        open(os.path.join(data_dir, b), 'wb').write(ba)

        warnings = []
        def record(event, message, detail=''):
            if event == 'warning':
                warnings.append(f'{message} {detail}')
        dest   = os.path.join(published_vault['tmp'], 'clone_swap')
        static = Vault__API__Static(base_url=swap_site)
        static.setup()
        Vault__Sync(crypto=Vault__Crypto(), api=static).clone(
            published_vault['vault_key'], dest, on_progress=record)

        joined = ' '.join(warnings)
        assert 'did not match their content address' in joined
        assert 'substituted objects' in joined                  # the substitution risk is named

    def test_verified_write_verdicts(self, tmp_path):
        from sgit_ai.storage.Vault__Verified_Write import Vault__Verified_Write
        W      = Vault__Verified_Write
        crypto = Vault__Crypto()
        writer = W(crypto=crypto)
        data   = b'some ciphertext bytes'
        good   = crypto.compute_object_id(data)
        assert writer.save(str(tmp_path), f'bare/data/{good}', data) == W.VERIFIED
        assert os.path.isfile(tmp_path / 'bare' / 'data' / good)
        assert writer.save(str(tmp_path), 'bare/data/obj-cas-imm-deadbeef0000', data) == W.REFUSED
        assert not os.path.exists(tmp_path / 'bare' / 'data' / 'obj-cas-imm-deadbeef0000')
        assert writer.save(str(tmp_path), '../../escape', data) == W.REFUSED
        # non-content-addressed names (refs/keys/indexes) are written as-is
        assert writer.save(str(tmp_path), 'bare/refs/ref-pid-muw-aaaaaaaaaaaa', data) == W.VERIFIED

    def test_verified_write_authenticated_fallback_only_with_key(self, tmp_path):
        """A1: a CAS mismatch that decrypts under the key is AUTHENTICATED (not
        VERIFIED) when a key is present, and REFUSED for a keyless caller."""
        from sgit_ai.storage.Vault__Verified_Write import Vault__Verified_Write
        W      = Vault__Verified_Write
        crypto = Vault__Crypto()
        keys   = crypto.derive_keys_from_vault_key('verifyfallbackpass012345:vfallbvlt')
        read_key = keys['read_key_bytes']
        cipher   = crypto.encrypt(read_key, b'authentic plaintext')
        wrong_id = 'bare/data/obj-cas-imm-000000000000'          # decrypts, but wrong id
        assert W(crypto=crypto).classify(wrong_id, cipher, read_key=read_key) == W.AUTHENTICATED
        assert W(crypto=crypto).classify(wrong_id, cipher, read_key=None)     == W.REFUSED  # keyless
        garbage = b'not a valid ciphertext at all'
        assert W(crypto=crypto).classify(wrong_id, garbage, read_key=read_key) == W.REFUSED


class Test_Vault__API__Auto:

    def test_folder_resolves_local(self, published_vault):
        auto = Vault__API__Auto(base_url=published_vault['flat'])
        auto.setup()
        assert auto.resolved == Enum__Transport.LOCAL
        assert 'local' in auto.describe()
        dest = os.path.join(published_vault['tmp'], 'clone_auto_folder')
        Vault__Sync(crypto=Vault__Crypto(), api=auto).clone(published_vault['vault_key'], dest)
        assert open(os.path.join(dest, 'hello.txt')).read() == 'served over plain GET'

    def test_http_static_host_flips_to_static(self, published_vault, capsys):
        """A plain file server has no batch endpoint (POST → 501): auto must
        remember the static transport and say so."""
        httpd, url = _serve(published_vault['flat'])
        try:
            auto = Vault__API__Auto(base_url=url)
            auto.setup()
            dest = os.path.join(published_vault['tmp'], 'clone_auto_http')
            Vault__Sync(crypto=Vault__Crypto(), api=auto).clone(published_vault['vault_key'], dest)
            assert auto.resolved == Enum__Transport.STATIC
            assert 'static' in auto.describe()
            assert 'static read-only transport' in capsys.readouterr().err
        finally:
            httpd.shutdown()
