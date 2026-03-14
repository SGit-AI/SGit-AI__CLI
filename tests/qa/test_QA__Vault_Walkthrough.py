"""QA walkthrough: manual step-by-step vault operations against a local server.

Prerequisites:
    1. Start the local vault server in a separate terminal:
           .venv-312/bin/python scripts/local_vault_server.py
       (defaults to port 18321)

    2. Run individual tests one at a time, in order:
           pytest tests/qa/test_QA__Vault_Walkthrough.py::Test_QA__Vault_Walkthrough::test__1__seed_vault -s
           pytest tests/qa/test_QA__Vault_Walkthrough.py::Test_QA__Vault_Walkthrough::test__2__clone_vault -s
           ...

    The -s flag shows all print output so you can see what's happening.

Notes:
    - Tests are numbered (test__1__, test__2__, ...) and should be run in order.
    - Each test prints what it's doing and what to inspect.
    - All tests use a tempdir as the working directory.
    - The entire qa/ folder is excluded from normal pytest runs via conftest.py.
    - Tests 2-11 are skipped because clone() is not yet implemented.
"""
import json
import os
import shutil
import socket
import tempfile

import pytest

from sg_send_cli.api.Vault__API             import Vault__API
from sg_send_cli.crypto.Vault__Crypto       import Vault__Crypto
from sg_send_cli.sync.Vault__Sync           import Vault__Sync
from sg_send_cli.objects.Vault__Inspector   import Vault__Inspector
from tests.qa.helpers                       import print_section, print_tree

SERVER_PORT = 18321
SERVER_URL  = f'http://127.0.0.1:{SERVER_PORT}'
QA_DIR      = tempfile.mkdtemp(prefix='sg_qa_walkthrough_')
CLONE_DIR   = os.path.join(QA_DIR, 'my-vault')
CLONE_DIR_2 = os.path.join(QA_DIR, 'my-vault-2')
PASSPHRASE  = 'qa-test-passphrase'
VAULT_ID    = 'qa-test-vault-01'
VAULT_KEY   = f'{PASSPHRASE}:{VAULT_ID}'

CLONE_NOT_IMPLEMENTED = 'clone() not yet implemented — all subsequent tests depend on it'


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
class Test_QA__Vault_Walkthrough:

    def setup_method(self):
        self.crypto    = Vault__Crypto()
        self.api       = Vault__API(base_url=SERVER_URL, access_token='qa-token')
        self.api.setup()
        self.sync      = Vault__Sync(crypto=self.crypto, api=self.api)
        self.inspector = Vault__Inspector(crypto=self.crypto)
        self.keys      = self.crypto.derive_keys_from_vault_key(VAULT_KEY)

    # -------------------------------------------------------------------------
    # Step 1: Seed the server (simulates what the browser does)
    # -------------------------------------------------------------------------

    def test__1__seed_vault(self):
        print_section('Step 1: Seed vault on server')

        os.makedirs(QA_DIR, exist_ok=True)
        read_key  = self.keys['read_key_bytes']
        write_key = self.keys['write_key']

        files = {
            'README.md'        : b'# My Vault\nThis is a test vault.\n',
            'notes/todo.txt'   : b'- Buy milk\n- Write code\n- Ship it\n',
            'notes/ideas.txt'  : b'Idea 1: encrypted vaults as git repos\n',
        }

        children = {}
        file_ids = {}
        for path, content in files.items():
            file_id   = os.urandom(6).hex()
            encrypted = self.crypto.encrypt(read_key, content)
            result    = self.api.write(VAULT_ID, file_id, write_key, encrypted)
            file_ids[path] = file_id

            parts   = path.split('/')
            current = children
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {'type': 'folder', 'children': {}}
                current = current[part]['children']
            current[parts[-1]] = {'type': 'file', 'file_id': file_id, 'size': len(content)}

            print(f'  Uploaded: {path} -> file_id={file_id} ({len(content)} bytes)')

        tree = {'version': 1, 'tree': {'/': {'type': 'folder', 'children': children}}}
        settings = {'vault_id': VAULT_ID, 'vault_name': 'QA Test Vault'}

        self.api.write(VAULT_ID, self.keys['tree_file_id'], write_key,
                       self.crypto.encrypt(read_key, json.dumps(tree).encode()))
        self.api.write(VAULT_ID, self.keys['settings_file_id'], write_key,
                       self.crypto.encrypt(read_key, json.dumps(settings).encode()))

        print(f'\n  Vault ID:          {VAULT_ID}')
        print(f'  Tree file ID:      {self.keys["tree_file_id"]}')
        print(f'  Settings file ID:  {self.keys["settings_file_id"]}')
        print(f'  Files uploaded:    {len(files)}')
        print(f'\n  Server is ready for clone.')

    # -------------------------------------------------------------------------
    # Step 2: Clone the vault
    # -------------------------------------------------------------------------

    @pytest.mark.skip(reason=CLONE_NOT_IMPLEMENTED)
    def test__2__clone_vault(self):
        print_section('Step 2: Clone vault from server')

        if os.path.exists(CLONE_DIR):
            shutil.rmtree(CLONE_DIR)

        result = self.sync.clone(VAULT_KEY, CLONE_DIR)

        print(f'  Cloned to: {result}')
        print(f'\n  File tree:')
        print_tree(CLONE_DIR)

    # -------------------------------------------------------------------------
    # Step 3: Inspect the object store
    # -------------------------------------------------------------------------

    @pytest.mark.skip(reason=CLONE_NOT_IMPLEMENTED)
    def test__3__inspect_object_store(self):
        print_section('Step 3: Inspect the local object store')

        summary = self.inspector.format_vault_summary(CLONE_DIR)
        print(f'\n{summary}')

        read_key = self.keys['read_key_bytes']
        tree_info = self.inspector.inspect_tree(CLONE_DIR, read_key=read_key)
        print(f'\n  Tree entries:')
        for entry in tree_info.get('entries', []):
            print(f'    {entry["path"]:30s}  blob={entry["blob_id"]}  size={entry["size"]}')

        chain = self.inspector.inspect_commit_chain(CLONE_DIR, read_key=read_key)
        print(f'\n  Commit chain:')
        print(self.inspector.format_commit_log(chain))

    # -------------------------------------------------------------------------
    # Step 3b: Cat individual objects (commit, tree, blob)
    # -------------------------------------------------------------------------

    @pytest.mark.skip(reason=CLONE_NOT_IMPLEMENTED)
    def test__3b__cat_objects(self):
        print_section('Step 3b: Cat object contents')

        read_key = self.keys['read_key_bytes']

        chain = self.inspector.inspect_commit_chain(CLONE_DIR, read_key=read_key)
        assert len(chain) > 0
        head_commit_id = chain[0]['commit_id']
        tree_id        = chain[0]['tree_id']

        print(self.inspector.format_cat_object(CLONE_DIR, head_commit_id, read_key))

        print()
        print(self.inspector.format_cat_object(CLONE_DIR, tree_id, read_key))

        tree_info = self.inspector.inspect_tree(CLONE_DIR, read_key=read_key)
        first_blob = tree_info['entries'][0]['blob_id']
        print()
        print(self.inspector.format_cat_object(CLONE_DIR, first_blob, read_key))

        print()
        print(self.inspector.format_cat_object(CLONE_DIR, 'does_not_exist', read_key))

    # -------------------------------------------------------------------------
    # Step 4: Check status (should be clean after clone)
    # -------------------------------------------------------------------------

    @pytest.mark.skip(reason=CLONE_NOT_IMPLEMENTED)
    def test__4__status_after_clone(self):
        print_section('Step 4: Status after clone (should be clean)')

        status = self.sync.status(CLONE_DIR)
        print(f'  Status: {json.dumps(status, indent=2)}')
        assert status['clean'], 'Expected clean status after clone'

    # -------------------------------------------------------------------------
    # Step 5: Add a new file locally
    # -------------------------------------------------------------------------

    @pytest.mark.skip(reason=CLONE_NOT_IMPLEMENTED)
    def test__5__add_local_file(self):
        print_section('Step 5: Add a new file locally')

        new_file = os.path.join(CLONE_DIR, 'changelog.txt')
        with open(new_file, 'w') as f:
            f.write('v0.1 - Initial vault created\nv0.2 - Added changelog\n')

        print(f'  Created: {new_file}')

        status = self.sync.status(CLONE_DIR)
        print(f'\n  Status: {json.dumps(status, indent=2)}')
        assert 'changelog.txt' in status['added']

    # -------------------------------------------------------------------------
    # Step 6: Push changes to server
    # -------------------------------------------------------------------------

    @pytest.mark.skip(reason=CLONE_NOT_IMPLEMENTED)
    def test__6__push_changes(self):
        print_section('Step 6: Push changes to server')

        result = self.sync.push(CLONE_DIR)
        print(f'  Push result: {json.dumps(result, indent=2)}')

        status = self.sync.status(CLONE_DIR)
        print(f'\n  Status after push: {json.dumps(status, indent=2)}')
        assert status['clean'], 'Expected clean after push'

        read_key = self.keys['read_key_bytes']
        chain = self.inspector.inspect_commit_chain(CLONE_DIR, read_key=read_key)
        print(f'\n  Commit chain (should have 2 commits):')
        print(self.inspector.format_commit_log(chain))

    # -------------------------------------------------------------------------
    # Step 7: Clone into a second directory (verify round-trip)
    # -------------------------------------------------------------------------

    @pytest.mark.skip(reason=CLONE_NOT_IMPLEMENTED)
    def test__7__clone_second_copy(self):
        print_section('Step 7: Clone into second directory')

        if os.path.exists(CLONE_DIR_2):
            shutil.rmtree(CLONE_DIR_2)

        self.sync.clone(VAULT_KEY, CLONE_DIR_2)

        print(f'  Cloned to: {CLONE_DIR_2}')
        print(f'\n  File tree:')
        print_tree(CLONE_DIR_2)

        changelog = os.path.join(CLONE_DIR_2, 'changelog.txt')
        assert os.path.isfile(changelog), 'changelog.txt missing from second clone'
        with open(changelog) as f:
            content = f.read()
        print(f'\n  changelog.txt content:')
        print(f'    {content}')

    # -------------------------------------------------------------------------
    # Step 8: Modify a file and push from second copy
    # -------------------------------------------------------------------------

    @pytest.mark.skip(reason=CLONE_NOT_IMPLEMENTED)
    def test__8__modify_and_push_from_second_copy(self):
        print_section('Step 8: Modify file in second copy and push')

        readme = os.path.join(CLONE_DIR_2, 'README.md')
        with open(readme, 'w') as f:
            f.write('# My Vault\nThis is a test vault.\n\nUpdated from second clone!\n')

        status = self.sync.status(CLONE_DIR_2)
        print(f'  Status: {json.dumps(status, indent=2)}')
        assert 'README.md' in status['modified']

        result = self.sync.push(CLONE_DIR_2)
        print(f'\n  Push result: {json.dumps(result, indent=2)}')

    # -------------------------------------------------------------------------
    # Step 9: Pull changes into first copy
    # -------------------------------------------------------------------------

    @pytest.mark.skip(reason=CLONE_NOT_IMPLEMENTED)
    def test__9__pull_into_first_copy(self):
        print_section('Step 9: Pull changes into first copy')

        result = self.sync.pull(CLONE_DIR)
        print(f'  Pull result: {json.dumps(result, indent=2)}')

        readme = os.path.join(CLONE_DIR, 'README.md')
        with open(readme) as f:
            content = f.read()
        print(f'\n  README.md after pull:')
        print(f'    {content}')
        assert 'Updated from second clone!' in content

        read_key = self.keys['read_key_bytes']
        chain = self.inspector.inspect_commit_chain(CLONE_DIR, read_key=read_key)
        print(f'\n  Commit chain (should have 3 commits):')
        print(self.inspector.format_commit_log(chain))

    # -------------------------------------------------------------------------
    # Step 10: Delete a file and push
    # -------------------------------------------------------------------------

    @pytest.mark.skip(reason=CLONE_NOT_IMPLEMENTED)
    def test__10__delete_file_and_push(self):
        print_section('Step 10: Delete a file and push')

        os.remove(os.path.join(CLONE_DIR, 'notes', 'ideas.txt'))
        print(f'  Deleted: notes/ideas.txt')

        status = self.sync.status(CLONE_DIR)
        print(f'\n  Status: {json.dumps(status, indent=2)}')
        assert 'notes/ideas.txt' in status['deleted']

        result = self.sync.push(CLONE_DIR)
        print(f'\n  Push result: {json.dumps(result, indent=2)}')

        status = self.sync.status(CLONE_DIR)
        print(f'\n  Status after push: {json.dumps(status, indent=2)}')
        assert status['clean']

    # -------------------------------------------------------------------------
    # Step 11: Final inspection
    # -------------------------------------------------------------------------

    @pytest.mark.skip(reason=CLONE_NOT_IMPLEMENTED)
    def test__11__final_inspection(self):
        print_section('Step 11: Final vault state')

        print(f'\n  First copy ({CLONE_DIR}):')
        print_tree(CLONE_DIR)

        summary = self.inspector.format_vault_summary(CLONE_DIR)
        print(f'\n{summary}')

        read_key = self.keys['read_key_bytes']
        chain = self.inspector.inspect_commit_chain(CLONE_DIR, read_key=read_key)
        print(f'\n  Full commit history:')
        print(self.inspector.format_commit_log(chain))

        stats = self.inspector.object_store_stats(CLONE_DIR)
        print(f'\n  Object store stats:')
        print(f'    Total objects: {stats["total_objects"]}')
        print(f'    Total bytes:   {stats["total_bytes"]}')
        print(f'    Buckets:       {stats["buckets"]}')
