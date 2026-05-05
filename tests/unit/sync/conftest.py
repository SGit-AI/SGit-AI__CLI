"""Shared fixtures for sync unit tests.

Implements F3 / F4 / F5 / F6 from
  team/villager/dev/v0.10.30__shared-fixtures-design.md (Section 2).

F3 `bare_vault_snapshot` (module scope): two named bare-vault variants
   (`small_vault` and `read_list_vault`) snapshotted to disk.
F4 `bare_vault_workspace` (function scope factory): copytree's an F3
   variant into a fresh tempdir + returns ready-to-use Vault objects.
F5 `probe_vault_env` (session scope): wraps `Vault__Test_Env.
   setup_single_vault('give-foul-8361', {'readme.md': 'probe test
   vault'})`; consumed by both Probe classes.
F6 `simple_token_origin_pushed` (module scope): post-push origin for
   `TOKEN_SIMPLE`; consumed only by the 2 share-safe tests in
   `test_Vault__Sync__Simple_Token.py`.

Mutation contract: snapshots are read-only.  All mutation happens
inside the per-test workspace returned by the factory.
"""
import copy
import os
import shutil
import tempfile

import pytest

from sgit_ai.network.api.Vault__API__In_Memory       import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto            import Vault__Crypto
from sgit_ai.storage.Vault__Ref_Manager      import Vault__Ref_Manager
from sgit_ai.core.Vault__Bare                import Vault__Bare
from sgit_ai.core.Vault__Sync                import Vault__Sync

from tests.unit.sync.vault_test_env          import Vault__Test_Env


# ---------------------------------------------------------------------------
# F3 + F4: bare vault snapshot + per-test workspace
# ---------------------------------------------------------------------------

_BARE_VAULT_VARIANTS = {
    'small_vault': {
        'config.json'    : b'{"key": "value"}',
        'deploy/run.sh'  : b'deploy script contents',
    },
    'read_list_vault': {
        'readme.txt'     : b'hello world',
        'docs/guide.md'  : b'# Guide',
    },
}


def _build_bare_vault_snapshot(files: dict) -> dict:
    """Init a vault, write files, commit, advance named ref, strip to bare."""
    snap_dir  = tempfile.mkdtemp(prefix='bare_vault_snap_')
    crypto    = Vault__Crypto()
    sync      = Vault__Sync(crypto=crypto)

    init_result = sync.init(snap_dir)
    vault_key   = init_result['vault_key']

    for rel_path, content in files.items():
        full   = os.path.join(snap_dir, rel_path)
        parent = os.path.dirname(full)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        with open(full, 'wb') as fh:
            fh.write(content)

    commit_result = sync.commit(snap_dir, 'add test files')

    keys     = crypto.derive_keys_from_vault_key(vault_key)
    sg_dir   = os.path.join(snap_dir, '.sg_vault')
    ref_mgr  = Vault__Ref_Manager(vault_path=sg_dir, crypto=crypto)
    ref_mgr.write_ref(keys['ref_file_id'], commit_result['commit_id'],
                      keys['read_key_bytes'])

    # Strip working copy + vault_key file → bare state
    for rel_path in files:
        full = os.path.join(snap_dir, rel_path)
        if os.path.isfile(full):
            os.remove(full)
        # Remove any now-empty parent dirs we created
        parent = os.path.dirname(full)
        if parent != snap_dir and os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)
    vault_key_path = os.path.join(snap_dir, '.sg_vault', 'local', 'vault_key')
    if os.path.isfile(vault_key_path):
        os.remove(vault_key_path)

    return {
        'snapshot_dir' : snap_dir,
        'vault_key'    : vault_key,
    }


@pytest.fixture(scope='module')
def bare_vault_snapshot():
    """Build both bare-vault variants once per module."""
    snapshots = {name: _build_bare_vault_snapshot(files)
                 for name, files in _BARE_VAULT_VARIANTS.items()}
    try:
        yield snapshots
    finally:
        for snap in snapshots.values():
            shutil.rmtree(snap['snapshot_dir'], ignore_errors=True)


@pytest.fixture
def bare_vault_workspace(bare_vault_snapshot):
    """Factory: copytree a named F3 snapshot into a fresh tempdir."""
    created = []

    def make(name: str):
        if name not in bare_vault_snapshot:
            raise KeyError(f'Unknown bare vault variant: {name!r}')
        snap    = bare_vault_snapshot[name]
        tmp_dir = tempfile.mkdtemp(prefix=f'bare_vault_ws_{name}_')
        created.append(tmp_dir)
        # copytree wants the destination to NOT exist, so clone INTO a sub
        # of tmp_dir then move-up; simplest: copy the contents directly.
        for entry in os.listdir(snap['snapshot_dir']):
            src = os.path.join(snap['snapshot_dir'], entry)
            dst = os.path.join(tmp_dir, entry)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

        crypto = Vault__Crypto()
        bare   = Vault__Bare(crypto=crypto)
        sync   = Vault__Sync(crypto=crypto)
        return {
            'tmp_dir'   : tmp_dir,
            'vault_key' : snap['vault_key'],
            'crypto'    : crypto,
            'bare'      : bare,
            'sync'      : sync,
        }

    yield make

    for tmp_dir in created:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# F5: probe vault env (session scope, wraps Vault__Test_Env)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='session')
def probe_vault_env():
    """Build the probe-test vault snapshot once per session."""
    env = Vault__Test_Env()
    env.setup_single_vault(vault_key='give-foul-8361',
                           files={'readme.md': 'probe test vault'})
    try:
        yield env
    finally:
        env.cleanup_snapshot()


# ---------------------------------------------------------------------------
# F6: simple-token origin (module scope, post-push)
# ---------------------------------------------------------------------------

TOKEN_SIMPLE   = 'coral-equal-1234'
TOKEN_VAULT_ID = 'c4958581e0ab'   # sha256('coral-equal-1234')[:12]


@pytest.fixture(scope='module')
def simple_token_origin_pushed():
    """Build a post-init+commit+push origin for TOKEN_SIMPLE once per module.

    Consumed by exactly two tests:
      - test_clone_simple_token_vault_found
      - test_clone_simple_token_clone_has_simple_token_config

    Each consumer clones from this snapshot into its own fresh tempdir.
    """
    snap_dir   = tempfile.mkdtemp(prefix='simple_token_origin_')
    origin_dir = os.path.join(snap_dir, 'origin')

    crypto = Vault__Crypto()
    api    = Vault__API__In_Memory()
    api.setup()
    sync   = Vault__Sync(crypto=crypto, api=api)

    sync.init(origin_dir, token=TOKEN_SIMPLE)
    with open(os.path.join(origin_dir, 'data.txt'), 'w') as f:
        f.write('vault data')
    sync.commit(origin_dir, message='add data')
    sync.push(origin_dir)

    snapshot_store = copy.deepcopy(api._store)

    try:
        yield {
            'snapshot_dir'   : snap_dir,
            'origin_sub'     : 'origin',
            'token'          : TOKEN_SIMPLE,
            'vault_id'       : TOKEN_VAULT_ID,
            'snapshot_store' : snapshot_store,
        }
    finally:
        shutil.rmtree(snap_dir, ignore_errors=True)
