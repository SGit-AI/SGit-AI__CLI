from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory    # noqa: F401 — re-export for backwards compat

import copy
import os
import shutil
import tempfile

import pytest

from sgit_ai.api.Vault__API__In_Memory  import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto       import Vault__Crypto
from sgit_ai.sync.Vault__Branch_Switch  import Vault__Branch_Switch
from sgit_ai.sync.Vault__Sync           import Vault__Sync


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sync():
    crypto = Vault__Crypto()
    api    = Vault__API__In_Memory()
    api.setup()
    return Vault__Sync(crypto=crypto, api=api), crypto, api


def _snapshot(api, snap_dir):
    return copy.deepcopy(api._store), snap_dir


def _restore_api(snapshot_store):
    api = Vault__API__In_Memory()
    api.setup()
    api._store = copy.deepcopy(snapshot_store)
    return api


# ---------------------------------------------------------------------------
# Session fixture: pre-derived keys
# ---------------------------------------------------------------------------

@pytest.fixture(scope='session')
def known_test_keys():
    """Pre-derived keys for 5 canonical test vault_keys."""
    crypto = Vault__Crypto()
    # Format: passphrase:vault_id  (24-char passphrase + 8-char vault_id)
    keys = [
        'coralequalpassphrase1234:coralvlt',
        'givefoulpassphrase836100:givefvlt',
        'azurehatpassphrase799120:azurehvlt',
        'plumstackpassphrase55660:plumsvlt',
        'olivefernpassphrase11330:olivefvlt',
    ]
    return {k: crypto.derive_keys_from_vault_key(k) for k in keys}


@pytest.fixture(scope='session')
def precomputed_encrypted_blobs(known_test_keys):
    """Pre-encrypted blobs for tests that need 'a ciphertext to load', not crypto testing."""
    crypto   = Vault__Crypto()
    read_key = known_test_keys['coralequalpassphrase1234:coralvlt']['read_key_bytes']
    return {
        'small'  : crypto.encrypt(read_key, b'small content'),
        'medium' : crypto.encrypt(read_key, b'medium content' * 100),
        'large'  : crypto.encrypt(read_key, b'large content'  * 10_000),
    }


# ---------------------------------------------------------------------------
# NF1 — two_clones_pushed (module scope snapshot + function scope workspace)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def two_clones_pushed():
    """Module-scope snapshot: Alice init+commit+push, Bob clone."""
    sync, crypto, api = _make_sync()
    snap_dir  = tempfile.mkdtemp()
    alice_dir = os.path.join(snap_dir, 'alice')
    bob_dir   = os.path.join(snap_dir, 'bob')

    result    = sync.init(alice_dir)
    vault_key = result['vault_key']

    with open(os.path.join(alice_dir, 'init.txt'), 'w') as fh:
        fh.write('init')

    commit_result = sync.commit(alice_dir, message='initial commit')
    sync.push(alice_dir)
    head_commit_id = commit_result['commit_id']

    clone_sync = Vault__Sync(crypto=crypto, api=api)
    clone_sync.clone(vault_key, bob_dir)

    snapshot_store = copy.deepcopy(api._store)
    yield {
        'snapshot_dir'   : snap_dir,
        'alice_sub'      : 'alice',
        'bob_sub'        : 'bob',
        'vault_key'      : vault_key,
        'head_commit_id' : head_commit_id,
        'snapshot_store' : snapshot_store,
    }
    shutil.rmtree(snap_dir, ignore_errors=True)


@pytest.fixture
def two_clones_workspace(two_clones_pushed):
    """Per-test copytree copy of the two_clones_pushed snapshot."""
    snap    = two_clones_pushed
    tmp_dir = tempfile.mkdtemp()

    alice_src = os.path.join(snap['snapshot_dir'], snap['alice_sub'])
    bob_src   = os.path.join(snap['snapshot_dir'], snap['bob_sub'])
    alice_dst = os.path.join(tmp_dir, snap['alice_sub'])
    bob_dst   = os.path.join(tmp_dir, snap['bob_sub'])
    shutil.copytree(alice_src, alice_dst)
    shutil.copytree(bob_src,   bob_dst)

    api    = _restore_api(snap['snapshot_store'])
    crypto = Vault__Crypto()
    sync   = Vault__Sync(crypto=crypto, api=api)

    yield {
        'alice_dir'      : alice_dst,
        'bob_dir'        : bob_dst,
        'vault_key'      : snap['vault_key'],
        'head_commit_id' : snap['head_commit_id'],
        'sync'           : sync,
        'crypto'         : crypto,
        'api'            : api,
        'tmp_dir'        : tmp_dir,
    }
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# NF2 — vault_with_N_commits (module scope snapshots + function scope factory)
# ---------------------------------------------------------------------------

def _build_vault_with_n_commits(n: int) -> dict:
    sync, crypto, api = _make_sync()
    snap_dir  = tempfile.mkdtemp()
    vault_dir = os.path.join(snap_dir, 'vault')

    sync.init(vault_dir)

    last_commit_id = None
    for i in range(1, n + 1):
        path = os.path.join(vault_dir, f'file_{i}.txt')
        with open(path, 'w') as fh:
            fh.write(f'commit-{i}-content')
        result = sync.commit(vault_dir, message=f'commit {i}')
        last_commit_id = result['commit_id']

    sync.push(vault_dir)

    return {
        'snapshot_dir'   : snap_dir,
        'vault_sub'      : 'vault',
        'vault_key'      : open(os.path.join(vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip(),
        'head_commit_id' : last_commit_id,
        'n'              : n,
        'snapshot_store' : copy.deepcopy(api._store),
    }


@pytest.fixture(scope='module')
def vault_with_N_commits_snapshots():
    """Module-scope: one snapshot per N in {1, 5, 20}."""
    snapshots = {n: _build_vault_with_n_commits(n) for n in (1, 5, 20)}
    yield snapshots
    for snap in snapshots.values():
        shutil.rmtree(snap['snapshot_dir'], ignore_errors=True)


@pytest.fixture
def vault_with_N_commits(vault_with_N_commits_snapshots):
    """Per-test factory: make(n) returns a fresh copytree workspace for N commits."""
    tmp_dirs = []

    def make(n: int) -> dict:
        if n not in vault_with_N_commits_snapshots:
            raise KeyError(f'No snapshot for n={n}; available: {list(vault_with_N_commits_snapshots)}')
        snap    = vault_with_N_commits_snapshots[n]
        tmp_dir = tempfile.mkdtemp()
        tmp_dirs.append(tmp_dir)

        src = os.path.join(snap['snapshot_dir'], snap['vault_sub'])
        dst = os.path.join(tmp_dir, snap['vault_sub'])
        shutil.copytree(src, dst)

        api    = _restore_api(snap['snapshot_store'])
        crypto = Vault__Crypto()
        sync   = Vault__Sync(crypto=crypto, api=api)

        return {
            'vault_dir'      : dst,
            'vault_key'      : snap['vault_key'],
            'head_commit_id' : snap['head_commit_id'],
            'n'              : n,
            'sync'           : sync,
            'crypto'         : crypto,
            'api'            : api,
            'tmp_dir'        : tmp_dir,
        }

    yield make

    for tmp_dir in tmp_dirs:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# NF3 — vault_with_pending_changes (module scope snapshot + function factory)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def vault_with_pending_changes_snapshot():
    """Module-scope: a vault past initial commit+push with working copy dirtied."""
    sync, crypto, api = _make_sync()
    snap_dir  = tempfile.mkdtemp()
    vault_dir = os.path.join(snap_dir, 'vault')

    sync.init(vault_dir)

    # Initial commit: tracked.txt + modified.txt + deleted.txt
    for name, content in [('tracked.txt', 'tracked'), ('modified.txt', 'original'), ('deleted.txt', 'to-delete')]:
        with open(os.path.join(vault_dir, name), 'w') as fh:
            fh.write(content)
    commit_result = sync.commit(vault_dir, message='initial commit')
    sync.push(vault_dir)

    # Dirty the working copy (these changes are NOT committed)
    with open(os.path.join(vault_dir, 'modified.txt'), 'w') as fh:
        fh.write('modified-content')
    os.unlink(os.path.join(vault_dir, 'deleted.txt'))
    with open(os.path.join(vault_dir, 'untracked.txt'), 'w') as fh:
        fh.write('untracked')

    expected_status = {
        'added'    : ['untracked.txt'],
        'modified' : ['modified.txt'],
        'deleted'  : ['deleted.txt'],
    }

    snapshot_data = {
        'snapshot_dir'    : snap_dir,
        'vault_sub'       : 'vault',
        'vault_key'       : open(os.path.join(vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip(),
        'head_commit_id'  : commit_result['commit_id'],
        'expected_status' : expected_status,
        'snapshot_store'  : copy.deepcopy(api._store),
    }
    yield snapshot_data
    shutil.rmtree(snap_dir, ignore_errors=True)


@pytest.fixture
def vault_with_pending_changes(vault_with_pending_changes_snapshot):
    """Per-test copytree workspace with pending (uncommitted) changes."""
    snap    = vault_with_pending_changes_snapshot
    tmp_dir = tempfile.mkdtemp()

    src = os.path.join(snap['snapshot_dir'], snap['vault_sub'])
    dst = os.path.join(tmp_dir, snap['vault_sub'])
    shutil.copytree(src, dst)

    api    = _restore_api(snap['snapshot_store'])
    crypto = Vault__Crypto()
    sync   = Vault__Sync(crypto=crypto, api=api)

    yield {
        'vault_dir'      : dst,
        'vault_key'      : snap['vault_key'],
        'head_commit_id' : snap['head_commit_id'],
        'expected_status': snap['expected_status'],
        'sync'           : sync,
        'crypto'         : crypto,
        'api'            : api,
        'tmp_dir'        : tmp_dir,
    }
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# NF4 — vault_with_branches (module scope snapshot + function workspace)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def vault_with_branches_snapshot():
    """Module-scope: vault with 'main' and 'feature' branches diverged from a common base."""
    sync, crypto, api = _make_sync()
    snap_dir  = tempfile.mkdtemp()
    vault_dir = os.path.join(snap_dir, 'vault')

    sync.init(vault_dir)

    # Base commit (shared ancestor)
    with open(os.path.join(vault_dir, 'base.txt'), 'w') as fh:
        fh.write('base')
    base_result = sync.commit(vault_dir, message='base commit')
    sync.push(vault_dir)
    base_commit_id = base_result['commit_id']

    vault_key = open(os.path.join(vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()

    # Create a feature branch from the current (main) branch
    branches_info  = sync.branches(vault_dir)
    main_branch    = next(b for b in branches_info['branches'] if b['branch_type'] == 'named')
    main_branch_id = main_branch['branch_id']

    switcher = Vault__Branch_Switch(crypto=crypto)
    new_branch_result = switcher.branch_new(vault_dir, 'feature', from_branch_id=main_branch_id)
    feature_branch_id = new_branch_result['named_branch_id']

    # Switch to feature branch and add a feature commit
    switcher.switch(vault_dir, 'feature')
    with open(os.path.join(vault_dir, 'feature.txt'), 'w') as fh:
        fh.write('feature work')
    feature_result = sync.commit(vault_dir, message='feature commit')
    sync.push(vault_dir)
    feature_commit_id = feature_result['commit_id']

    # Switch back to main and add a main-only commit
    switcher.switch(vault_dir, main_branch['name'])
    with open(os.path.join(vault_dir, 'main_extra.txt'), 'w') as fh:
        fh.write('main extra')
    main_result = sync.commit(vault_dir, message='main commit')
    sync.push(vault_dir)
    main_commit_id = main_result['commit_id']

    snapshot_data = {
        'snapshot_dir'     : snap_dir,
        'vault_sub'        : 'vault',
        'vault_key'        : vault_key,
        'branches'         : {
            'main'    : main_commit_id,
            'feature' : feature_commit_id,
            'base'    : base_commit_id,
        },
        'branch_ids'       : {
            'main'    : main_branch_id,
            'feature' : feature_branch_id,
        },
        'snapshot_store'   : copy.deepcopy(api._store),
    }
    yield snapshot_data
    shutil.rmtree(snap_dir, ignore_errors=True)


@pytest.fixture
def vault_with_branches(vault_with_branches_snapshot):
    """Per-test copytree workspace with two diverged branches."""
    snap    = vault_with_branches_snapshot
    tmp_dir = tempfile.mkdtemp()

    src = os.path.join(snap['snapshot_dir'], snap['vault_sub'])
    dst = os.path.join(tmp_dir, snap['vault_sub'])
    shutil.copytree(src, dst)

    api    = _restore_api(snap['snapshot_store'])
    crypto = Vault__Crypto()
    sync   = Vault__Sync(crypto=crypto, api=api)

    yield {
        'vault_dir'   : dst,
        'vault_key'   : snap['vault_key'],
        'branches'    : snap['branches'],
        'branch_ids'  : snap['branch_ids'],
        'sync'        : sync,
        'crypto'      : crypto,
        'api'         : api,
        'tmp_dir'     : tmp_dir,
    }
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# NF5 — read_only_clone (module scope snapshot + function workspace)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def read_only_clone_snapshot():
    """Module-scope: a vault cloned in read-only mode (clone_mode.json has only read_key)."""
    sync, crypto, api = _make_sync()
    snap_dir    = tempfile.mkdtemp()
    source_dir  = os.path.join(snap_dir, 'source')
    ro_dir      = os.path.join(snap_dir, 'ro_clone')

    result    = sync.init(source_dir)
    vault_key = result['vault_key']

    with open(os.path.join(source_dir, 'data.txt'), 'w') as fh:
        fh.write('read-only data')
    sync.commit(source_dir, message='initial commit')
    sync.push(source_dir)

    keys         = crypto.derive_keys_from_vault_key(vault_key)
    vault_id     = keys['vault_id']
    read_key_hex = keys['read_key']

    ro_clone_sync = Vault__Sync(crypto=crypto, api=api)
    ro_clone_sync.clone_read_only(vault_id, read_key_hex, ro_dir)

    snapshot_data = {
        'snapshot_dir'      : snap_dir,
        'source_sub'        : 'source',
        'ro_clone_sub'      : 'ro_clone',
        'source_vault_key'  : vault_key,
        'vault_id'          : vault_id,
        'read_key_hex'      : read_key_hex,
        'snapshot_store'    : copy.deepcopy(api._store),
    }
    yield snapshot_data
    shutil.rmtree(snap_dir, ignore_errors=True)


@pytest.fixture
def read_only_clone(read_only_clone_snapshot):
    """Per-test copytree workspace with a read-only clone."""
    snap    = read_only_clone_snapshot
    tmp_dir = tempfile.mkdtemp()

    src = os.path.join(snap['snapshot_dir'], snap['ro_clone_sub'])
    dst = os.path.join(tmp_dir, snap['ro_clone_sub'])
    shutil.copytree(src, dst)

    api    = _restore_api(snap['snapshot_store'])
    crypto = Vault__Crypto()
    sync   = Vault__Sync(crypto=crypto, api=api)

    yield {
        'ro_dir'           : dst,
        'source_vault_key' : snap['source_vault_key'],
        'vault_id'         : snap['vault_id'],
        'read_key_hex'     : snap['read_key_hex'],
        'sync'             : sync,
        'crypto'           : crypto,
        'api'              : api,
        'tmp_dir'          : tmp_dir,
    }
    shutil.rmtree(tmp_dir, ignore_errors=True)
