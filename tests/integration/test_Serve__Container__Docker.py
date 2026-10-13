"""`sgit serve` with real Docker and the real SG/Send image: start from a clone, the clone's
files reachable through the server, a commit made through the server brought back with
`serve pull`, then stop. Skipped when no Docker daemon answers, or when the image can be
neither pulled nor found locally (Docker Hub rate limits anonymous pulls)."""
import os
import shutil
import subprocess
import tempfile

import pytest

from sgit_ai.core.serve.Vault__Serve           import Vault__Serve, IMAGE_DEFAULT
from sgit_ai.core.serve.Vault__Serve__Mirror   import Vault__Serve__Mirror
from sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from sgit_ai.network.api.Vault__API            import Vault__API
from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory
from sgit_ai.core.Vault__Sync                  import Vault__Sync


def _docker_ready() -> bool:
    if not shutil.which('docker'):
        return False
    if subprocess.run(['docker', 'info'], capture_output=True).returncode != 0:
        return False
    if subprocess.run(['docker', 'image', 'inspect', IMAGE_DEFAULT], capture_output=True).returncode == 0:
        return True
    return subprocess.run(['docker', 'pull', IMAGE_DEFAULT], capture_output=True).returncode == 0


pytestmark = pytest.mark.skipif(not _docker_ready(), reason='no Docker daemon, or the SG/Send image is unavailable')


def _write(d, rel, content):
    full = os.path.join(d, rel)
    os.makedirs(os.path.dirname(full) or d, exist_ok=True)
    with open(full, 'w') as f:
        f.write(content)


def test_serve_a_clone_edit_through_the_server_and_bring_it_back():
    tmp   = tempfile.mkdtemp()
    crypto = Vault__Crypto()
    sync  = Vault__Sync(crypto=crypto, api=Vault__API__In_Memory().setup())
    clone = os.path.join(tmp, 'clone')
    vault_key = sync.init(clone)['vault_key']
    _write(clone, 'a.md', 'from the clone')
    sync.commit(clone, 'first')
    serve = Vault__Serve().setup()
    try:
        info = serve.start(clone, port=18480, pull=False)
        assert info['status'] in ('started', 'already_running')
        url    = info['url'].replace('localhost', '127.0.0.1')
        mirror = Vault__Serve__Mirror(crypto=crypto, api=Vault__API(base_url=url, access_token=''))
        assert mirror.push(clone)['moved']

        browser_sync = Vault__Sync(crypto=crypto, api=Vault__API(base_url=url, access_token=''))
        browser      = os.path.join(tmp, 'browser')
        browser_sync.clone(vault_key, browser)                                      # what the UI reads
        assert open(os.path.join(browser, 'a.md')).read() == 'from the clone'
        _write(browser, 'web.md', 'from the server side')
        browser_sync.commit(browser, 'web')
        browser_sync.push(browser)
        _write(browser, 'web2.md', 'second edit')                                   # the server's list endpoint answers [] in
        browser_sync.commit(browser, 'web 2')                                       # disk mode: later pushes must still work
        browser_sync.push(browser)                                                  # (TM-F34 reads the ref itself, not the listing)
        browser_sync.push(browser)                                                  # nothing new: the resync path

        assert mirror.pull(clone)['status'] == 'updated'
        assert open(os.path.join(clone, 'web.md')).read() == 'from the server side'
        assert open(os.path.join(clone, 'web2.md')).read() == 'second edit'
        assert serve.status(clone)['status'] == 'running'
    finally:
        serve.stop(clone)
        shutil.rmtree(tmp, ignore_errors=True)
