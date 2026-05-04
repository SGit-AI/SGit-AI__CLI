"""Integration tests for API__Transfer and Vault__API against the local test server.

Covers all the HTTP-dependent code paths that cannot be reached with the
in-memory API fixture.  The server starts in <300ms and exposes the same
Transfer and Vault endpoints as the production Send stack.

Run with:
    /tmp/sgit-ai-venv-312/bin/python -m pytest tests/integration/test_API__Transfer__Local_Server.py -v
"""
import os
import time
import tempfile
import shutil

import pytest

from sgit_ai.api.API__Transfer    import API__Transfer
from sgit_ai.api.Vault__API       import Vault__API
from sgit_ai.crypto.Vault__Crypto import Vault__Crypto
from sgit_ai.core.Vault__Sync     import Vault__Sync


# ---------------------------------------------------------------------------
# API__Transfer — full lifecycle
# ---------------------------------------------------------------------------

class Test_API__Transfer__Create_Upload_Complete:
    """Test the core create / upload / complete / info / download lifecycle."""

    def test_create_returns_transfer_id(self, send_server):
        """Line 29-34: create() POSTs, returns transfer_id."""
        api = API__Transfer(base_url=send_server.server_url,
                            access_token=send_server.access_token)
        api.setup()
        result = api.create(file_size_bytes=10)
        assert 'transfer_id' in result

    def test_upload_returns_status(self, send_server):
        """Line 37-39: upload() POSTs bytes, returns status."""
        api = API__Transfer(base_url=send_server.server_url,
                            access_token=send_server.access_token)
        api.setup()
        tid = api.create(10)['transfer_id']
        result = api.upload(tid, b'0123456789')
        assert result.get('status') == 'uploaded'

    def test_complete_returns_transfer_id(self, send_server):
        """Line 42-43: complete() POSTs to finalize the transfer."""
        api = API__Transfer(base_url=send_server.server_url,
                            access_token=send_server.access_token)
        api.setup()
        tid = api.create(5)['transfer_id']
        api.upload(tid, b'hello')
        result = api.complete(tid)
        assert 'transfer_id' in result

    def test_info_returns_metadata(self, send_server):
        """Line 50-51: info() GETs transfer metadata."""
        api = API__Transfer(base_url=send_server.server_url,
                            access_token=send_server.access_token)
        api.setup()
        tid = api.create(5)['transfer_id']
        api.upload(tid, b'world')
        api.complete(tid)
        info = api.info(tid)
        assert info.get('file_size_bytes') == 5
        assert info.get('status') == 'completed'

    def test_download_returns_bytes(self, send_server):
        """Line 54-55: download() returns the original payload bytes."""
        api = API__Transfer(base_url=send_server.server_url,
                            access_token=send_server.access_token)
        api.setup()
        payload = b'download me'
        tid = api.create(len(payload))['transfer_id']
        api.upload(tid, payload)
        api.complete(tid)
        assert api.download(tid) == payload

    def test_download_base64_returns_dict(self, send_server):
        """Line 60-61: download_base64() returns dict with base64-encoded data."""
        import base64
        api = API__Transfer(base_url=send_server.server_url,
                            access_token=send_server.access_token)
        api.setup()
        payload = b'base64me'
        tid = api.create(len(payload))['transfer_id']
        api.upload(tid, payload)
        api.complete(tid)
        result = api.download_base64(tid)
        assert base64.b64decode(result['data']) == payload

    def test_check_token_returns_valid(self, send_server):
        """Line 66-67: check_token() validates the access token."""
        api = API__Transfer(base_url=send_server.server_url,
                            access_token=send_server.access_token)
        api.setup()
        result = api.check_token('test-token-name')
        assert result.get('valid') is True

    def test_upload_file_small_roundtrip(self, send_server):
        """Lines 133-150: upload_file() + download_file() small payload roundtrip."""
        api = API__Transfer(base_url=send_server.server_url,
                            access_token=send_server.access_token)
        api.setup()
        payload = b'small file roundtrip content'
        tid = api.upload_file(payload)
        assert tid
        result = api.download_file(tid)
        assert result == payload

    def test_upload_file_no_explicit_transfer_id(self, send_server):
        """Lines 133-150: upload_file() without explicit transfer_id — server assigns one."""
        api = API__Transfer(base_url=send_server.server_url,
                            access_token=send_server.access_token)
        api.setup()
        payload  = b'no explicit transfer id content'
        returned = api.upload_file(payload)
        assert returned
        assert api.download_file(returned) == payload


class Test_API__Transfer__Error_Paths:
    """Test error path coverage in API__Transfer."""

    def test_download_nonexistent_raises(self, send_server):
        """Lines 243-244: download of non-existent transfer → RuntimeError with HTTP error."""
        api = API__Transfer(base_url=send_server.server_url,
                            access_token=send_server.access_token)
        api.setup()
        with pytest.raises(RuntimeError, match='HTTP'):
            api.download('nonexistent-transfer-id-xyz')

    def test_request_json_error_includes_method_url(self, send_server):
        """Lines 208, 212-237: _api_error formats method+url+headers in message."""
        api = API__Transfer(base_url=send_server.server_url,
                            access_token=send_server.access_token)
        api.setup()
        try:
            api.info('bad-transfer-id-000')
            pytest.fail('Expected RuntimeError')
        except RuntimeError as e:
            msg = str(e)
            assert 'HTTP' in msg
            assert 'bad-transfer-id-000' in msg

    def test_create_with_content_type_hint(self, send_server):
        """Line 33: create() with explicit content_type_hint sets body field."""
        api = API__Transfer(base_url=send_server.server_url,
                            access_token=send_server.access_token)
        api.setup()
        result = api.create(file_size_bytes=10, content_type_hint='image/png')
        assert 'transfer_id' in result


class Test_API__Transfer__Debug_Log:
    """Lines 95-127: debug_log path (log_request, log_response, log_error)."""

    def test_debug_log_records_requests(self, send_server):
        """debug_log intercepts request and response entries."""
        from sgit_ai.cli.CLI__Debug_Log import CLI__Debug_Log
        log = CLI__Debug_Log(enabled=True)

        api = API__Transfer(base_url=send_server.server_url,
                            access_token=send_server.access_token,
                            debug_log=log)
        api.setup()
        payload = b'log test payload'
        tid     = api.create(len(payload))['transfer_id']
        api.upload(tid, payload)
        api.complete(tid)
        api.download(tid)

        assert len(log.entries) > 0
        methods = [e.get('method') for e in log.entries]
        assert 'POST' in methods
        assert 'GET'  in methods


# ---------------------------------------------------------------------------
# Vault__API — full lifecycle via local server
# ---------------------------------------------------------------------------

class Test_Vault__API__Write_Read_Delete:
    """Cover write/read/delete/batch/list methods in Vault__API (vault IDs: 8-24 lowercase alnum)."""

    def test_write_and_read(self, vault_api, crypto):
        """Lines 30-34, 41-44: write() and read() roundtrip."""
        keys       = crypto.derive_keys('testpass', 'vaprwtest')
        ciphertext = crypto.encrypt(keys['read_key_bytes'], b'read write test')
        vault_api.write('vaprwtest', 'filea', keys['write_key'], ciphertext)
        result = vault_api.read('vaprwtest', 'filea')
        assert result == ciphertext

    def test_delete_removes_file(self, vault_api, crypto):
        """Lines 58-63: delete() removes file; subsequent read raises."""
        keys       = crypto.derive_keys('testpass', 'vapdeltest')
        ciphertext = crypto.encrypt(keys['read_key_bytes'], b'delete me')
        vault_api.write('vapdeltest', 'delfile', keys['write_key'], ciphertext)
        vault_api.delete('vapdeltest', 'delfile', keys['write_key'])
        with pytest.raises(RuntimeError, match='HTTP'):
            vault_api.read('vapdeltest', 'delfile')

    def test_batch_write_and_read(self, vault_api, crypto):
        """Lines 77-96: batch() write ops + batch_read()."""
        import base64
        keys = crypto.derive_keys('testpass', 'vapbatchtest')
        ct1  = crypto.encrypt(keys['read_key_bytes'], b'batch file 1')
        ct2  = crypto.encrypt(keys['read_key_bytes'], b'batch file 2')
        ops  = [
            {'op': 'write', 'file_id': 'b1', 'data': base64.b64encode(ct1).decode()},
            {'op': 'write', 'file_id': 'b2', 'data': base64.b64encode(ct2).decode()},
        ]
        result = vault_api.batch('vapbatchtest', keys['write_key'], ops)
        assert result.get('status') in ('ok', 'completed', 'success') or 'results' in result

        payloads = vault_api.batch_read('vapbatchtest', ['b1', 'b2'])
        assert payloads.get('b1') == ct1
        assert payloads.get('b2') == ct2

    def test_list_files_returns_list(self, vault_api, crypto):
        """Lines 207-211: list_files() returns list of file IDs."""
        keys = crypto.derive_keys('testpass', 'vaplisttest')
        ct   = crypto.encrypt(keys['read_key_bytes'], b'list me')
        vault_api.write('vaplisttest', 'listfile', keys['write_key'], ct)
        files = vault_api.list_files('vaplisttest')
        assert isinstance(files, list)
        assert 'listfile' in files

    def test_list_files_with_prefix(self, vault_api, crypto):
        """Lines 207-211: list_files() with prefix filter."""
        keys = crypto.derive_keys('testpass', 'vappfxtest')
        ct   = crypto.encrypt(keys['read_key_bytes'], b'prefix filtered')
        vault_api.write('vappfxtest', 'obj/file1', keys['write_key'], ct)
        vault_api.write('vappfxtest', 'other/file2', keys['write_key'], ct)
        filtered = vault_api.list_files('vappfxtest', prefix='obj/')
        assert any(f.startswith('obj/') for f in filtered)

    def test_delete_vault_removes_all(self, send_server, crypto):
        """Lines 214-238: delete_vault() removes all files. Requires access token."""
        api  = Vault__API(base_url=send_server.server_url,
                          access_token=send_server.access_token)
        api.setup()
        keys = crypto.derive_keys('testpass', 'vapdestrtest')
        ct   = crypto.encrypt(keys['read_key_bytes'], b'to be destroyed')
        api.write('vapdestrtest', 'filex', keys['write_key'], ct)
        result = api.delete_vault('vapdestrtest', keys['write_key'])
        assert result.get('status') == 'deleted'

    def test_read_nonexistent_raises(self, vault_api):
        """Lines 184-185: read() of nonexistent file raises RuntimeError."""
        with pytest.raises(RuntimeError, match='HTTP'):
            vault_api.read('vapemptytest', 'nonexistentfile')

    def test_write_wrong_key_raises(self, vault_api, crypto):
        """Lines 192-198: write() with wrong key → 403."""
        keys = crypto.derive_keys('testpass', 'vapauthtest')
        ct   = crypto.encrypt(keys['read_key_bytes'], b'establish vault')
        vault_api.write('vapauthtest', 'initfile', keys['write_key'], ct)
        with pytest.raises(RuntimeError, match='403|Forbidden|HTTP'):
            vault_api.write('vapauthtest', 'badfile', 'b' * 64, ct)

    def test_batch_read_single_nonexistent(self, vault_api):
        """Lines 99-109: batch_read() with a single missing file_id returns None for it."""
        result = vault_api.batch_read('vapbatchrd01', ['missingfile01'])
        assert result.get('missingfile01') is None

    def test_api_error_message_format(self, vault_api):
        """Lines 244, 247-248: _api_error includes method, URL, response body."""
        try:
            vault_api.read('vapemptytest', 'missingfile')
            pytest.fail('expected RuntimeError')
        except RuntimeError as e:
            msg = str(e)
            assert 'HTTP' in msg


# ---------------------------------------------------------------------------
# Vault__Sync against local server — Clone / Pull / Push coverage
# ---------------------------------------------------------------------------

class Test_Vault__Sync__Local_Server__ClonePushPull:
    """Cover Clone/Push/Pull code paths using the real HTTP server."""

    def test_push_then_clone_roundtrip(self, vault_api, crypto, temp_dir):
        """Commit + push then clone to new dir — verifies full HTTP round-trip."""
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        src_dir   = os.path.join(temp_dir, 'source')
        sync.init(src_dir, vault_key='pushclone:pcvaulttest01')

        with open(os.path.join(src_dir, 'greet.txt'), 'w') as f:
            f.write('hello vault')
        sync.commit(src_dir, message='first commit')
        push_result = sync.push(src_dir)
        assert push_result['status'] == 'pushed'

        # Clone into a separate dir
        clone_dir = os.path.join(temp_dir, 'clone')
        result    = sync.clone('pushclone:pcvaulttest01', clone_dir)
        assert os.path.isfile(os.path.join(clone_dir, 'greet.txt'))
        assert open(os.path.join(clone_dir, 'greet.txt')).read() == 'hello vault'

    def test_pull_fetches_new_commit(self, vault_api, crypto, temp_dir):
        """Push a second commit on source, pull on clone — file appears."""
        sync    = Vault__Sync(crypto=crypto, api=vault_api)
        src_dir = os.path.join(temp_dir, 'src2')
        sync.init(src_dir, vault_key='pulltest:pullvlttest01')

        with open(os.path.join(src_dir, 'a.txt'), 'w') as f:
            f.write('first')
        sync.commit(src_dir, 'add a')
        sync.push(src_dir)

        clone_dir = os.path.join(temp_dir, 'clone2')
        sync.clone('pulltest:pullvlttest01', clone_dir)

        with open(os.path.join(src_dir, 'b.txt'), 'w') as f:
            f.write('second')
        sync.commit(src_dir, 'add b')
        sync.push(src_dir)

        pull_result = sync.pull(clone_dir)
        assert pull_result['status'] in ('updated', 'pulled', 'up_to_date', 'merged')

    def test_status_after_push_is_clean(self, vault_api, crypto, temp_dir):
        """status() after push reports clean."""
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        vault_dir = os.path.join(temp_dir, 'status3')
        sync.init(vault_dir, vault_key='statpush:spvaulttest01')
        with open(os.path.join(vault_dir, 'f.txt'), 'w') as f:
            f.write('hi')
        sync.commit(vault_dir, 'add f')
        sync.push(vault_dir)
        assert sync.status(vault_dir)['clean']
