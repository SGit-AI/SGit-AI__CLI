import json
import os
import tempfile
import shutil
import pytest

from sgit_ai.core.Vault__Errors            import Vault__Remotes_Unreadable_Error
from sgit_ai.core.Vault__Remote_Manager    import Vault__Remote_Manager
from sgit_ai.safe_types.Enum__Doctor_Status import Enum__Doctor_Status
from sgit_ai.storage.Vault__Storage        import Vault__Storage


class Test_Vault__Remote_Manager:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.storage = Vault__Storage()
        self.manager = Vault__Remote_Manager(storage=self.storage)
        os.makedirs(self.storage.local_dir(self.tmp_dir), exist_ok=True)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_add_remote(self):
        result = self.manager.add_remote(self.tmp_dir, 'origin',
                                          'https://send.sgraph.ai', 'a1b2c3d4')
        assert str(result.name)     == 'origin'
        assert str(result.url)      == 'https://send.sgraph.ai'
        assert str(result.vault_id) == 'a1b2c3d4'

    def test_list_remotes_empty(self):
        remotes = self.manager.list_remotes(self.tmp_dir)
        assert remotes == []

    def test_list_remotes_after_add(self):
        self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')
        self.manager.add_remote(self.tmp_dir, 'backup', 'https://backup.example.com', 'cc33dd44')
        remotes = self.manager.list_remotes(self.tmp_dir)
        assert len(remotes) == 2
        names = [r['name'] for r in remotes]
        assert 'origin' in names
        assert 'backup' in names

    def test_remove_remote(self):
        self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')
        assert self.manager.remove_remote(self.tmp_dir, 'origin')
        remotes = self.manager.list_remotes(self.tmp_dir)
        assert remotes == []

    def test_remove_nonexistent_returns_false(self):
        assert not self.manager.remove_remote(self.tmp_dir, 'nonexistent')

    def test_get_remote(self):
        self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')
        remote = self.manager.get_remote(self.tmp_dir, 'origin')
        assert remote is not None
        assert str(remote.name) == 'origin'

    def test_get_remote_nonexistent(self):
        remote = self.manager.get_remote(self.tmp_dir, 'missing')
        assert remote is None

    def test_add_duplicate_raises(self):
        self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')
        with pytest.raises(RuntimeError, match='Remote already exists'):
            self.manager.add_remote(self.tmp_dir, 'origin', 'https://other.example.com', 'cc33dd44')

    def test_remotes_persist_to_disk(self):
        self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')

        manager2 = Vault__Remote_Manager(storage=self.storage)
        remotes  = manager2.list_remotes(self.tmp_dir)
        assert len(remotes) == 1
        assert remotes[0]['name'] == 'origin'

    # ── defaults ────────────────────────────────────────────────────────
    def test_first_remote_becomes_default_even_when_not_asked(self):
        """The first remote added is the default regardless of is_default."""
        first = self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')
        assert first.is_default is True
        assert str(self.manager.get_default(self.tmp_dir).name) == 'origin'

    def test_second_remote_is_not_default_unless_asked(self):
        self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')
        second = self.manager.add_remote(self.tmp_dir, 'backup', 'https://b.example.com', 'cc33dd44')
        assert second.is_default is False
        assert [r['is_default'] for r in self.manager.list_remotes(self.tmp_dir)] == [True, False]

    def test_add_with_is_default_moves_the_default_off_the_others(self):
        """is_default=True on add clears the flag on every existing remote (one default at a time)."""
        self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')
        self.manager.add_remote(self.tmp_dir, 'backup', 'https://b.example.com', 'cc33dd44', is_default=True)
        remotes = self.manager.list_remotes(self.tmp_dir)
        assert {r['name']: r['is_default'] for r in remotes} == {'origin': False, 'backup': True}
        assert str(self.manager.get_default(self.tmp_dir).name) == 'backup'

    def test_get_default_with_no_remotes_is_none(self):
        assert self.manager.get_default(self.tmp_dir) is None

    def test_get_default_falls_back_to_the_first_remote_when_none_is_flagged(self):
        """A remotes.json written without any is_default (e.g. by hand) still yields a default: the first."""
        path = self.storage.remotes_path(self.tmp_dir)
        with open(path, 'w') as f:
            json.dump([dict(name='one', url='https://one.example.com', vault_id='aa11bb22', is_default=False),
                       dict(name='two', url='https://two.example.com', vault_id='cc33dd44', is_default=False)], f)
        assert str(self.manager.get_default(self.tmp_dir).name) == 'one'

    def test_removing_the_default_promotes_the_first_survivor(self):
        """Deleting the default remote makes the first remaining one the default (never zero defaults)."""
        self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')
        self.manager.add_remote(self.tmp_dir, 'backup', 'https://b.example.com', 'cc33dd44')
        self.manager.add_remote(self.tmp_dir, 'third',  'https://c.example.com', 'ee55ff66')
        assert self.manager.remove_remote(self.tmp_dir, 'origin') is True
        remotes = self.manager.list_remotes(self.tmp_dir)
        assert [(r['name'], r['is_default']) for r in remotes] == [('backup', True), ('third', False)]

    def test_removing_a_non_default_keeps_the_default(self):
        self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')
        self.manager.add_remote(self.tmp_dir, 'backup', 'https://b.example.com', 'cc33dd44')
        assert self.manager.remove_remote(self.tmp_dir, 'backup') is True
        assert [(r['name'], r['is_default']) for r in self.manager.list_remotes(self.tmp_dir)] == [('origin', True)]

    # ── set_url ─────────────────────────────────────────────────────────
    def test_set_url_rewrites_and_persists(self):
        self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')
        updated = self.manager.set_url(self.tmp_dir, 'origin', 'https://new.example.com')
        assert str(updated.url) == 'https://new.example.com'
        assert str(Vault__Remote_Manager(storage=self.storage).get_remote(self.tmp_dir, 'origin').url) == 'https://new.example.com'

    def test_set_url_unknown_remote_raises(self):
        with pytest.raises(RuntimeError, match='Remote not found: nope'):
            self.manager.set_url(self.tmp_dir, 'nope', 'https://new.example.com')

    # ── set_default ─────────────────────────────────────────────────────
    def test_set_default_moves_the_flag_and_returns_the_remote(self):
        self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')
        self.manager.add_remote(self.tmp_dir, 'backup', 'https://b.example.com', 'cc33dd44')
        found = self.manager.set_default(self.tmp_dir, 'backup')
        assert str(found.name) == 'backup' and found.is_default is True
        assert {r['name']: r['is_default'] for r in self.manager.list_remotes(self.tmp_dir)} == {'origin': False, 'backup': True}

    def test_set_default_unknown_remote_raises_and_changes_nothing(self):
        """An unknown name raises BEFORE saving: the existing default survives on disk."""
        self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')
        with pytest.raises(RuntimeError, match='Remote not found: nope'):
            self.manager.set_default(self.tmp_dir, 'nope')
        assert self.manager.list_remotes(self.tmp_dir)[0]['is_default'] is True

    # ── rename_remote ───────────────────────────────────────────────────
    def test_rename_remote_keeps_url_vault_id_and_default_flag(self):
        self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')
        renamed = self.manager.rename_remote(self.tmp_dir, 'origin', 'upstream')
        assert str(renamed.name) == 'upstream'
        assert self.manager.get_remote(self.tmp_dir, 'origin') is None
        remotes = self.manager.list_remotes(self.tmp_dir)
        assert remotes == [dict(name='upstream', url='https://api.example.com', vault_id='aa11bb22',
                                is_default=True, tls_verify=True)]

    def test_rename_to_an_existing_name_raises(self):
        self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')
        self.manager.add_remote(self.tmp_dir, 'backup', 'https://b.example.com', 'cc33dd44')
        with pytest.raises(RuntimeError, match='Remote already exists: backup'):
            self.manager.rename_remote(self.tmp_dir, 'origin', 'backup')

    def test_rename_unknown_remote_raises(self):
        with pytest.raises(RuntimeError, match='Remote not found: ghost'):
            self.manager.rename_remote(self.tmp_dir, 'ghost', 'other')

    # ── update_health ───────────────────────────────────────────────────
    def test_update_health_stamps_status_and_time(self):
        """A health check records the status enum and a millisecond timestamp, persisted to disk."""
        self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')
        updated = self.manager.update_health(self.tmp_dir, 'origin', Enum__Doctor_Status.PASS)
        assert updated.last_health_status == Enum__Doctor_Status.PASS
        assert int(updated.last_health_at) > 1_600_000_000_000
        reloaded = Vault__Remote_Manager(storage=self.storage).get_remote(self.tmp_dir, 'origin')
        assert reloaded.last_health_status == Enum__Doctor_Status.PASS
        assert int(reloaded.last_health_at) == int(updated.last_health_at)

    def test_update_health_unknown_remote_returns_none(self):
        assert self.manager.update_health(self.tmp_dir, 'ghost', Enum__Doctor_Status.FAIL) is None

    # ── tls_verify ──────────────────────────────────────────────────────
    def test_tls_verify_false_is_stored_and_listed(self):
        self.manager.add_remote(self.tmp_dir, 'lab', 'https://lab.example.com', 'aa11bb22', tls_verify=False)
        assert self.manager.list_remotes(self.tmp_dir)[0]['tls_verify'] is False

    # ── unreadable file ─────────────────────────────────────────────────
    def test_unreadable_remotes_file_refuses_instead_of_guessing(self):
        """A remotes.json that exists but is not valid JSON raises Vault__Remotes_Unreadable_Error
        (TM-F40) from every entry point rather than reading as 'no remotes'."""
        with open(self.storage.remotes_path(self.tmp_dir), 'w') as f:
            f.write('{not json')
        with pytest.raises(Vault__Remotes_Unreadable_Error, match='exists but cannot be read'):
            self.manager.list_remotes(self.tmp_dir)
        with pytest.raises(Vault__Remotes_Unreadable_Error):
            self.manager.add_remote(self.tmp_dir, 'origin', 'https://api.example.com', 'aa11bb22')
