"""Fixed in 0.21.0 — a vault's own secrets must never become vault content (review d3b8eef N1, L4).

`vault uninit` left <vault-id>__<ts>__uninit.zip (plaintext vault key, and since
482c11f the signing .pem) in the working folder under a name nothing protected, so a
plain `sgit commit` after `init --restore` committed it. A hard link to the vault key
was committed too: the link has its own name.

Threat model: TM-F11.
"""
import io
import os
import shutil
import zipfile

import pytest

from sgit_ai.core.Vault__Errors                 import Vault__Secret_In_Commit_Error
from sgit_ai.storage.Vault__Storage             import Vault__Storage
from tests._helpers.vault_test_env              import Vault__Test_Env


class Test_Fixed__Secrets_In_Commits:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'readme.md': 'hello'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s     = self._env.restore()
        self.vault = self.s.vault_dir
        self.sync  = self.s.sync

    def teardown_method(self):
        self.s.cleanup()

    def _committed_paths(self):
        return set(self.sync._get_head_flat_map(self.vault)[0])

    def _vault_key(self):
        with open(Vault__Storage().vault_key_path(self.vault)) as f:
            return f.read().strip()

    def _uninit_and_restore(self):
        result = self.sync.uninit(self.vault)
        self.sync.restore_from_backup(result['backup_path'], self.vault)
        return result['backup_path']

    def test_uninit_backup_has_the_protected_name(self):
        backup = self.sync.uninit(self.vault)['backup_path']
        assert os.path.basename(backup).startswith('.vault__')
        assert os.path.dirname(os.path.abspath(backup)) == os.path.abspath(self.vault)

    def test_commit_after_restore_does_not_commit_the_backup(self):
        self._uninit_and_restore()
        with open(os.path.join(self.vault, 'new.md'), 'w') as f:
            f.write('after restore')
        self.sync.commit(self.vault, message='after restore')
        assert self._committed_paths() == {'readme.md', 'new.md'}           # no zip, no sidecars

    def test_a_0_20_0_named_backup_is_not_committed_either(self):
        backup = self._uninit_and_restore()
        legacy = os.path.join(self.vault, os.path.basename(backup)[len('.vault__'):])   # <id>__<ts>__uninit.zip
        shutil.move(backup, legacy)
        for suffix in ('.sha256', '.manifest.json'):
            shutil.move(backup + suffix, legacy + suffix)
        with open(os.path.join(self.vault, 'new.md'), 'w') as f:
            f.write('x')
        self.sync.commit(self.vault, message='x')
        assert self._committed_paths() == {'readme.md', 'new.md'}

    def test_a_renamed_backup_is_refused_by_content(self):
        backup = self._uninit_and_restore()
        shutil.copy(backup, os.path.join(self.vault, 'handover.zip'))
        with pytest.raises(Vault__Secret_In_Commit_Error, match='handover.zip'):
            self.sync.commit(self.vault, message='oops')
        assert self._committed_paths() == {'readme.md'}

    def test_a_zip_holding_a_signing_key_is_refused(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('.sg_vault/local/abc.pem', '-----BEGIN PRIVATE KEY-----')
        with open(os.path.join(self.vault, 'keys.zip'), 'wb') as f:
            f.write(buf.getvalue())
        with pytest.raises(Vault__Secret_In_Commit_Error):
            self.sync.commit(self.vault, message='oops')

    def test_an_ordinary_zip_is_committed(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('docs/token', 'not a vault secret')                 # a name, not this vault's local/
        with open(os.path.join(self.vault, 'docs.zip'), 'wb') as f:
            f.write(buf.getvalue())
        self.sync.commit(self.vault, message='docs')
        assert 'docs.zip' in self._committed_paths()

    def test_write_file_refuses_a_backup_zip(self):
        backup = self._uninit_and_restore()
        with open(backup, 'rb') as f:
            content = f.read()
        with pytest.raises(Vault__Secret_In_Commit_Error):
            self.sync.write_file(self.vault, 'backup.zip', content)

    def test_a_hard_link_to_the_vault_key_is_refused(self):                 # L4
        os.link(Vault__Storage().vault_key_path(self.vault), os.path.join(self.vault, 'notes.txt'))
        with pytest.raises(Vault__Secret_In_Commit_Error, match='hard link'):
            self.sync.commit(self.vault, message='oops')
        assert self._committed_paths() == {'readme.md'}

    def test_restore_takes_only_what_a_backup_writes(self):
        backup = self.sync.uninit(self.vault)['backup_path']
        with zipfile.ZipFile(backup, 'a') as zf:                            # a doctored backup
            zf.writestr('local/base_url', 'https://attacker.example')
            zf.writestr('local/token', 'planted')
            zf.writestr('local/remotes.json', '{"origin": "https://attacker.example"}')
        self.sync.restore_from_backup(backup, self.vault)
        local = os.path.join(self.vault, '.sg_vault', 'local')
        assert not os.path.exists(os.path.join(local, 'base_url'))
        assert not os.path.exists(os.path.join(local, 'token'))
        assert not os.path.exists(os.path.join(local, 'remotes.json'))
        assert os.path.isfile(os.path.join(local, 'config.json'))


class Test_Fixed__Restore_Finds_Both_Names:

    def test_init_restore_finds_a_0_20_0_named_backup(self, tmp_path, monkeypatch, capsys):
        from types import SimpleNamespace
        from sgit_ai.cli.CLI__Vault import CLI__Vault
        env = Vault__Test_Env()
        env.setup_single_vault(files={'a.md': 'a'})
        s = env.restore()
        try:
            backup = s.sync.uninit(s.vault_dir)['backup_path']
            legacy = os.path.join(s.vault_dir, os.path.basename(backup)[len('.vault__'):])
            shutil.move(backup, legacy)
            monkeypatch.setattr('sgit_ai.cli.CLI__Input.CLI__Input.prompt', lambda self, q: 'y')
            CLI__Vault().cmd_init(SimpleNamespace(directory=s.vault_dir, restore=True, existing=False,
                                                  vault_key=None, token=None, base_url=None))
            assert 'Vault restored from backup.' in capsys.readouterr().out
            assert os.path.isdir(os.path.join(s.vault_dir, '.sg_vault'))
        finally:
            s.cleanup()
            env.cleanup_snapshot()
