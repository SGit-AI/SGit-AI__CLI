import os
import tempfile
import shutil
from   sgit_ai.core.Vault__Ignore import (Vault__Ignore, ALWAYS_IGNORED_DIRS,
                                           ALWAYS_IGNORED_DIR_PREFIXES,
                                           ALWAYS_IGNORED_FILES, ENV_TEMPLATE_ALLOWLIST)


class Test_Vault__Ignore__Always_Ignored:

    def test_always_ignored__git(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_dir('.git') is True

    def test_always_ignored__node_modules(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_dir('node_modules') is True

    def test_always_ignored__pycache(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_dir('__pycache__') is True

    def test_always_ignored__sg_vault(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_dir('.sg_vault') is True

    def test_always_ignored__venv(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_dir('.venv') is True

    def test_always_ignored__nested_node_modules(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_dir('src/node_modules') is True

    def test_always_ignored__nested_pycache(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_dir('pkg/__pycache__') is True

    def test_not_ignored__regular_dir(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_dir('src') is False
        assert ignore.should_ignore_dir('docs') is False

    def test_always_ignored__all_entries(self):
        ignore = Vault__Ignore()
        expected = {'.sg_vault', '.sg_vault_new', '.git', 'node_modules', '__pycache__',
                    '.venv', '.tox', '.nox', '.eggs', '.mypy_cache',
                    '.pytest_cache', '.ruff_cache',
                    '.idea', '.vscode', '.cache', '.parcel-cache',
                    '.next', '.nuxt', '.terraform', '.svelte-kit',
                    '.turbo', '.DS_Store', '.AppleDouble'}
        assert ALWAYS_IGNORED_DIRS == expected

    def test_always_ignored__idea(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_dir('.idea') is True

    def test_always_ignored__next(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_dir('.next') is True


class Test_Vault__Ignore__Dotfiles:

    def test_unknown_dotfile_is_tracked(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_file('.hidden') is False

    def test_env_file_in_subdir_still_ignored(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_file('src/.env') is True

    def test_vscode_in_always_ignored_dirs(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_dir('.vscode') is True

    def test_regular_file_not_ignored(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_file('readme.md') is False


class Test_Vault__Ignore__DotfileTracking:

    def test_dotfile_not_in_always_ignored_files_is_tracked(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_file('.editorconfig')      is False
        assert ignore.should_ignore_file('.github/workflows/ci.yml') is False

    def test_dotdir_not_in_always_ignored_dirs_is_tracked(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_dir('.claude')       is False
        assert ignore.should_ignore_dir('.devcontainer') is False

    def test_always_ignored_dirs_excluded(self):
        ignore = Vault__Ignore()
        for name in ['.idea', '.vscode', '.next', '.sg_vault', '.git', 'node_modules']:
            assert ignore.should_ignore_dir(name) is True, f'{name} should be ignored'

    def test_always_ignored_files_excluded(self):
        ignore = Vault__Ignore()
        for name in ['.env', 'id_rsa', '.netrc', '.npmrc']:
            assert ignore.should_ignore_file(name) is True, f'{name} should be ignored'

    def test_gitignore_pattern_overrides_default_track(self):
        tmp = tempfile.mkdtemp()
        try:
            with open(os.path.join(tmp, '.gitignore'), 'w') as f:
                f.write('.claude/\n')
            ignore_with = Vault__Ignore().load_gitignore(tmp)
            assert ignore_with.should_ignore_dir('.claude') is True

            ignore_without = Vault__Ignore()
            assert ignore_without.should_ignore_dir('.claude') is False
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_gitignore_negation_includes_specific_dotfile(self):
        tmp = tempfile.mkdtemp()
        try:
            with open(os.path.join(tmp, '.gitignore'), 'w') as f:
                f.write('.env*\n!.env.example\n')
            ignore = Vault__Ignore().load_gitignore(tmp)
            assert ignore.should_ignore_file('.env')         is True
            assert ignore.should_ignore_file('.env.example') is False

            # template allowlist also works without any gitignore
            ignore_bare = Vault__Ignore()
            assert ignore_bare.should_ignore_file('.env.example') is False
            assert ignore_bare.should_ignore_file('.env.sample')  is False
            assert ignore_bare.should_ignore_file('.env.template') is False
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_env_secret_glob_covers_staging(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_file('.env.staging') is True
        assert ignore.should_ignore_file('.env.test')    is True
        assert ignore.should_ignore_file('.env.ci')      is True

    def test_env_templates_tracked(self):
        ignore = Vault__Ignore()
        for name in ENV_TEMPLATE_ALLOWLIST:
            assert ignore.should_ignore_file(name) is False, f'{name} should be tracked'

    def test_no_blanket_dotfile_exclusion(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_file('.fooBar')  is False
        assert ignore.should_ignore_file('.bashrc')  is False
        assert ignore.should_ignore_dir('.myconfig') is False

    def test_sg_vault_old_prefix_ignored(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_dir('.sg_vault_old_1234567890') is True
        assert ignore.should_ignore_dir('.sg_vault_old_')           is True

    def test_sg_vault_new_ignored(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_dir('.sg_vault_new') is True

    def test_prefix_set_exported(self):
        assert '.sg_vault_old_' in ALWAYS_IGNORED_DIR_PREFIXES

    def test_explain_parent_dir_ignored_by_gitignore(self):
        tmp = tempfile.mkdtemp()
        try:
            with open(os.path.join(tmp, '.gitignore'), 'w') as f:
                f.write('dist/\n')
            ignore = Vault__Ignore().load_gitignore(tmp)
            reason = ignore.explain('dist/foo.js', is_dir=False)
            assert reason.is_ignored   is True
            assert reason.reason_code  == 'gitignore_pattern'
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_explain_tracked_file_returns_tracked(self):
        ignore = Vault__Ignore()
        reason = ignore.explain('.editorconfig', is_dir=False)
        assert reason.is_ignored  is False
        assert reason.reason_code == 'tracked'

    def test_explain_always_ignored_file(self):
        ignore = Vault__Ignore()
        reason = ignore.explain('id_rsa', is_dir=False)
        assert reason.is_ignored  is True
        assert reason.reason_code == 'always_ignored_file'

    def test_explain_env_secret_glob(self):
        ignore = Vault__Ignore()
        reason = ignore.explain('.env.staging', is_dir=False)
        assert reason.is_ignored  is True
        assert reason.reason_code == 'env_secret_glob'

    def test_explain_always_ignored_dir(self):
        ignore = Vault__Ignore()
        reason = ignore.explain('.vscode', is_dir=True)
        assert reason.is_ignored  is True
        assert reason.reason_code == 'always_ignored_dir'


class Test_Vault__Ignore__Gitignore_Parsing:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write_gitignore(self, content: str):
        with open(os.path.join(self.tmp_dir, '.gitignore'), 'w') as f:
            f.write(content)

    def test_no_gitignore__no_error(self):
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('anything.txt') is False

    def test_simple_file_pattern(self):
        self._write_gitignore('*.log\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('error.log')   is True
        assert ignore.should_ignore_file('readme.md')    is False

    def test_simple_dir_pattern(self):
        self._write_gitignore('build/\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_dir('build')         is True
        assert ignore.should_ignore_file('build.txt')    is False

    def test_nested_file_match(self):
        self._write_gitignore('*.pyc\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('src/module.pyc') is True

    def test_comment_lines_skipped(self):
        self._write_gitignore('# this is a comment\n*.log\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert len(ignore.patterns) == 1

    def test_blank_lines_skipped(self):
        self._write_gitignore('\n\n*.log\n\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert len(ignore.patterns) == 1

    def test_negation_pattern(self):
        self._write_gitignore('*.log\n!important.log\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('error.log')     is True
        assert ignore.should_ignore_file('important.log') is False

    def test_dir_only_pattern_not_match_file(self):
        self._write_gitignore('dist/\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_dir('dist')      is True
        assert ignore.should_ignore_file('dist')     is False

    def test_anchored_pattern(self):
        self._write_gitignore('/build\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('build')     is True
        assert ignore.should_ignore_dir('build')      is True

    def test_doublestar_prefix(self):
        self._write_gitignore('**/test.txt\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('test.txt')         is True
        assert ignore.should_ignore_file('a/b/test.txt')     is True

    def test_doublestar_suffix(self):
        self._write_gitignore('logs/**\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('logs/a.txt')       is True
        assert ignore.should_ignore_file('logs/sub/b.txt')   is True

    def test_wildcard_in_dir(self):
        self._write_gitignore('*.egg-info/\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_dir('my_pkg.egg-info')   is True

    def test_multiple_patterns(self):
        self._write_gitignore('*.log\n*.tmp\nbuild/\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('error.log')  is True
        assert ignore.should_ignore_file('data.tmp')   is True
        assert ignore.should_ignore_dir('build')       is True
        assert ignore.should_ignore_file('main.py')    is False


class Test_Vault__Ignore__Scan_Integration:
    """Test that Vault__Ignore integrates correctly with _scan_local_directory."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_scan_excludes_node_modules(self):
        from sgit_ai.core.Vault__Sync        import Vault__Sync
        from sgit_ai.crypto.Vault__Crypto     import Vault__Crypto
        from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory

        nm_dir = os.path.join(self.tmp_dir, 'node_modules', 'pkg')
        os.makedirs(nm_dir)
        with open(os.path.join(nm_dir, 'index.js'), 'w') as f:
            f.write('module.exports = {}')
        with open(os.path.join(self.tmp_dir, 'app.js'), 'w') as f:
            f.write('console.log("hello")')

        sync   = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())
        result = sync._scan_local_directory(self.tmp_dir)
        assert 'app.js'                      in result
        assert 'node_modules/pkg/index.js' not in result

    def test_scan_excludes_pycache(self):
        from sgit_ai.core.Vault__Sync        import Vault__Sync
        from sgit_ai.crypto.Vault__Crypto     import Vault__Crypto
        from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory

        cache_dir = os.path.join(self.tmp_dir, '__pycache__')
        os.makedirs(cache_dir)
        with open(os.path.join(cache_dir, 'mod.cpython-311.pyc'), 'w') as f:
            f.write('bytecode')
        with open(os.path.join(self.tmp_dir, 'mod.py'), 'w') as f:
            f.write('print("hi")')

        sync   = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())
        result = sync._scan_local_directory(self.tmp_dir)
        assert 'mod.py'                              in result
        assert '__pycache__/mod.cpython-311.pyc' not in result

    def test_scan_respects_gitignore(self):
        from sgit_ai.core.Vault__Sync        import Vault__Sync
        from sgit_ai.crypto.Vault__Crypto     import Vault__Crypto
        from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory

        with open(os.path.join(self.tmp_dir, '.gitignore'), 'w') as f:
            f.write('*.log\nbuild/\n')
        with open(os.path.join(self.tmp_dir, 'app.py'), 'w') as f:
            f.write('code')
        with open(os.path.join(self.tmp_dir, 'error.log'), 'w') as f:
            f.write('error')
        build_dir = os.path.join(self.tmp_dir, 'build')
        os.makedirs(build_dir)
        with open(os.path.join(build_dir, 'output.js'), 'w') as f:
            f.write('built')

        sync   = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())
        result = sync._scan_local_directory(self.tmp_dir)
        assert 'app.py'           in result
        assert 'error.log'    not in result
        assert 'build/output.js' not in result

    def test_scan_tracks_unknown_dotfiles(self):
        from sgit_ai.core.Vault__Sync        import Vault__Sync
        from sgit_ai.crypto.Vault__Crypto     import Vault__Crypto
        from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory

        with open(os.path.join(self.tmp_dir, '.editorconfig'), 'w') as f:
            f.write('[*]\nindent_size = 4\n')
        claude_dir = os.path.join(self.tmp_dir, '.claude')
        os.makedirs(claude_dir)
        with open(os.path.join(claude_dir, 'notes.md'), 'w') as f:
            f.write('# notes')

        sync   = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())
        result = sync._scan_local_directory(self.tmp_dir)
        assert '.editorconfig'   in result
        assert '.claude/notes.md' in result


class Test_Vault__Ignore__Doublestar_Edge_Cases:
    """Target the uncovered branches in _match_doublestar and _match_anchored."""

    def setup_method(self):
        import tempfile
        self.tmp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write_gitignore(self, content: str):
        with open(os.path.join(self.tmp_dir, '.gitignore'), 'w') as f:
            f.write(content)

    def test_anchored_pattern_with_slash_matches_file(self):
        self._write_gitignore('src/*.py\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('src/main.py') is True

    def test_anchored_pattern_with_slash_no_match(self):
        self._write_gitignore('src/*.py\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('other/main.py') is False

    def test_doublestar_alone_matches_file(self):
        self._write_gitignore('**\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('anything.txt') is True

    def test_doublestar_anchored_matches_all(self):
        self._write_gitignore('/**\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('deep/nested/file.py') is True

    def test_doublestar_prefix_no_match_returns_false(self):
        self._write_gitignore('**/readme.txt\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('other/file.py') is False

    def test_doublestar_prefix_matches_deep(self):
        self._write_gitignore('**/readme.txt\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('a/b/readme.txt') is True

    def test_doublestar_suffix_no_match(self):
        self._write_gitignore('logs/**\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('other/file.txt') is False

    def test_doublestar_suffix_exact_prefix(self):
        self._write_gitignore('logs/**\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_dir('logs') is True

    def test_doublestar_mid_pattern_matches(self):
        self._write_gitignore('src/**/foo.py\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('src/a/b/foo.py') is True

    def test_doublestar_mid_pattern_no_match(self):
        self._write_gitignore('src/**/foo.py\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('other/foo.py') is False

    def test_doublestar_mid_empty_after(self):
        self._write_gitignore('src/**\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('src/foo.py') is True

    def test_parse_line_slash_only_ignored(self):
        self._write_gitignore('/\n*.log\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert len(ignore.patterns) == 1

    def test_match_doublestar_alone_returns_true(self):
        ignore = Vault__Ignore()
        assert ignore._match_doublestar('any/path/file.txt', '**') is True

    def test_match_basename_path_matches_not_name(self):
        ignore = Vault__Ignore()
        result = ignore._match_basename('a/b', 'a*b', is_dir=False)
        assert result is True

    def test_match_anchored_no_match_returns_false(self):
        ignore = Vault__Ignore()
        result = ignore._match_anchored('other/file.txt', 'src/foo.txt', is_dir=False)
        assert result is False

    def test_match_doublestar_empty_after_matches(self):
        ignore = Vault__Ignore()
        result = ignore._match_doublestar('src/anything.txt', 'src**')
        assert result is True

    def test_doublestar_mid_parts_loop_no_match(self):
        self._write_gitignore('src/**/readme.md\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('src/a/b/other.txt') is False
