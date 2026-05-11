"""End-to-end test: dotfiles commit → push → clone round-trip using in-memory API.

This is the central correctness proof for the dotfile-tracking change:
  - Unknown dotfiles (.editorconfig, .claude/, .github/) are committed and survive
    a full push → clone cycle.
  - Always-ignored files (.env, id_rsa) are never committed, never cloned.
  - .env.* secrets are excluded; .env.example template is included.
  - .gitignore patterns are respected across the full cycle.
"""
import os
import shutil
import tempfile

from sgit_ai.core.Vault__Sync                        import Vault__Sync
from sgit_ai.crypto.Vault__Crypto                    import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory       import Vault__API__In_Memory


def _sync():
    return Vault__Sync(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())


def _write(directory: str, rel_path: str, content: str = 'x'):
    full = os.path.join(directory, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as f:
        f.write(content)


class Test_Vault__Dotfile__Roundtrip:
    """Full commit → push → clone cycle with dotfiles."""

    def setup_method(self):
        self.tmp    = tempfile.mkdtemp()
        self.src    = os.path.join(self.tmp, 'src')
        self.dst    = os.path.join(self.tmp, 'dst')
        self.sync   = _sync()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _init_and_commit(self, files: dict, gitignore: str = '') -> str:
        result = self.sync.init(self.src)
        vault_key = result['vault_key']
        if gitignore:
            _write(self.src, '.gitignore', gitignore)
        for rel_path, content in files.items():
            _write(self.src, rel_path, content)
        self.sync.commit(self.src, message='test commit')
        self.sync.push(self.src)
        return vault_key

    def _clone_files(self, vault_key: str) -> set:
        self.sync.clone(vault_key, self.dst)
        result = set()
        for root, dirs, files in os.walk(self.dst):
            dirs[:] = [d for d in dirs if d != '.sg_vault']
            for f in files:
                result.add(os.path.relpath(os.path.join(root, f), self.dst).replace(os.sep, '/'))
        return result

    # 1. Unknown dotfiles survive the full cycle
    def test_editorconfig_tracked_through_commit_push_clone(self):
        vault_key = self._init_and_commit({
            'app.py'       : 'print("hi")',
            '.editorconfig': '[*]\nindent_size = 4\n',
        })
        cloned = self._clone_files(vault_key)
        assert 'app.py'        in cloned
        assert '.editorconfig' in cloned

    # 2. Unknown dotdirs survive the full cycle
    def test_dotdir_tracked_through_commit_push_clone(self):
        vault_key = self._init_and_commit({
            'app.py'          : 'code',
            '.claude/notes.md': '# notes',
            '.github/workflows/ci.yml': 'on: push',
        })
        cloned = self._clone_files(vault_key)
        assert '.claude/notes.md'            in cloned
        assert '.github/workflows/ci.yml'    in cloned
        assert 'app.py'                      in cloned

    # 3. ALWAYS_IGNORED_FILES are never committed
    def test_env_secret_never_committed(self):
        vault_key = self._init_and_commit({
            'app.py': 'code',
            '.env'  : 'DB_PASS=secret',
        })
        cloned = self._clone_files(vault_key)
        assert 'app.py' in cloned
        assert '.env'   not in cloned

    # 4. env-secret glob: .env.staging excluded, .env.example included
    def test_env_glob_secret_excluded_template_included(self):
        vault_key = self._init_and_commit({
            'app.py'       : 'code',
            '.env.staging' : 'SECRET=x',
            '.env.example' : 'SECRET=change_me',
        })
        cloned = self._clone_files(vault_key)
        assert 'app.py'        in cloned
        assert '.env.example'  in cloned
        assert '.env.staging'  not in cloned

    # 5. SSH private key never committed
    def test_ssh_key_never_committed(self):
        vault_key = self._init_and_commit({
            'README.md': 'docs',
            'id_rsa'   : '-----BEGIN RSA PRIVATE KEY-----',
        })
        cloned = self._clone_files(vault_key)
        assert 'README.md' in cloned
        assert 'id_rsa'    not in cloned

    # 6. .gitignore pattern respected: matched file not committed
    def test_gitignore_pattern_excludes_from_commit(self):
        vault_key = self._init_and_commit(
            files     = {'app.py': 'code', 'build/output.js': 'built'},
            gitignore = 'build/\n',
        )
        cloned = self._clone_files(vault_key)
        assert 'app.py'          in cloned
        assert 'build/output.js' not in cloned

    # 7. dotfile explicitly gitignored is excluded
    def test_gitignore_can_exclude_dotfile(self):
        vault_key = self._init_and_commit(
            files     = {'app.py': 'code', '.devcontainer/devcontainer.json': '{}'},
            gitignore = '.devcontainer/\n',
        )
        cloned = self._clone_files(vault_key)
        assert 'app.py' in cloned
        assert '.devcontainer/devcontainer.json' not in cloned

    # 8. ALWAYS_IGNORED_DIRS are never committed
    def test_node_modules_never_committed(self):
        vault_key = self._init_and_commit({
            'app.js'               : 'code',
            'node_modules/pkg/index.js': 'module',
        })
        cloned = self._clone_files(vault_key)
        assert 'app.js'                    in cloned
        assert 'node_modules/pkg/index.js' not in cloned

    # 9. status is clean after clone (no uncommitted dotfiles appear as untracked)
    def test_status_clean_after_clone(self):
        vault_key = self._init_and_commit({
            'app.py'         : 'code',
            '.editorconfig'  : 'root=true',
            '.claude/notes.md': '# hi',
        })
        self.sync.clone(vault_key, self.dst)
        status = self.sync.status(self.dst)
        assert status.get('clean') is True, f'expected clean status after clone, got: {status}'

    # 10. .gitignore itself is committed and appears in clone
    def test_gitignore_file_itself_is_tracked(self):
        vault_key = self._init_and_commit(
            files     = {'app.py': 'code'},
            gitignore = 'build/\n',
        )
        cloned = self._clone_files(vault_key)
        assert '.gitignore' in cloned
