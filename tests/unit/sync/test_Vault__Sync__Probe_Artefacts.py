"""M9 closer — probe_token leaves no disk artefacts.

Mutation M9: in the probe_token success path, write clone_mode.json (or any
disk artefact) to disk.  This test asserts that probe_token returns a result
without creating ANY files in the working directory or a dedicated temp dir,
catching any accidental or injected disk-write in probe.

The test strategy:
1. Set up a vault with a known simple-token key and push it.
2. Create a fresh, empty temp directory as the "observed directory".
3. Also snapshot the CWD file set (in case probe writes relative to CWD).
4. Call probe_token — it must succeed (type='vault').
5. Assert the temp directory is still empty.
6. Assert no new files appeared in the CWD.
"""
import copy
import os
import shutil
import tempfile

import pytest

from sgit_ai.api.Vault__API__In_Memory  import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto       import Vault__Crypto
from sgit_ai.core.Vault__Sync           import Vault__Sync


PROBE_TOKEN = 'probe-artefact-9001'   # simple-token format: word-word-NNNN


def _list_all_files(directory: str) -> set:
    """Return a set of relative paths for every file under *directory*."""
    result = set()
    if not os.path.isdir(directory):
        return result
    for root, _, files in os.walk(directory):
        for fname in files:
            abs_path = os.path.join(root, fname)
            result.add(os.path.relpath(abs_path, directory))
    return result


class Test_Vault__Sync__Probe_Artefacts:
    """probe_token must not write any file to disk."""

    @classmethod
    def setup_class(cls):
        """Build a vault with PROBE_TOKEN and push it; snapshot the API store."""
        crypto = Vault__Crypto()
        api    = Vault__API__In_Memory()
        api.setup()
        sync   = Vault__Sync(crypto=crypto, api=api)

        snap_dir  = tempfile.mkdtemp(prefix='probe_artefact_snap_')
        vault_dir = os.path.join(snap_dir, 'vault')

        sync.init(vault_dir, token=PROBE_TOKEN)
        with open(os.path.join(vault_dir, 'readme.txt'), 'w') as fh:
            fh.write('probe artefact test vault')
        sync.commit(vault_dir, message='init')
        sync.push(vault_dir)

        cls._snapshot_store = copy.deepcopy(api._store)
        cls._snap_dir = snap_dir

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls._snap_dir, ignore_errors=True)

    def setup_method(self):
        crypto = Vault__Crypto()
        api    = Vault__API__In_Memory()
        api.setup()
        api._store = copy.deepcopy(self._snapshot_store)
        self.sync = Vault__Sync(crypto=crypto, api=api)

    def test_probe_token_returns_vault_type(self):
        """Sanity: probe must find the vault."""
        result = self.sync.probe_token(PROBE_TOKEN)
        assert result['type'] == 'vault'

    def test_probe_writes_no_files_to_empty_temp_dir(self):
        """M9 core: after probe, the observed temp dir must still be empty."""
        observed_dir = tempfile.mkdtemp(prefix='probe_artefact_observed_')
        try:
            # Change into the observed dir so any CWD-relative writes land there
            original_cwd = os.getcwd()
            os.chdir(observed_dir)
            try:
                result = self.sync.probe_token(PROBE_TOKEN)
            finally:
                os.chdir(original_cwd)

            assert result['type'] == 'vault'

            files_found = _list_all_files(observed_dir)
            assert files_found == set(), (
                f'M9 MUTATION DETECTED: probe_token wrote the following files '
                f'to the working directory: {sorted(files_found)}'
            )
        finally:
            shutil.rmtree(observed_dir, ignore_errors=True)

    def test_probe_writes_no_clone_mode_json(self):
        """probe_token must never write clone_mode.json (the specific M9 artefact)."""
        observed_dir = tempfile.mkdtemp(prefix='probe_m9_clone_mode_')
        try:
            original_cwd = os.getcwd()
            os.chdir(observed_dir)
            try:
                self.sync.probe_token(PROBE_TOKEN)
            finally:
                os.chdir(original_cwd)

            clone_mode_path = os.path.join(observed_dir, 'clone_mode.json')
            assert not os.path.isfile(clone_mode_path), (
                'M9 MUTATION DETECTED: probe_token wrote clone_mode.json to disk.'
            )
        finally:
            shutil.rmtree(observed_dir, ignore_errors=True)

    def test_probe_writes_no_sg_vault_dir(self):
        """probe_token must not create a .sg_vault/ directory."""
        observed_dir = tempfile.mkdtemp(prefix='probe_m9_sg_vault_')
        try:
            original_cwd = os.getcwd()
            os.chdir(observed_dir)
            try:
                self.sync.probe_token(PROBE_TOKEN)
            finally:
                os.chdir(original_cwd)

            sg_vault_path = os.path.join(observed_dir, '.sg_vault')
            assert not os.path.isdir(sg_vault_path), (
                'M9 MUTATION DETECTED: probe_token created a .sg_vault/ directory.'
            )
        finally:
            shutil.rmtree(observed_dir, ignore_errors=True)

    def test_probe_unknown_token_writes_no_files(self):
        """Even when probe raises RuntimeError, it must leave no disk artefacts."""
        # Use a token that doesn't exist in the API
        unknown_token = 'ghost-token-0000'
        observed_dir  = tempfile.mkdtemp(prefix='probe_m9_unknown_')
        try:
            original_cwd = os.getcwd()
            os.chdir(observed_dir)
            try:
                with pytest.raises(RuntimeError):
                    self.sync.probe_token(unknown_token)
            finally:
                os.chdir(original_cwd)

            files_found = _list_all_files(observed_dir)
            assert files_found == set(), (
                f'M9: probe_token wrote files even on failure path: {sorted(files_found)}'
            )
        finally:
            shutil.rmtree(observed_dir, ignore_errors=True)
