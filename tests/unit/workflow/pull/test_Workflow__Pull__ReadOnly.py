"""Tests for Workflow__Pull__ReadOnly — the redefined read-only pull (contract §5.3, §7.1).

Covers:
  - Static structure: 4 steps, correct order/names, NO merge step.
  - Dispatch: cmd_pull selects the RO workflow when clone_mode == READ_ONLY.
  - Safety: a read-only pull issues NO server writes (api.write / api.delete) —
    only api.read-family calls — preserving the zero-knowledge guarantee.
  - Behaviour: the working copy updates to the new named-branch HEAD after a
    fresh commit was pushed to the server.
"""
import os

import pytest

from sgit_ai.workflow.pull.Workflow__Pull__ReadOnly         import Workflow__Pull__ReadOnly
from sgit_ai.workflow.pull.Step__Pull__Derive_Keys          import Step__Pull__Derive_Keys
from sgit_ai.workflow.pull.Step__Pull__RO__Load_Named_Head  import Step__Pull__RO__Load_Named_Head
from sgit_ai.workflow.pull.Step__Pull__Fetch_Missing        import Step__Pull__Fetch_Missing
from sgit_ai.workflow.pull.Step__Pull__RO__Checkout         import Step__Pull__RO__Checkout
from sgit_ai.workflow.pull.Step__Pull__Merge                import Step__Pull__Merge
from sgit_ai.schemas.workflow.pull.Schema__Pull__State      import Schema__Pull__State


# ── helpers ─────────────────────────────────────────────────────────────────

class _Server_Write_Spy:
    """Wraps a Vault__API instance to count server-mutating calls (write/delete).

    Read-family calls (read, batch_read, presigned_read_url) pass through
    untouched and are NOT counted — they are permitted on the read-only path.
    """

    def __init__(self, api):
        self.api          = api
        self.write_calls  = []
        self.delete_calls = []
        self._orig_write  = api.write
        self._orig_delete = api.delete

    def __enter__(self):
        def _write(*a, **k):
            self.write_calls.append((a, k))
            return self._orig_write(*a, **k)

        def _delete(*a, **k):
            self.delete_calls.append((a, k))
            return self._orig_delete(*a, **k)

        self.api.write  = _write
        self.api.delete = _delete
        return self

    def __exit__(self, *exc):
        self.api.write  = self._orig_write
        self.api.delete = self._orig_delete
        return False

    @property
    def server_mutations(self):
        return len(self.write_calls) + len(self.delete_calls)


def _push_new_commit_to_server(snap, filename, content):
    """Full-clone the source vault from its key, add a file, commit + push.

    Uses the same shared in-memory api._store the read-only clone reads from,
    so afterwards the read-only clone is exactly one commit 'behind'. Returns the
    new working-copy file's (path, content).
    """
    import tempfile
    from sgit_ai.core.Vault__Sync   import Vault__Sync
    from sgit_ai.crypto.Vault__Crypto import Vault__Crypto

    crypto   = snap['crypto']
    api      = snap['api']                       # same store the RO clone uses
    work_dir = tempfile.mkdtemp()
    full_dir = os.path.join(work_dir, 'full')

    full_sync = Vault__Sync(crypto=crypto, api=api)
    full_sync.clone(snap['source_vault_key'], full_dir)

    with open(os.path.join(full_dir, filename), 'w') as fh:
        fh.write(content)
    full_sync.commit(full_dir, message=f'add {filename}')
    full_sync.push(full_dir)
    return filename, content


# ── static structure ────────────────────────────────────────────────────────

class Test_Workflow__Pull__ReadOnly__Structure:

    def test_workflow_name(self):
        wf = Workflow__Pull__ReadOnly()
        assert str(wf.name) == 'pull-read-only'

    def test_workflow_version(self):
        wf = Workflow__Pull__ReadOnly()
        assert str(wf.version) == '1.0.0'

    def test_workflow_has_four_steps(self):
        wf = Workflow__Pull__ReadOnly()
        assert len(wf.steps) == 4

    def test_step_order(self):
        wf = Workflow__Pull__ReadOnly()
        assert wf.steps[0] is Step__Pull__Derive_Keys
        assert wf.steps[1] is Step__Pull__RO__Load_Named_Head
        assert wf.steps[2] is Step__Pull__Fetch_Missing
        assert wf.steps[3] is Step__Pull__RO__Checkout

    def test_step_names(self):
        names = [str(cls().name) for cls in Workflow__Pull__ReadOnly.steps]
        assert names == ['derive-keys', 'ro-load-named-head', 'fetch-missing', 'ro-checkout']

    def test_no_merge_step(self):
        # Guard rail §8: NO merge / commit-creation on the read-only pull path.
        assert Step__Pull__Merge not in Workflow__Pull__ReadOnly.steps
        names = [str(cls().name) for cls in Workflow__Pull__ReadOnly.steps]
        assert 'merge' not in names

    def test_reuses_derive_keys_and_fetch_missing(self):
        # Guard rail §8 #12: the shared steps are reused as-is, not re-defined.
        assert Step__Pull__Derive_Keys  in Workflow__Pull__ReadOnly.steps
        assert Step__Pull__Fetch_Missing in Workflow__Pull__ReadOnly.steps

    def test_all_steps_use_pull_state_schema(self):
        for cls in Workflow__Pull__ReadOnly.steps:
            assert cls.input_schema  is Schema__Pull__State
            assert cls.output_schema is Schema__Pull__State


# ── dispatch (cmd_pull selects RO workflow) ─────────────────────────────────

class Test_Workflow__Pull__ReadOnly__Dispatch:

    def test_cmd_pull_dispatches_to_read_only(self, read_only_clone, monkeypatch):
        """cmd_pull must route a READ_ONLY clone to the RO pull, not the full pull."""
        import sgit_ai.cli.CLI__Vault as cli_mod
        from sgit_ai.cli.CLI__Vault import CLI__Vault

        cli = CLI__Vault()

        called = {'ro': 0, 'full': 0}
        monkeypatch.setattr(cli, '_cmd_pull_read_only',
                            lambda args: called.__setitem__('ro', called['ro'] + 1))
        # If the full path is taken it calls create_sync(); flag that.
        monkeypatch.setattr(cli, 'create_sync',
                            lambda *a, **k: called.__setitem__('full', called['full'] + 1))

        class _Args:
            directory = read_only_clone['ro_dir']
            token     = None

        cli.cmd_pull(_Args())
        assert called['ro']   == 1            # RO workflow chosen
        assert called['full'] == 0            # full pull never invoked

    def test_cmd_pull_read_only_no_longer_exits_1(self, read_only_clone, capsys):
        """The refuse-gate is gone: a read-only pull runs and returns (no SystemExit)."""
        from sgit_ai.cli.CLI__Vault import CLI__Vault

        cli = CLI__Vault()

        class _Args:
            directory = read_only_clone['ro_dir']
            token     = None
            base_url  = None
            name      = None

        # Must not raise SystemExit(1); should print a read-only-flavoured result.
        cli.cmd_pull(_Args())
        out = capsys.readouterr().out
        assert 'read-only' in out.lower() or 'up to date' in out.lower()


# ── safety + behaviour (functional, against the in-memory server) ───────────

class Test_Workflow__Pull__ReadOnly__Functional:

    def test_pull_up_to_date_makes_no_server_writes(self, read_only_clone):
        """A no-op RO pull (already at HEAD) must not write to the server."""
        sync = read_only_clone['sync']
        api  = read_only_clone['api']
        ro   = read_only_clone['ro_dir']

        with _Server_Write_Spy(api) as spy:
            result = sync.pull_read_only(ro)
        assert spy.server_mutations == 0
        assert result['status'] == 'up_to_date'

    def test_pull_fetches_new_commit_and_updates_working_copy(self, read_only_clone_snapshot, read_only_clone):
        """After a 2nd commit is pushed, RO pull downloads it and re-checks-out."""
        sync = read_only_clone['sync']
        ro   = read_only_clone['ro_dir']

        # The RO clone shares the api/store with the snapshot helper below.
        filename, content = _push_new_commit_to_server(read_only_clone,
                                                        'added_by_remote.txt',
                                                        'fresh remote content')

        new_path = os.path.join(ro, filename)
        assert not os.path.isfile(new_path)          # not present before pull

        result = sync.pull_read_only(ro)

        assert os.path.isfile(new_path)              # working copy updated
        with open(new_path) as fh:
            assert fh.read() == content
        assert result['status'] == 'merged'          # _pull_state_to_dict label
        assert filename in result['added']

    def test_pull_with_new_commit_makes_no_server_writes(self, read_only_clone):
        """The whole RO pull path (incl. fetch-missing + checkout) writes nothing
        to the server — only api.read-family calls are permitted (zero-knowledge)."""
        sync = read_only_clone['sync']
        api  = read_only_clone['api']
        ro   = read_only_clone['ro_dir']

        _push_new_commit_to_server(read_only_clone, 'second.txt', 'second body')

        with _Server_Write_Spy(api) as spy:
            sync.pull_read_only(ro)
        assert spy.write_calls  == []
        assert spy.delete_calls == []

    def test_pull_does_not_write_clone_branch_ref(self, read_only_clone):
        """Guard rail §8 #4: no clone-branch ref/metadata appears in the bare store."""
        sync = read_only_clone['sync']
        ro   = read_only_clone['ro_dir']

        _push_new_commit_to_server(read_only_clone, 'third.txt', 'third body')
        sync.pull_read_only(ro)

        branches_dir = os.path.join(ro, '.sg_vault', 'bare', 'branches')
        # branches/ must stay empty (no clone branch on an RO clone).
        if os.path.isdir(branches_dir):
            assert os.listdir(branches_dir) == []

    def test_pull_does_not_create_vault_key(self, read_only_clone):
        """Guard rail §8 #2: pull never materialises a vault_key on an RO clone."""
        sync = read_only_clone['sync']
        ro   = read_only_clone['ro_dir']

        _push_new_commit_to_server(read_only_clone, 'fourth.txt', 'fourth body')
        sync.pull_read_only(ro)

        assert not os.path.isfile(os.path.join(ro, '.sg_vault', 'local', 'vault_key'))

    def test_status_before_pull_still_updates_working_copy(self, read_only_clone):
        """Regression: `sgit status` refreshes the cached named ref. A subsequent
        `sgit pull` must still download the new HEAD and update the working copy —
        the cached-ref pointer must not poison the fetch-missing stop-point."""
        sync = read_only_clone['sync']
        ro   = read_only_clone['ro_dir']

        filename, content = _push_new_commit_to_server(read_only_clone,
                                                       'after_status.txt',
                                                       'content after status')

        # status() reads + caches the remote named ref (advances the ref pointer
        # ahead of the still-undownloaded commit object).
        st = sync.status(ro)
        assert st['behind'] == 1

        new_path = os.path.join(ro, filename)
        assert not os.path.isfile(new_path)

        sync.pull_read_only(ro)
        assert os.path.isfile(new_path)                       # pull still checks out the new HEAD
        with open(new_path) as fh:
            assert fh.read() == content
