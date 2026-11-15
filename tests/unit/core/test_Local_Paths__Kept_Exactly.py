"""Local paths are kept exactly (issue #18: on Windows every clone failed).

The local workspace, vault and store directories were held in Safe_Str__File_Path / Safe_Str__Vault_Path /
Safe_Str__Base_URL, sanitisers that rewrite every character outside [a-zA-Z0-9/\\_.- ] to `_`. A Windows temp
path `C:\\Users\\…\\Temp\\sgit-clone-…` became the relative `C_\\Users\\…`, so every clone failed; and on any OS a
folder with `( ) ~ @ +` or a non-ASCII letter in its absolute path broke (iCloud's `com~apple~CloudDocs`,
`GoogleDrive-me@gmail.com`, `/home/josé`). They are now Safe_Str__Host_Path: any printable text, refused if it
holds a control character, never rewritten.

Linux allows `:` in a file name, so the Windows failure reproduces here with a temp folder named like a drive."""
import os
import re
import shutil
import tempfile

import pytest

from sgit_ai.cli.CLI__Main                          import CLI__Main
from sgit_ai.core.Vault__Sync                       import Vault__Sync
from sgit_ai.crypto.Vault__Crypto                   import Vault__Crypto
from sgit_ai.network.api.Vault__API__Auto           import Vault__API__Auto
from sgit_ai.network.api.Vault__API__In_Memory      import Vault__API__In_Memory
from sgit_ai.network.api.Vault__API__Static         import Vault__API__Static
from sgit_ai.safe_types.Safe_Str__Host_Path         import Safe_Str__Host_Path
from sgit_ai.schemas.workflow.clone.Schema__Clone__State import Schema__Clone__State
from sgit_ai.secrets.Secrets__Store                 import Secrets__Store
from sgit_ai.storage.Vault__Object_Store            import Vault__Object_Store
from sgit_ai.workflow.Workflow__Workspace           import Workflow__Workspace
from tests._helpers.vault_test_env                  import TEST_VAULT_KEY

WINDOWS_TEMP = 'C:\\Users\\Ana María\\AppData\\Local\\Temp\\sgit-clone-a27e1c91'
ODD_NAME     = 'C:x (y)~é@+'                                         # a drive-like colon and the other casualties


class Test_Local_Paths__Kept_Exactly:

    @pytest.mark.parametrize('path', [WINDOWS_TEMP, '/Users/me/Library/Mobile Documents/com~apple~CloudDocs/vault',
                                      '/home/josé/GoogleDrive-me@gmail.com/v (1)', 'D:\\a\\b'])
    def test_every_holder_of_a_local_path_keeps_it(self, path):
        assert str(Safe_Str__Host_Path(path))                                  == path
        assert str(Schema__Clone__State(directory=path, sg_dir=path).directory) == path
        assert str(Schema__Clone__State(directory=path, sg_dir=path).sg_dir)    == path
        assert str(Workflow__Workspace(workspace_dir=path).workspace_dir)       == path
        assert str(Vault__Object_Store(vault_path=path).vault_path)             == path
        assert str(Secrets__Store(store_path=path).store_path)                  == path
        assert str(Vault__API__Static(base_url=path).base_url)                  == path
        assert str(Vault__API__Auto(base_url=path).base_url)                    == path

    def test_a_control_character_is_refused_not_rewritten(self):
        with pytest.raises(ValueError):
            Safe_Str__Host_Path('C:\\x\ny')

    def test_no_local_path_field_uses_a_rewriting_type(self):
        """A guard against a new field going back to a sanitiser: local-path fields by name."""
        root     = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'sgit_ai')
        pattern  = re.compile(r'^\s*(directory|sg_dir|workspace_dir|vault_path|temp_vault_dir|backup_zip_path|output_dir|'
                              r'zip_path|zip_source|destination|local_path|keyring_dir|keys_dir|store_path|root_path|'
                              r'cache_root|root_dir|bare_dir|data_dir)\s*:\s*(Safe_Str__File_Path|Safe_Str__Vault_Path|'
                              r'Safe_Str\b|Safe_Str__Base_URL)', re.M)
        found = []
        for folder, _, files in os.walk(root):
            for name in files:
                if name.endswith('.py'):
                    path = os.path.join(folder, name)
                    with open(path, encoding='utf-8') as f:
                        found += [f'{os.path.relpath(path, root)}: {m.group(0).strip()}' for m in pattern.finditer(f.read())]
        assert found == []


class Test_Local_Paths__End_To_End:
    """The issue's clone, and the rest of the round trip, with the temp folder and the vault under a folder whose
    name carries a colon, parentheses, a tilde, `@`, `+` and an accent."""

    def setup_method(self):
        self.root = tempfile.mkdtemp()
        self.odd  = os.path.join(self.root, ODD_NAME)
        os.makedirs(self.odd)

    def teardown_method(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def round_trip(self, base: str) -> list:
        sync = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())
        a, b = os.path.join(base, 'a'), os.path.join(base, 'b')
        key  = sync.init(a, vault_key=TEST_VAULT_KEY)['vault_key']
        with open(os.path.join(a, 'f.txt'), 'w') as f:
            f.write('x\n')
        sync.commit(a, message='m')
        sync.push(a)
        sync.clone(key, b)
        with open(os.path.join(a, 'f.txt'), 'w') as f:
            f.write('y\n')
        sync.commit(a, message='m2')
        sync.push(a)
        sync.pull(b)
        with open(os.path.join(b, 'f.txt')) as f:
            return [f.read()]

    def test_the_issues_clone_with_the_temp_folder_on_a_drive_like_path(self, monkeypatch):
        monkeypatch.setattr(tempfile, 'tempdir', self.odd)                    # where mkdtemp puts the workspace
        plain = os.path.join(self.root, 'plain')
        os.makedirs(plain)
        assert self.round_trip(plain) == ['y\n']

    def test_a_vault_whose_own_path_has_those_characters(self):
        assert self.round_trip(self.odd) == ['y\n']                          # push used to fail: "branch moved"

    def test_write_also_splits_at_the_first_colon_so_a_drive_letter_survives(self, capsys):
        """The issue's side note: `--also VAULT_PATH:LOCAL_FILE` splits at the first `:`, which comes after the
        vault path, so a local path with a drive colon is kept."""
        sync  = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())
        vault = os.path.join(self.root, 'v')
        sync.init(vault, vault_key=TEST_VAULT_KEY)
        local = os.path.join(self.odd, 'C:extra.txt')
        with open(local, 'w') as f:
            f.write('extra\n')
        source = os.path.join(self.root, 'main.txt')
        with open(source, 'w') as f:
            f.write('main\n')
        here = os.getcwd()
        os.chdir(vault)
        try:
            CLI__Main().run(['--base-url', 'http://127.0.0.1:9', 'write', 'main.txt', '--file', source,
                             '--also', f'docs/extra.txt:{local}'])
        except SystemExit as e:
            assert not e.code
        finally:
            os.chdir(here)
        with open(os.path.join(vault, 'docs', 'extra.txt')) as f:
            assert f.read() == 'extra\n'
