"""P4b — fetch-verify-cache for --api-docs=bundled: the hash decides."""
import functools
import os
import shutil
import tempfile
import threading

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from sgit_ai.network.assets.Swagger_UI__Assets import Swagger_UI__Assets


class _Local_Assets(Swagger_UI__Assets):
    """The real fetch-verify-cache machinery pointed at a LOCAL origin with
    fixture bytes and their true SRI hashes — no network, no mocks."""
    origin_url : object = None
    pins       : object = None

    def expected_files(self) -> dict:
        return self.pins

    def origins(self) -> tuple:
        return (self.origin_url + '/{name}',)


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture()
def asset_env():
    tmp    = tempfile.mkdtemp(prefix='swagger_assets_')
    origin = os.path.join(tmp, 'origin')
    cache  = os.path.join(tmp, 'cache')
    os.makedirs(origin)
    files = {'swagger-ui.css': b'body { color: red }', 'swagger-ui-bundle.js': b'window.x=1;'}
    for name, data in files.items():
        with open(os.path.join(origin, name), 'wb') as f:
            f.write(data)
    handler = functools.partial(_QuietHandler, directory=origin)
    httpd   = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url  = f'http://127.0.0.1:{httpd.server_address[1]}'
    pins = {name: Swagger_UI__Assets().sri_hash(data) for name, data in files.items()}
    yield dict(tmp=tmp, origin=origin, cache=cache, url=url, files=files, pins=pins)
    httpd.shutdown()
    shutil.rmtree(tmp, ignore_errors=True)


class Test_Swagger_UI__Assets:

    def test_sri_hash_shape(self):
        value = Swagger_UI__Assets().sri_hash(b'hello')
        assert value.startswith('sha384-')
        assert len(value) == len('sha384-') + 64             # base64 of 48 bytes

    def test_fetch_verifies_and_caches(self, asset_env):
        assets = _Local_Assets(cache_root=asset_env['cache'],
                               origin_url=asset_env['url'], pins=asset_env['pins'])
        result = assets.get_files()
        assert result == asset_env['files']
        for name in asset_env['files']:
            assert os.path.isfile(os.path.join(assets.cache_dir(), name))
        # second call is served from the cache even with the origin gone
        assets_offline = _Local_Assets(cache_root=asset_env['cache'],
                                       origin_url='http://127.0.0.1:1',   # dead
                                       pins=asset_env['pins'])
        assert assets_offline.get_files() == asset_env['files']

    def test_substituted_bytes_fail_closed(self, asset_env):
        pins = dict(asset_env['pins'])
        pins['swagger-ui.css'] = Swagger_UI__Assets().sri_hash(b'the bytes we expected')
        assets = _Local_Assets(cache_root=asset_env['cache'],
                               origin_url=asset_env['url'], pins=pins)
        with pytest.raises(RuntimeError) as exc:
            assets.get_files()
        assert 'SRI mismatch' in str(exc.value)
        assert '--api-docs=cdn' in str(exc.value)

    def test_corrupted_cache_entry_is_refetched(self, asset_env):
        assets = _Local_Assets(cache_root=asset_env['cache'],
                               origin_url=asset_env['url'], pins=asset_env['pins'])
        assets.get_files()
        cache_file = os.path.join(assets.cache_dir(), 'swagger-ui.css')
        with open(cache_file, 'wb') as f:
            f.write(b'tampered cache bytes')
        result = assets.get_files()                          # refetches, never serves bad bytes
        assert result['swagger-ui.css'] == asset_env['files']['swagger-ui.css']

    def test_offline_first_use_names_the_cdn_alternative(self, asset_env):
        assets = _Local_Assets(cache_root=asset_env['cache'],
                               origin_url='http://127.0.0.1:1', pins=asset_env['pins'])
        with pytest.raises(RuntimeError) as exc:
            assets.get_files()
        assert '--api-docs=cdn' in str(exc.value)
