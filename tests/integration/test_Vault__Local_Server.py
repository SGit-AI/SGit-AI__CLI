"""Integration tests that run against a real SG/Send vault server (in-memory mode).

Uses the sgraph-ai-app-send test server — a real HTTP server running the
full User Lambda stack with in-memory storage. No mocks, no external deps.
"""
import json
import os
import tempfile
import shutil

import pytest

from sg_send_cli.api.Vault__API       import Vault__API
from sg_send_cli.crypto.Vault__Crypto import Vault__Crypto
from sg_send_cli.sync.Vault__Sync     import Vault__Sync


TEST_PASSPHRASE = 'local-test-passphrase'


class Test_Vault__Local_Server__API:
    """Low-level API tests against the local vault server."""

    def test_write_and_read(self, vault_api, crypto):
        keys      = crypto.derive_keys(TEST_PASSPHRASE, 'api-rw-vault')
        read_key  = keys['read_key_bytes']
        write_key = keys['write_key']

        plaintext  = b'hello from local test'
        ciphertext = crypto.encrypt(read_key, plaintext)

        result = vault_api.write('api-rw-vault', 'test-file-01', write_key, ciphertext)
        assert result['status'] == 'completed'

        downloaded  = vault_api.read('api-rw-vault', 'test-file-01')
        decrypted   = crypto.decrypt(read_key, downloaded)
        assert decrypted == plaintext

    def test_write_and_delete(self, vault_api, crypto):
        keys      = crypto.derive_keys(TEST_PASSPHRASE, 'api-del-vault')
        write_key = keys['write_key']
        read_key  = keys['read_key_bytes']
        ciphertext = crypto.encrypt(read_key, b'delete me')

        vault_api.write('api-del-vault', 'del-file-01', write_key, ciphertext)
        result = vault_api.delete('api-del-vault', 'del-file-01', write_key)
        assert result['status'] == 'deleted'

        with pytest.raises(RuntimeError, match='404'):
            vault_api.read('api-del-vault', 'del-file-01')

    def test_wrong_write_key_rejected(self, vault_api, crypto):
        keys      = crypto.derive_keys(TEST_PASSPHRASE, 'api-auth-vault')
        read_key  = keys['read_key_bytes']
        write_key = keys['write_key']
        ciphertext = crypto.encrypt(read_key, b'establish vault')

        vault_api.write('api-auth-vault', 'auth-file-01', write_key, ciphertext)

        wrong_key = 'b' * 64
        with pytest.raises(RuntimeError, match='403'):
            vault_api.write('api-auth-vault', 'auth-file-02', wrong_key, ciphertext)


class Test_Vault__Local_Server__Sync:
    """Full init/commit/push/pull cycle against the local vault server."""

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

        sync.commit(vault_dir, message='add hello')

        push_result = sync.push(vault_dir)
        assert push_result['status'] == 'pushed'

        status = sync.status(vault_dir)
        assert status['clean']

    def test_init_then_push_verifies_upload(self, vault_api, crypto, temp_dir):
        """Init, add files, commit, push, then verify objects reached the server."""
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        vault_key = 'verify-pass:verify-vid'
        vault_dir = os.path.join(temp_dir, 'verify-vault')
        result    = sync.init(vault_dir, vault_key=vault_key)

        with open(os.path.join(vault_dir, 'data.txt'), 'w') as f:
            f.write('verify upload data')

        sync.commit(vault_dir, message='add data')
        push_result = sync.push(vault_dir)
        assert push_result['objects_uploaded'] > 0

    def test_status_after_init_is_clean(self, vault_api, crypto, temp_dir):
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        vault_dir = os.path.join(temp_dir, 'status-vault')
        sync.init(vault_dir, vault_key='statpass:statvault')

        status = sync.status(vault_dir)
        assert status['clean']

    def test_status_detects_added_file(self, vault_api, crypto, temp_dir):
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        vault_dir = os.path.join(temp_dir, 'status-add-vault')
        sync.init(vault_dir, vault_key='statadd:stataddvid')

        with open(os.path.join(vault_dir, 'new-file.txt'), 'w') as f:
            f.write('new content')

        status = sync.status(vault_dir)
        assert 'new-file.txt' in status['added']
        assert not status['clean']

    def test_commit_then_status_clean(self, vault_api, crypto, temp_dir):
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        vault_dir = os.path.join(temp_dir, 'commit-vault')
        sync.init(vault_dir, vault_key='commitp:commitv')

        with open(os.path.join(vault_dir, 'file.txt'), 'w') as f:
            f.write('content')

        sync.commit(vault_dir, message='add file')
        status = sync.status(vault_dir)
        assert status['clean']

    def test_push_nothing_to_push(self, vault_api, crypto, temp_dir):
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        vault_dir = os.path.join(temp_dir, 'noop-vault')
        sync.init(vault_dir, vault_key='nooppas:noopvid')

        result = sync.push(vault_dir)
        assert result['status'] == 'up_to_date'

    def test_pull_up_to_date(self, vault_api, crypto, temp_dir):
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        vault_dir = os.path.join(temp_dir, 'pull-vault')
        sync.init(vault_dir, vault_key='pullpas:pullvid')

        result = sync.pull(vault_dir)
        assert result['status'] == 'up_to_date'

    def test_branches_lists_both(self, vault_api, crypto, temp_dir):
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        vault_dir = os.path.join(temp_dir, 'branch-vault')
        sync.init(vault_dir, vault_key='branchp:branchv')

        result = sync.branches(vault_dir)
        names  = [b['name'] for b in result['branches']]
        assert 'current' in names
        assert 'local'   in names

    def test_multiple_commits_and_push(self, vault_api, crypto, temp_dir):
        """Multiple commits then push — verifies delta upload."""
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        vault_dir = os.path.join(temp_dir, 'multi-vault')
        sync.init(vault_dir, vault_key='multip:multiv')

        with open(os.path.join(vault_dir, 'file1.txt'), 'w') as f:
            f.write('first file')
        sync.commit(vault_dir, message='add file1')

        with open(os.path.join(vault_dir, 'file2.txt'), 'w') as f:
            f.write('second file')
        sync.commit(vault_dir, message='add file2')

        push_result = sync.push(vault_dir)
        assert push_result['status']           == 'pushed'
        assert push_result['objects_uploaded']  >= 2
        assert push_result['commits_pushed']   >= 2

    def test_push_second_push_only_uploads_delta(self, vault_api, crypto, temp_dir):
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        vault_dir = os.path.join(temp_dir, 'delta-vault')
        sync.init(vault_dir, vault_key='deltap:deltav')

        with open(os.path.join(vault_dir, 'a.txt'), 'w') as f:
            f.write('alpha')
        sync.commit(vault_dir, message='first')
        sync.push(vault_dir)

        with open(os.path.join(vault_dir, 'b.txt'), 'w') as f:
            f.write('bravo')
        sync.commit(vault_dir, message='second')
        push2 = sync.push(vault_dir)

        assert push2['status']          == 'pushed'
        assert push2['objects_uploaded'] == 1
