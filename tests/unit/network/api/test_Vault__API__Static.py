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

    def test_verified_write_refuses_wrong_bytes_and_traversal(self, tmp_path):
        from sgit_ai.storage.Vault__Verified_Write import Vault__Verified_Write
        crypto = Vault__Crypto()
        writer = Vault__Verified_Write(crypto=crypto)
        data   = b'some ciphertext bytes'
        good   = crypto.compute_object_id(data)
        assert writer.save(str(tmp_path), f'bare/data/{good}', data) is True
        assert os.path.isfile(tmp_path / 'bare' / 'data' / good)
        assert writer.save(str(tmp_path), 'bare/data/obj-cas-imm-deadbeef0000', data) is False
        assert not os.path.exists(tmp_path / 'bare' / 'data' / 'obj-cas-imm-deadbeef0000')
        assert writer.save(str(tmp_path), '../../escape', data) is False
        # non-content-addressed names (refs/keys/indexes) are written as-is
        assert writer.save(str(tmp_path), 'bare/refs/ref-pid-muw-aaaaaaaaaaaa', data) is True


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
