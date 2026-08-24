"""Swagger_UI__Assets — fetch-verify-cache for `--api-docs=bundled` (08 §3).

sgit ships NO Swagger UI bytes in its wheel. Bundled mode fetches the pinned
files once, verifies them against the SAME SRI hashes the CDN mode pins (so
the vendored copy's integrity comes from the pin, not from whatever was on
disk), and caches them under ~/.sgit/assets/swagger-ui/<version>/.

Fetch order: static.sgit.ai first, jsdelivr as fallback — a first-party
mirror is safe HERE, at publish time, because the hash decides and a
substituted byte fails closed. It is NOT safe as a read-time origin (09).

The SRI pins are MEASURED values (recorded 2026-08-18 from
swagger-ui-dist@5.17.14). On any version bump they must be recomputed from
the package bytes — `openssl dgst -sha384 -binary <file> | openssl base64 -A`
— never copied from a web page.
"""
import base64
import hashlib
import os
from   urllib.request                            import urlopen
from   osbot_utils.type_safe.Type_Safe           import Type_Safe
from   sgit_ai.safe_types.Safe_Str__Vault_Path   import Safe_Str__Vault_Path

SWAGGER_UI_VERSION = '5.17.14'

SWAGGER_UI_FILES = {
    'swagger-ui.css'       : 'sha384-wxLW6kwyHktdDGr6Pv1zgm/VGJh99lfUbzSn6HNHBENZlCN7W602k9VkGdxuFvPn',
    'swagger-ui-bundle.js' : 'sha384-wmyclcVGX/WhUkdkATwhaK1X1JtiNrr2EoYJ+diV3vj4v6OC5yCeSu+yW13SYJep',
}
# The standalone preset (230 KB) is deliberately NOT here: it only powers the
# topbar/URL explorer, which a fixed-spec page does not use.

ASSET_ORIGINS = (
    'https://static.sgit.ai/swagger-ui/{version}/{name}',
    'https://cdn.jsdelivr.net/npm/swagger-ui-dist@{version}/{name}',
)


class Swagger_UI__Assets(Type_Safe):
    cache_root : Safe_Str__Vault_Path = None    # tests point this at a tmp dir; default ~/.sgit

    def expected_files(self) -> dict:
        """{name: sri_hash} — the pinned set. A method (not inlined) so the
        fetch-verify-cache machinery is testable against local fixtures."""
        return SWAGGER_UI_FILES

    def origins(self) -> tuple:
        return ASSET_ORIGINS

    def cache_dir(self) -> str:
        root = str(self.cache_root) if self.cache_root else os.path.join(os.path.expanduser('~'), '.sgit')
        return os.path.join(root, 'assets', 'swagger-ui', SWAGGER_UI_VERSION)

    def sri_hash(self, data: bytes) -> str:
        return 'sha384-' + base64.b64encode(hashlib.sha384(data).digest()).decode('ascii')

    def get_files(self) -> dict:
        """{name: bytes} for the pinned files — from the cache when present
        and hash-valid, else fetched, verified, and cached. Fails closed on
        any hash mismatch; first use offline fails naming --api-docs=cdn."""
        results = {}
        for name, expected_sri in self.expected_files().items():
            cached = self._read_cache(name, expected_sri)
            if cached is not None:
                results[name] = cached
                continue
            data = self._fetch_verified(name, expected_sri)
            self._write_cache(name, data)
            results[name] = data
        return results

    def _read_cache(self, name: str, expected_sri: str) -> bytes:
        path = os.path.join(self.cache_dir(), name)
        if not os.path.isfile(path):
            return None
        with open(path, 'rb') as f:
            data = f.read()
        if self.sri_hash(data) != expected_sri:
            os.remove(path)                              # corrupted cache: fail closed, refetch
            return None
        return data

    def _write_cache(self, name: str, data: bytes) -> None:
        os.makedirs(self.cache_dir(), exist_ok=True)
        with open(os.path.join(self.cache_dir(), name), 'wb') as f:
            f.write(data)

    def _fetch_verified(self, name: str, expected_sri: str) -> bytes:
        errors = []
        for origin in self.origins():
            url = origin.format(version=SWAGGER_UI_VERSION, name=name)
            try:
                with urlopen(url, timeout=60) as response:
                    data = response.read()
            except Exception as error:
                errors.append(f'{url}: {error}')
                continue
            actual = self.sri_hash(data)
            if actual != expected_sri:
                errors.append(f'{url}: SRI mismatch — expected {expected_sri}, got {actual}')
                continue                                 # a substituted byte fails closed
            return data
        raise RuntimeError(
            f'could not fetch a verified {name} for --api-docs=bundled:\n  '
            + '\n  '.join(errors)
            + '\nIf you are offline, use --api-docs=cdn (the docs page then loads the '
              'UI from the CDN at view time instead).')
