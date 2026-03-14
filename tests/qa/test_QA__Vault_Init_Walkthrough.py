"""QA walkthrough: init a new vault from scratch using sg-send-cli.

Prerequisites:
    1. Start the local vault server in a separate terminal:
           .venv-312/bin/python scripts/local_vault_server.py
       (defaults to port 18321)

    2. Run individual tests one at a time, in order:
           pytest tests/qa/test_QA__Vault_Init_Walkthrough.py::Test_QA__Vault_Init_Walkthrough::test__1__init_vault -s
           pytest tests/qa/test_QA__Vault_Init_Walkthrough.py::Test_QA__Vault_Init_Walkthrough::test__2__inspect_empty_vault -s
           ...

    The -s flag shows all print output so you can see what's happening.

Notes:
    - This walkthrough creates a vault from scratch (no browser seeding needed).
    - Tests are numbered and should be run in order.
    - Uses /tmp/sg_vault_qa_init/ as the working directory.
"""
import json
import os
import shutil
import socket

import pytest
from osbot_utils.utils.Files import path_combine

from sg_send_cli.api.Vault__API           import Vault__API
from sg_send_cli.crypto.Vault__Crypto     import Vault__Crypto
from sg_send_cli.sync.Vault__Sync         import Vault__Sync
from sg_send_cli.objects.Vault__Inspector import Vault__Inspector
from tests.qa.helpers                     import print_section, print_tree

SERVER_PORT = 18321
SERVER_URL  = f'http://127.0.0.1:{SERVER_PORT}'
#QA_DIR      = '/tmp/sg_vault_qa_init'
QA_DIR      = path_combine(__file__, '../_vaults')
VAULT_DIR   = os.path.join(QA_DIR, 'my-new-vault')
CLONE_DIR   = os.path.join(QA_DIR, 'cloned-vault')
VAULT_KEY   = 'qa-init-passphrase:qa-init-01'


def _server_is_running():
    try:
        with socket.create_connection(('127.0.0.1', SERVER_PORT), timeout=1):
            return True
    except OSError:
        return False


SKIP_REASON = (
    f'Local vault server not running on port {SERVER_PORT}. '
    f'Start it with: .venv-312/bin/python scripts/local_vault_server.py'
)


@pytest.mark.skipif(not _server_is_running(), reason=SKIP_REASON)
class Test_QA__Vault_Init_Walkthrough:

    def setup_method(self):
        self.crypto    = Vault__Crypto()
        self.api       = Vault__API(base_url=SERVER_URL, access_token='qa-token')
        self.api.setup()
        self.sync      = Vault__Sync(crypto=self.crypto, api=self.api)
        self.inspector = Vault__Inspector(crypto=self.crypto)
        self.keys      = self.crypto.derive_keys_from_vault_key(VAULT_KEY)

    # -------------------------------------------------------------------------
    # Step 1: Init a new empty vault (no browser seeding needed!)
    # -------------------------------------------------------------------------

    def test__1__init_vault(self):
        print_section('Step 1: Init a new vault from the CLI')

        if os.path.exists(QA_DIR):
            shutil.rmtree(QA_DIR)
        os.makedirs(QA_DIR, exist_ok=True)

        result = self.sync.init(VAULT_DIR, vault_key=VAULT_KEY)

        print(f'  Directory:  {result["directory"]}')
        print(f'  Vault ID:   {result["vault_id"]}')
        print(f'  Vault key:  {result["vault_key"]}')
        print(f'\n  File tree:')
        print_tree(VAULT_DIR)

    # -------------------------------------------------------------------------
    # Step 2: Inspect the empty vault
    # -------------------------------------------------------------------------

    def test__2__inspect_empty_vault(self):
        print_section('Step 2: Inspect the empty vault')

        summary = self.inspector.format_vault_summary(VAULT_DIR)
        print(f'\n{summary}')

        read_key = self.keys['read_key_bytes']
        chain = self.inspector.inspect_commit_chain(VAULT_DIR, read_key=read_key)
        print(f'\n  Commit chain (should have 1 "init" commit):')
        print(self.inspector.format_commit_log(chain))

    # -------------------------------------------------------------------------
    # Step 3: Status should be clean
    # -------------------------------------------------------------------------

    def test__3__status_after_init(self):
        print_section('Step 3: Status after init (should be clean)')

        status = self.sync.status(VAULT_DIR)
        print(f'  Status: {json.dumps(status, indent=2)}')
        assert status['clean'], 'Expected clean status after init'

    # -------------------------------------------------------------------------
    # Step 4: Add files and check status
    # -------------------------------------------------------------------------

    def test__4__add_files(self):
        print_section('Step 4: Add files to the vault')

        os.makedirs(os.path.join(VAULT_DIR, 'docs'), exist_ok=True)

        with open(os.path.join(VAULT_DIR, 'README.md'), 'w') as f:
            f.write('# My New Vault\nCreated from sg-send-cli init!\n')

        with open(os.path.join(VAULT_DIR, 'docs', 'notes.txt'), 'w') as f:
            f.write('- First note from CLI-created vault\n- Second note\n')

        print(f'  Created: README.md')
        print(f'  Created: docs/notes.txt')

        status = self.sync.status(VAULT_DIR)
        print(f'\n  Status: {json.dumps(status, indent=2)}')
        assert 'README.md' in status['added']
        assert 'docs/notes.txt' in status['added']

        result = self.sync.commit(VAULT_DIR, message='add initial files')
        print(f'\n  Commit result: {json.dumps(result, indent=2)}')
        assert result['commit_id'].startswith('obj-')

    # -------------------------------------------------------------------------
    # Step 5: Push files to server
    # -------------------------------------------------------------------------

    def test__5__push_files(self):
        print_section('Step 5: Push files to server')

        result = self.sync.push(VAULT_DIR)
        print(f'  Push result: {json.dumps(result, indent=2)}')

        status = self.sync.status(VAULT_DIR)
        print(f'\n  Status after push: {json.dumps(status, indent=2)}')
        assert status['clean']

        read_key = self.keys['read_key_bytes']
        chain = self.inspector.inspect_commit_chain(VAULT_DIR, read_key=read_key)
        print(f'\n  Commit chain (should have 2 commits):')
        print(self.inspector.format_commit_log(chain))

    # -------------------------------------------------------------------------
    # Step 6: Clone the vault into a second directory
    # -------------------------------------------------------------------------

    @pytest.mark.skip(reason='clone() not yet implemented')
    def test__6__clone_vault(self):
        print_section('Step 6: Clone the init-created vault')

        if os.path.exists(CLONE_DIR):
            shutil.rmtree(CLONE_DIR)

        self.sync.clone(VAULT_KEY, CLONE_DIR)

        print(f'  Cloned to: {CLONE_DIR}')
        print(f'\n  File tree:')
        print_tree(CLONE_DIR)

        readme = os.path.join(CLONE_DIR, 'README.md')
        assert os.path.isfile(readme)
        with open(readme) as f:
            content = f.read()
        print(f'\n  README.md content:')
        print(f'    {content}')
        assert 'sg-send-cli init' in content

    # -------------------------------------------------------------------------
    # Step 7: Push from clone, pull into original
    # -------------------------------------------------------------------------

    @pytest.mark.skip(reason='clone() not yet implemented — depends on test 6')
    def test__7__push_from_clone_pull_into_original(self):
        print_section('Step 7: Modify clone, push, then pull into original')

        with open(os.path.join(CLONE_DIR, 'from-clone.txt'), 'w') as f:
            f.write('This file was added from the cloned copy.\n')

        result = self.sync.push(CLONE_DIR)
        print(f'  Push from clone: {json.dumps(result, indent=2)}')

        pull_result = self.sync.pull(VAULT_DIR)
        print(f'\n  Pull into original: {json.dumps(pull_result, indent=2)}')
        assert 'from-clone.txt' in pull_result['added']

        with open(os.path.join(VAULT_DIR, 'from-clone.txt')) as f:
            content = f.read()
        print(f'\n  from-clone.txt content: {content.strip()}')

    # -------------------------------------------------------------------------
    # Step 8: Final inspection
    # -------------------------------------------------------------------------

    def test__8__final_inspection(self):
        print_section('Step 8: Final vault state')

        print(f'\n  Vault directory ({VAULT_DIR}):')
        print_tree(VAULT_DIR)

        read_key = self.keys['read_key_bytes']
        chain = self.inspector.inspect_commit_chain(VAULT_DIR, read_key=read_key)
        print(f'\n  Full commit history:')
        print(self.inspector.format_commit_log(chain))

        stats = self.inspector.object_store_stats(VAULT_DIR)
        print(f'\n  Object store stats:')
        print(f'    Total objects: {stats["total_objects"]}')
        print(f'    Total bytes:   {stats["total_bytes"]}')

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    # def test__9__cleanup(self):
    #     print_section('Step 9: Cleanup')
    #
    #     if os.path.exists(QA_DIR):
    #         shutil.rmtree(QA_DIR)
    #         print(f'  Removed: {QA_DIR}')
    #     else:
    #         print(f'  Nothing to clean up')
