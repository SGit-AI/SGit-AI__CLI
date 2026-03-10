"""Integration tests that run against a real SG/Send vault server (in-memory mode).

Requires: .venv-312 with sgraph-ai-app-send installed.
The server is launched as a subprocess using Python 3.12,
while the tests themselves run under the project's Python 3.11.
"""
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import shutil
import time

import pytest

from sg_send_cli.api.Vault__API       import Vault__API
from sg_send_cli.crypto.Vault__Crypto import Vault__Crypto
from sg_send_cli.sync.Vault__Sync     import Vault__Sync

PROJECT_ROOT  = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
VENV_PYTHON   = os.path.join(PROJECT_ROOT, '.venv-312', 'bin', 'python')
SERVER_SCRIPT = os.path.join(PROJECT_ROOT, 'scripts', 'local_vault_server.py')
SKIP          = not os.path.isfile(VENV_PYTHON)
SKIP_REASON   = '.venv-312 not found — run: python3.12 -m venv .venv-312 && .venv-312/bin/pip install sgraph-ai-app-send'


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _wait_for_server(port, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


@pytest.fixture(scope='module')
def vault_server():
    if SKIP:
        pytest.skip(SKIP_REASON)
    port = _find_free_port()
    proc = subprocess.Popen([VENV_PYTHON, SERVER_SCRIPT, str(port)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        if not _wait_for_server(port):
            proc.kill()
            stdout = proc.stdout.read().decode(errors='replace')
            stderr = proc.stderr.read().decode(errors='replace')
            pytest.fail(f'Vault server did not start on port {port}\nstdout: {stdout}\nstderr: {stderr}')
        yield f'http://127.0.0.1:{port}'
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)


@pytest.fixture()
def vault_api(vault_server):
    api = Vault__API(base_url=vault_server, access_token='test-token')
    api.setup()
    return api


@pytest.fixture()
def crypto():
    return Vault__Crypto()


@pytest.fixture()
def temp_dir():
    d = tempfile.mkdtemp(prefix='sg_vault_local_')
    yield d
    shutil.rmtree(d, ignore_errors=True)


TEST_PASSPHRASE = 'local-test-passphrase'
TEST_VAULT_ID   = 'local-test-vault'
TEST_VAULT_KEY  = f'{TEST_PASSPHRASE}:{TEST_VAULT_ID}'


@pytest.mark.skipif(SKIP, reason=SKIP_REASON)
class Test_Vault__Local_Server__API:
    """Low-level API tests against the local vault server."""

    def test_write_and_read(self, vault_api, crypto):
        keys      = crypto.derive_keys(TEST_PASSPHRASE, TEST_VAULT_ID)
        read_key  = keys['read_key_bytes']
        write_key = keys['write_key']

        plaintext  = b'hello from local test'
        ciphertext = crypto.encrypt(read_key, plaintext)

        result = vault_api.write(TEST_VAULT_ID, 'test-file-01', write_key, ciphertext)
        assert result['status'] == 'completed'

        downloaded  = vault_api.read(TEST_VAULT_ID, 'test-file-01')
        decrypted   = crypto.decrypt(read_key, downloaded)
        assert decrypted == plaintext

    def test_write_and_delete(self, vault_api, crypto):
        keys      = crypto.derive_keys(TEST_PASSPHRASE, TEST_VAULT_ID)
        write_key = keys['write_key']
        read_key  = keys['read_key_bytes']
        ciphertext = crypto.encrypt(read_key, b'delete me')

        vault_api.write(TEST_VAULT_ID, 'del-file-01', write_key, ciphertext)
        result = vault_api.delete(TEST_VAULT_ID, 'del-file-01', write_key)
        assert result['status'] == 'deleted'

        with pytest.raises(RuntimeError, match='404'):
            vault_api.read(TEST_VAULT_ID, 'del-file-01')

    def test_wrong_write_key_rejected(self, vault_api, crypto):
        keys      = crypto.derive_keys(TEST_PASSPHRASE, TEST_VAULT_ID)
        read_key  = keys['read_key_bytes']
        write_key = keys['write_key']
        ciphertext = crypto.encrypt(read_key, b'establish vault')

        vault_api.write(TEST_VAULT_ID, 'auth-file-01', write_key, ciphertext)

        wrong_key = 'b' * 64
        with pytest.raises(RuntimeError, match='403'):
            vault_api.write(TEST_VAULT_ID, 'auth-file-02', wrong_key, ciphertext)


@pytest.mark.skipif(SKIP, reason=SKIP_REASON)
class Test_Vault__Local_Server__Sync:
    """Full clone/push/pull cycle against the local vault server."""

    def _seed_vault(self, vault_api, crypto, keys):
        """Seed the server with settings + tree + one file, simulating browser upload."""
        vault_id  = keys['vault_id']
        read_key  = keys['read_key_bytes']
        write_key = keys['write_key']

        file_content   = b'# README\nThis is a test vault file.'
        encrypted_file = crypto.encrypt(read_key, file_content)
        content_file_id = 'cf' + os.urandom(5).hex()

        settings = {'vault_id': vault_id, 'vault_name': 'Test Vault'}
        tree     = {'version': 1,
                    'tree': {'/': {'type': 'folder',
                                   'children': {'README.md': {'type'   : 'file',
                                                               'file_id': content_file_id,
                                                               'size'   : len(file_content)}}}}}

        encrypted_settings = crypto.encrypt(read_key, json.dumps(settings).encode())
        encrypted_tree     = crypto.encrypt(read_key, json.dumps(tree).encode())

        vault_api.write(vault_id, content_file_id,          write_key, encrypted_file)
        vault_api.write(vault_id, keys['settings_file_id'], write_key, encrypted_settings)
        vault_api.write(vault_id, keys['tree_file_id'],     write_key, encrypted_tree)

        return dict(file_content=file_content, content_file_id=content_file_id)

    def test_clone__downloads_files(self, vault_api, crypto, temp_dir):
        keys   = crypto.derive_keys(TEST_PASSPHRASE, 'clone-test-vault')
        seeded = self._seed_vault(vault_api, crypto, keys)

        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        clone_dir = os.path.join(temp_dir, 'vault')
        sync.clone(f'{TEST_PASSPHRASE}:clone-test-vault', clone_dir)

        readme_path = os.path.join(clone_dir, 'README.md')
        assert os.path.isfile(readme_path)
        with open(readme_path, 'rb') as f:
            assert f.read() == seeded['file_content']

        assert os.path.isfile(os.path.join(clone_dir, '.sg_vault', 'VAULT-KEY'))
        assert os.path.isfile(os.path.join(clone_dir, '.sg_vault', 'tree.json'))
        assert os.path.isfile(os.path.join(clone_dir, '.sg_vault', 'settings.json'))

    def test_clone__decrypts_settings_correctly(self, vault_api, crypto, temp_dir):
        keys   = crypto.derive_keys(TEST_PASSPHRASE, 'settings-test-vault')
        self._seed_vault(vault_api, crypto, keys)

        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        clone_dir = os.path.join(temp_dir, 'vault')
        sync.clone(f'{TEST_PASSPHRASE}:settings-test-vault', clone_dir)

        with open(os.path.join(clone_dir, '.sg_vault', 'settings.json')) as f:
            settings = json.load(f)
        assert settings['vault_name'] == 'Test Vault'

    def test_clone__multiple_files(self, vault_api, crypto, temp_dir):
        """Seed a vault with multiple files and verify clone gets them all."""
        keys      = crypto.derive_keys(TEST_PASSPHRASE, 'multi-file-vault')
        vault_id  = keys['vault_id']
        read_key  = keys['read_key_bytes']
        write_key = keys['write_key']

        files = {'doc.txt'       : b'Document content',
                 'data/notes.md' : b'# Notes\nSome notes here.'}
        children = {}
        for path, content in files.items():
            file_id   = 'mf' + os.urandom(5).hex()
            encrypted = crypto.encrypt(read_key, content)
            vault_api.write(vault_id, file_id, write_key, encrypted)

            parts   = path.split('/')
            current = children
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {'type': 'folder', 'children': {}}
                current = current[part]['children']
            current[parts[-1]] = {'type': 'file', 'file_id': file_id, 'size': len(content)}

        tree     = {'version': 1, 'tree': {'/': {'type': 'folder', 'children': children}}}
        settings = {'vault_id': vault_id, 'vault_name': 'Multi File Vault'}

        vault_api.write(vault_id, keys['tree_file_id'],     write_key,
                        crypto.encrypt(read_key, json.dumps(tree).encode()))
        vault_api.write(vault_id, keys['settings_file_id'], write_key,
                        crypto.encrypt(read_key, json.dumps(settings).encode()))

        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        clone_dir = os.path.join(temp_dir, 'vault')
        sync.clone(f'{TEST_PASSPHRASE}:multi-file-vault', clone_dir)

        for path, content in files.items():
            full_path = os.path.join(clone_dir, path)
            assert os.path.isfile(full_path), f'Missing: {path}'
            with open(full_path, 'rb') as f:
                assert f.read() == content

    def test_clone_then_push__uploads_new_file(self, vault_api, crypto, temp_dir):
        keys   = crypto.derive_keys(TEST_PASSPHRASE, 'push-test-vault')
        self._seed_vault(vault_api, crypto, keys)

        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        clone_dir = os.path.join(temp_dir, 'vault')
        sync.clone(f'{TEST_PASSPHRASE}:push-test-vault', clone_dir)

        new_file = os.path.join(clone_dir, 'notes.txt')
        with open(new_file, 'w') as f:
            f.write('New file added locally')

        result = sync.push(clone_dir)
        assert 'notes.txt' in result['added']

    def test_clone_push_then_pull__round_trips(self, vault_api, crypto, temp_dir):
        keys   = crypto.derive_keys(TEST_PASSPHRASE, 'roundtrip-vault')
        self._seed_vault(vault_api, crypto, keys)

        sync       = Vault__Sync(crypto=crypto, api=vault_api)
        vault_key  = f'{TEST_PASSPHRASE}:roundtrip-vault'
        clone_dir  = os.path.join(temp_dir, 'vault')
        sync.clone(vault_key, clone_dir)

        with open(os.path.join(clone_dir, 'data.txt'), 'w') as f:
            f.write('round trip data')
        sync.push(clone_dir)

        clone_dir2 = os.path.join(temp_dir, 'vault2')
        sync.clone(vault_key, clone_dir2)

        data_path = os.path.join(clone_dir2, 'data.txt')
        assert os.path.isfile(data_path)
        with open(data_path) as f:
            assert f.read() == 'round trip data'

    def test_status_after_clone__is_clean(self, vault_api, crypto, temp_dir):
        keys = crypto.derive_keys(TEST_PASSPHRASE, 'status-test-vault')
        self._seed_vault(vault_api, crypto, keys)

        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        clone_dir = os.path.join(temp_dir, 'vault')
        sync.clone(f'{TEST_PASSPHRASE}:status-test-vault', clone_dir)

        status = sync.status(clone_dir)
        assert status['clean']


@pytest.mark.skipif(SKIP, reason=SKIP_REASON)
class Test_Vault__Local_Server__Init:
    """Test init command against the local vault server."""

    def test_init_creates_empty_vault(self, vault_api, crypto, temp_dir):
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        vault_dir = os.path.join(temp_dir, 'new-vault')
        result    = sync.init(vault_dir, vault_key='init-pass:init-vid')

        assert os.path.isdir(os.path.join(vault_dir, '.sg_vault'))
        assert result['vault_id'] == 'init-vid'

        status = sync.status(vault_dir)
        assert status['clean']

    def test_init_with_random_key(self, vault_api, crypto, temp_dir):
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        vault_dir = os.path.join(temp_dir, 'random-vault')
        result    = sync.init(vault_dir)

        assert ':' in result['vault_key']
        assert len(result['vault_key']) > 10

    def test_init_then_add_file_and_push(self, vault_api, crypto, temp_dir):
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        vault_dir = os.path.join(temp_dir, 'push-vault')
        result    = sync.init(vault_dir, vault_key='initpush:pushvid')

        with open(os.path.join(vault_dir, 'hello.txt'), 'w') as f:
            f.write('hello from init')

        push_result = sync.push(vault_dir)
        assert 'hello.txt' in push_result['added']

        status = sync.status(vault_dir)
        assert status['clean']

    def test_init_then_push_then_clone(self, vault_api, crypto, temp_dir):
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        vault_dir = os.path.join(temp_dir, 'roundtrip')
        vault_key = 'initrt:rtvault'
        sync.init(vault_dir, vault_key=vault_key)

        with open(os.path.join(vault_dir, 'data.txt'), 'w') as f:
            f.write('init round trip')
        sync.push(vault_dir)

        clone_dir = os.path.join(temp_dir, 'cloned')
        sync.clone(vault_key, clone_dir)

        data_path = os.path.join(clone_dir, 'data.txt')
        assert os.path.isfile(data_path)
        with open(data_path) as f:
            assert f.read() == 'init round trip'

    def test_init_then_push_then_pull_from_second_clone(self, vault_api, crypto, temp_dir):
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        vault_key = 'initpull:pullvid'

        dir1 = os.path.join(temp_dir, 'vault1')
        sync.init(dir1, vault_key=vault_key)

        with open(os.path.join(dir1, 'file1.txt'), 'w') as f:
            f.write('from vault1')
        sync.push(dir1)

        dir2 = os.path.join(temp_dir, 'vault2')
        sync.clone(vault_key, dir2)

        with open(os.path.join(dir2, 'file2.txt'), 'w') as f:
            f.write('from vault2')
        sync.push(dir2)

        pull_result = sync.pull(dir1)
        assert 'file2.txt' in pull_result['added']
        with open(os.path.join(dir1, 'file2.txt')) as f:
            assert f.read() == 'from vault2'
