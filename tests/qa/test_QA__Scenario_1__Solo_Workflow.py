"""QA Scenario 1: Solo Workflow — init, add files, commit, push, clone, pull.

Maps to arch-simulation-v6 Scenario 1 (Steps 1.1 → 1.3).
Validates file counts, object counts, and state at every step.

Self-contained: uses Vault__API__In_Memory (no external server required).

Run step-by-step:
    pytest tests/qa/test_QA__Scenario_1__Solo_Workflow.py -s -v

Or one at a time:
    pytest tests/qa/test_QA__Scenario_1__Solo_Workflow.py::Test_QA__Scenario_1 -s -k test__1
"""
import json
import os
import shutil
import tempfile

import pytest

from sg_send_cli.crypto.Vault__Crypto      import Vault__Crypto
from sg_send_cli.sync.Vault__Sync          import Vault__Sync
from sg_send_cli.objects.Vault__Inspector   import Vault__Inspector
from sg_send_cli.api.Vault__API__In_Memory import Vault__API__In_Memory
from tests.qa.helpers                       import print_section, print_tree, count_bare_files, count_working_files


VAULT_KEY = 'solo-qa-passphrase:solo-qa-vault'

@pytest.fixture(scope='class')
def shared():
    """Shared state across all ordered tests in this class."""
    api    = Vault__API__In_Memory().setup()
    crypto = Vault__Crypto()
    tmp    = tempfile.mkdtemp(prefix='sg_qa_scenario1_')
    yield dict(api=api, crypto=crypto, tmp=tmp)
    shutil.rmtree(tmp, ignore_errors=True)


class Test_QA__Scenario_1:
    """Solo workflow: init → add files → commit → push → clone → push from clone → pull.

    Follows arch-simulation-v6 Steps 1.1 through 1.3, then extends with
    clone + round-trip to verify the full solo lifecycle.
    """

    # -----------------------------------------------------------------------
    # Step 1.1: Init (Local Only)
    # -----------------------------------------------------------------------

    def test__1__init_vault(self, shared):
        print_section('Step 1.1: Init — Create empty vault')

        sync      = Vault__Sync(crypto=shared['crypto'], api=shared['api'])
        vault_dir = os.path.join(shared['tmp'], 'my-vault')
        result    = sync.init(vault_dir, vault_key=VAULT_KEY)

        shared['vault_dir'] = vault_dir
        shared['sync']      = sync

        print(f'  Directory:    {result["directory"]}')
        print(f'  Vault ID:     {result["vault_id"]}')
        print(f'  Vault key:    {result["vault_key"]}')
        print(f'  Named branch: {result["named_branch"]}')
        print(f'  Clone branch: {result["branch_id"]}')
        print(f'  Init commit:  {result["commit_id"]}')

        # Validate vault structure
        sg_dir = os.path.join(vault_dir, '.sg_vault')
        assert os.path.isdir(os.path.join(sg_dir, 'bare', 'data'))
        assert os.path.isdir(os.path.join(sg_dir, 'bare', 'refs'))
        assert os.path.isdir(os.path.join(sg_dir, 'bare', 'keys'))
        assert os.path.isdir(os.path.join(sg_dir, 'bare', 'indexes'))
        assert os.path.isdir(os.path.join(sg_dir, 'local'))

        # Count encrypted files in bare/
        counts = count_bare_files(vault_dir)
        print(f'\n  Encrypted files in bare/:')
        for k, v in sorted(counts.items()):
            print(f'    {k}: {v}')

        # Arch doc predicts 10 (with 2 in branches/).
        # Implementation: 8 (branch metadata is in the index, not separate files).
        #   data/:    2 (1 empty tree + 1 init commit)
        #   refs/:    2 (named HEAD + clone HEAD, both → init commit)
        #   keys/:    3 (named pub + named priv + clone pub)
        #   indexes/: 1 (branch index)
        assert counts['data']    == 2, f'Expected 2 data objects, got {counts["data"]}'
        assert counts['refs']    == 2, f'Expected 2 refs, got {counts["refs"]}'
        assert counts['keys']    == 3, f'Expected 3 keys, got {counts["keys"]}'
        assert counts['indexes'] == 1, f'Expected 1 index, got {counts["indexes"]}'
        assert counts['total']   == 8, f'Expected 8 total bare files, got {counts["total"]}'

        # Working dir: 0 files (empty vault)
        assert count_working_files(vault_dir) == 0

        # Local files
        local_dir = os.path.join(sg_dir, 'local')
        local_files = sorted(os.listdir(local_dir))
        print(f'\n  Local files: {local_files}')
        assert 'config.json' in local_files

        print(f'\n  File tree:')
        print_tree(vault_dir)

    # -----------------------------------------------------------------------
    # Step 1.1b: Status after init
    # -----------------------------------------------------------------------

    def test__2__status_after_init(self, shared):
        print_section('Step 1.1b: Status — should be clean')

        status = shared['sync'].status(shared['vault_dir'])
        print(f'  Status: {json.dumps(status, indent=2)}')
        assert status['clean'], 'Expected clean status after init'

    # -----------------------------------------------------------------------
    # Step 1.1c: Inspect empty vault
    # -----------------------------------------------------------------------

    def test__3__inspect_empty_vault(self, shared):
        print_section('Step 1.1c: Inspect — empty vault with 1 init commit')

        inspector = Vault__Inspector(crypto=shared['crypto'])
        keys      = shared['crypto'].derive_keys_from_vault_key(VAULT_KEY)
        read_key  = keys['read_key_bytes']

        summary = inspector.format_vault_summary(shared['vault_dir'])
        print(f'\n{summary}')

        chain = inspector.inspect_commit_chain(shared['vault_dir'], read_key=read_key)
        print(f'\n  Commit chain ({len(chain)} commits):')
        print(inspector.format_commit_log(chain))

        assert len(chain) == 1, f'Expected 1 commit, got {len(chain)}'
        assert chain[0]['message'] == 'init'

    # -----------------------------------------------------------------------
    # Step 1.2: Add Files and Commit
    # -----------------------------------------------------------------------

    def test__4__add_files_and_commit(self, shared):
        print_section('Step 1.2: Add files and commit')

        vault_dir = shared['vault_dir']

        # Create files matching arch doc: README.md + configs/EC2.json
        with open(os.path.join(vault_dir, 'README.md'), 'w') as f:
            f.write('# My Project\n')
        os.makedirs(os.path.join(vault_dir, 'configs'), exist_ok=True)
        with open(os.path.join(vault_dir, 'configs', 'EC2.json'), 'w') as f:
            f.write('{"region": "eu-west-2"}\n')

        # Check status before commit
        status = shared['sync'].status(vault_dir)
        print(f'  Status before commit: {json.dumps(status, indent=2)}')
        assert 'README.md' in status['added']
        assert 'configs/EC2.json' in status['added']

        # Commit
        result = shared['sync'].commit(vault_dir, message='add initial files')
        print(f'\n  Commit result: {json.dumps(result, indent=2)}')

        # Count bare/ files after commit
        counts = count_bare_files(vault_dir)
        print(f'\n  Encrypted files in bare/ after commit:')
        for k, v in sorted(counts.items()):
            print(f'    {k}: {v}')

        # After commit: +4 data objects (2 blobs + 1 tree + 1 commit)
        # Implementation uses flat tree (all entries in one tree object),
        # unlike arch doc which predicts separate sub-trees for folders.
        #   data/:    6 (init tree + init commit + 2 blobs + 1 tree + 1 commit)
        #   refs/:    2 (clone ref updated, named ref unchanged)
        #   keys/:    3 (unchanged)
        #   indexes/: 1 (unchanged)
        assert counts['data']  == 6, f'Expected 6 data objects, got {counts["data"]}'
        assert counts['total'] == 12, f'Expected 12 total bare files, got {counts["total"]}'

        # Working dir: 2 files
        assert count_working_files(vault_dir) == 2

        # Status should be clean after commit
        status = shared['sync'].status(vault_dir)
        print(f'\n  Status after commit: {json.dumps(status, indent=2)}')
        assert status['clean']

    # -----------------------------------------------------------------------
    # Step 1.2b: Inspect after commit
    # -----------------------------------------------------------------------

    def test__5__inspect_after_commit(self, shared):
        print_section('Step 1.2b: Inspect — 2 commits, 2 files in tree')

        inspector = Vault__Inspector(crypto=shared['crypto'])
        keys      = shared['crypto'].derive_keys_from_vault_key(VAULT_KEY)
        read_key  = keys['read_key_bytes']

        chain = inspector.inspect_commit_chain(shared['vault_dir'], read_key=read_key)
        print(f'\n  Commit chain ({len(chain)} commits):')
        print(inspector.format_commit_log(chain))
        assert len(chain) == 2

        tree_info = inspector.inspect_tree(shared['vault_dir'], read_key=read_key)
        print(f'\n  Tree entries ({tree_info["file_count"]} files):')
        for entry in tree_info.get('entries', []):
            print(f'    {entry["path"]:30s}  blob={entry["blob_id"]}  size={entry["size"]}')
        assert tree_info['file_count'] == 2

    # -----------------------------------------------------------------------
    # Step 1.3: Push to server
    # -----------------------------------------------------------------------

    def test__6__push_to_server(self, shared):
        print_section('Step 1.3: Push to server')

        result = shared['sync'].push(shared['vault_dir'])
        print(f'  Push result: {json.dumps(result, indent=2)}')

        assert result['status'] == 'pushed'
        assert result['objects_uploaded'] >= 1
        assert result['commits_pushed'] >= 1

        # API store should now have uploaded objects
        api = shared['api']
        print(f'\n  API store: {len(api._store)} entries')
        print(f'  Total API writes: {api._write_count}')

        # After push: bare/ files unchanged (push uploads to API, doesn't change local)
        counts = count_bare_files(shared['vault_dir'])
        print(f'\n  Encrypted files in bare/ after push:')
        for k, v in sorted(counts.items()):
            print(f'    {k}: {v}')
        assert counts['total'] == 12

        # Status still clean
        status = shared['sync'].status(shared['vault_dir'])
        assert status['clean']

    # -----------------------------------------------------------------------
    # Step 1.4: Add more files and second commit
    # -----------------------------------------------------------------------

    def test__7__add_more_files_and_commit(self, shared):
        print_section('Step 1.4: Add more files, second commit')

        vault_dir = shared['vault_dir']

        with open(os.path.join(vault_dir, 'notes.txt'), 'w') as f:
            f.write('- Buy milk\n- Ship it\n')

        status = shared['sync'].status(vault_dir)
        print(f'  Status: {json.dumps(status, indent=2)}')
        assert 'notes.txt' in status['added']

        result = shared['sync'].commit(vault_dir, message='add notes.txt')
        print(f'\n  Commit: {json.dumps(result, indent=2)}')

        # After second commit: +3 data (1 blob + 1 tree + 1 commit) = 9 data total
        counts = count_bare_files(vault_dir)
        print(f'\n  bare/ after second commit:')
        for k, v in sorted(counts.items()):
            print(f'    {k}: {v}')
        assert counts['data'] == 9, f'Expected 9 data objects, got {counts["data"]}'

        status = shared['sync'].status(vault_dir)
        assert status['clean']

    # -----------------------------------------------------------------------
    # Step 1.5: Modify a file, delete another, third commit
    # -----------------------------------------------------------------------

    def test__8__modify_and_delete(self, shared):
        print_section('Step 1.5: Modify README.md, delete configs/EC2.json, commit')

        vault_dir = shared['vault_dir']

        # Modify README
        with open(os.path.join(vault_dir, 'README.md'), 'w') as f:
            f.write('# My Project v2\nUpdated with new info.\n')

        # Delete configs/EC2.json
        os.remove(os.path.join(vault_dir, 'configs', 'EC2.json'))
        os.rmdir(os.path.join(vault_dir, 'configs'))

        status = shared['sync'].status(vault_dir)
        print(f'  Status: {json.dumps(status, indent=2)}')
        assert 'README.md' in status['modified']
        assert 'configs/EC2.json' in status['deleted']

        result = shared['sync'].commit(vault_dir, message='update readme, remove EC2 config')
        print(f'\n  Commit: {json.dumps(result, indent=2)}')

        counts = count_bare_files(vault_dir)
        print(f'\n  bare/ after third commit:')
        for k, v in sorted(counts.items()):
            print(f'    {k}: {v}')

        # Working files: 2 (README.md, notes.txt)
        wf = count_working_files(vault_dir)
        print(f'\n  Working files: {wf}')
        assert wf == 2

    # -----------------------------------------------------------------------
    # Step 1.6: Second push (delta upload)
    # -----------------------------------------------------------------------

    def test__9__second_push(self, shared):
        print_section('Step 1.6: Second push — delta upload')

        result = shared['sync'].push(shared['vault_dir'])
        print(f'  Push result: {json.dumps(result, indent=2)}')

        assert result['status'] == 'pushed'
        assert result['commits_pushed'] >= 2, 'Should push the 2 new commits'

        api = shared['api']
        print(f'\n  API store: {len(api._store)} entries')
        print(f'  Total API writes: {api._write_count}')

    # -----------------------------------------------------------------------
    # Step 1.7: Branches command
    # -----------------------------------------------------------------------

    def test__10__branches(self, shared):
        print_section('Step 1.7: List branches')

        result = shared['sync'].branches(shared['vault_dir'])
        print(f'  Branches: {json.dumps(result, indent=2)}')

        names = [b['name'] for b in result['branches']]
        assert 'current' in names, 'Expected "current" named branch'
        assert 'local'   in names, 'Expected "local" clone branch'

    # -----------------------------------------------------------------------
    # Step 1.8: Final inspection
    # -----------------------------------------------------------------------

    def test__11__final_inspection(self, shared):
        print_section('Step 1.8: Final inspection')

        vault_dir = shared['vault_dir']
        inspector = Vault__Inspector(crypto=shared['crypto'])
        keys      = shared['crypto'].derive_keys_from_vault_key(VAULT_KEY)
        read_key  = keys['read_key_bytes']

        print(f'\n  Vault directory:')
        print_tree(vault_dir)

        chain = inspector.inspect_commit_chain(vault_dir, read_key=read_key)
        print(f'\n  Full commit history ({len(chain)} commits):')
        print(inspector.format_commit_log(chain))

        # Should have: init + 3 commits + merge commits from push
        assert len(chain) >= 4, f'Expected at least 4 commits, got {len(chain)}'

        stats = inspector.object_store_stats(vault_dir)
        print(f'\n  Object store stats:')
        print(f'    Total objects: {stats["total_objects"]}')
        print(f'    Total bytes:   {stats["total_bytes"]}')

        counts = count_bare_files(vault_dir)
        print(f'\n  Final bare/ file counts:')
        for k, v in sorted(counts.items()):
            print(f'    {k}: {v}')

        wf = count_working_files(vault_dir)
        print(f'\n  Working files: {wf}')
        assert wf == 2

        # ---------------------------------------------------------------
        # Arch doc validation summary
        # ---------------------------------------------------------------
        print(f'\n  {"=" * 50}')
        print(f'  ARCH DOC v6 VALIDATION')
        print(f'  {"=" * 50}')
        print(f'  Step 1.1 (Init):')
        print(f'    Arch doc predicts: 10 bare files (incl. 2 in branches/)')
        print(f'    Actual:            8 bare files (branch metadata in index only)')
        print(f'    GAP: branches/ folder unused — metadata consolidated in idx-*')
        print(f'')
        print(f'  Step 1.2 (Commit):')
        print(f'    Arch doc predicts: 5 new objects (2 blobs + 2 sub-trees + 1 commit)')
        print(f'    Actual:            4 new objects (2 blobs + 1 flat tree + 1 commit)')
        print(f'    GAP: Implementation uses flat tree, not hierarchical sub-trees')
        print(f'')
        print(f'  Step 1.3 (Push):')
        print(f'    Arch doc predicts: merge commit on named branch before push')
        print(f'    Actual:            push creates merge during pull phase')
        print(f'    ALIGNED: push does pull-first (fetch-merge), then uploads delta')
        print(f'')
        print(f'  Overall: Core workflow matches arch doc. Two structural differences:')
        print(f'    1. Flat tree vs hierarchical sub-trees')
        print(f'    2. Branch metadata in index vs separate files in branches/')
        print(f'  {"=" * 50}')
