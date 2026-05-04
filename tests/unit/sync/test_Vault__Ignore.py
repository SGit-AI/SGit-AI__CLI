import os
import tempfile
import shutil
from   sgit_ai.core.Vault__Ignore import Vault__Ignore, ALWAYS_IGNORED_DIRS


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
        expected = {'.sg_vault', '.git', 'node_modules', '__pycache__',
                    '.venv', '.tox', '.nox', '.eggs', '.mypy_cache',
                    '.pytest_cache', '.ruff_cache'}
        assert ALWAYS_IGNORED_DIRS == expected


class Test_Vault__Ignore__Dotfiles:

    def test_dotfile_ignored(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_file('.hidden') is True

    def test_dotfile_in_subdir(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_file('src/.env') is True

    def test_dotdir_ignored(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_dir('.vscode') is True

    def test_regular_file_not_ignored(self):
        ignore = Vault__Ignore()
        assert ignore.should_ignore_file('readme.md') is False


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
        from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory

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
        from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory

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
        from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory

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

    # --- _match_anchored (lines 83-85): anchored pattern with '/' that matches ---

    def test_anchored_pattern_with_slash_matches_file(self):
        """Pattern src/*.py (contains '/') → _match_anchored → fnmatch matches."""
        self._write_gitignore('src/*.py\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('src/main.py') is True

    def test_anchored_pattern_with_slash_no_match(self):
        """Pattern src/*.py does not match other/main.py."""
        self._write_gitignore('src/*.py\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('other/main.py') is False

    # --- _match_doublestar pattern == '**' (line 89): matches everything ---

    def test_doublestar_alone_matches_file(self):
        """Pattern ** (no '/') → _match_basename; fnmatch('x', '**') is True."""
        self._write_gitignore('**\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('anything.txt') is True

    def test_doublestar_anchored_matches_all(self):
        """Pattern /** becomes ** after stripping leading '/'; still matches."""
        self._write_gitignore('/**\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('deep/nested/file.py') is True

    # --- _match_doublestar **/rest — return False path (line 99) ---

    def test_doublestar_prefix_no_match_returns_false(self):
        """**/readme.txt does not match other/file.py."""
        self._write_gitignore('**/readme.txt\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('other/file.py') is False

    def test_doublestar_prefix_matches_deep(self):
        """**/readme.txt matches a/b/readme.txt via parts loop."""
        self._write_gitignore('**/readme.txt\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('a/b/readme.txt') is True

    # --- _match_doublestar prefix/** — return False path (line 104) ---

    def test_doublestar_suffix_no_match(self):
        """logs/** does not match other/file.txt."""
        self._write_gitignore('logs/**\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('other/file.txt') is False

    def test_doublestar_suffix_exact_prefix(self):
        """logs/** matches logs itself (as a dir)."""
        self._write_gitignore('logs/**\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_dir('logs') is True

    # --- _match_doublestar mid-pattern (lines 105-117) ---

    def test_doublestar_mid_pattern_matches(self):
        """src/**/foo.py matches src/a/b/foo.py."""
        self._write_gitignore('src/**/foo.py\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('src/a/b/foo.py') is True

    def test_doublestar_mid_pattern_no_match(self):
        """src/**/foo.py does not match other/foo.py."""
        self._write_gitignore('src/**/foo.py\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('other/foo.py') is False

    def test_doublestar_mid_empty_after(self):
        """src/** where after is empty → matches anything under src/."""
        self._write_gitignore('src/**\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('src/foo.py') is True

    # --- _parse_line: stripped becomes empty after stripping '/' (line 133) ---

    def test_parse_line_slash_only_ignored(self):
        """A line that is just '/' produces no pattern."""
        self._write_gitignore('/\n*.log\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        # '/' line is skipped, only *.log pattern remains
        assert len(ignore.patterns) == 1

    # --- _match_doublestar: line 89 (pattern == '**' → return True directly) ---

    def test_match_doublestar_alone_returns_true(self):
        """Line 89: _match_doublestar called directly with '**' → return True."""
        ignore = Vault__Ignore()
        assert ignore._match_doublestar('any/path/file.txt', '**') is True

    # --- _match_basename: line 77 (return True when rel_path matches but name doesn't) ---

    def test_match_basename_path_matches_not_name(self):
        """Line 77: name doesn't match 'a*b' but full path 'a/b' does."""
        ignore = Vault__Ignore()
        result = ignore._match_basename('a/b', 'a*b', is_dir=False)
        assert result is True

    # --- _match_anchored: line 89 (return False when anchored pattern doesn't match) ---

    def test_match_anchored_no_match_returns_false(self):
        """Line 89: anchored pattern without '**', fnmatch fails → return False."""
        ignore = Vault__Ignore()
        result = ignore._match_anchored('other/file.txt', 'src/foo.txt', is_dir=False)
        assert result is False

    # --- _match_doublestar: line 111 (return True when after is empty) ---

    def test_match_doublestar_empty_after_matches(self):
        """Line 111: pattern 'src**' → before='src', after='' → return True."""
        ignore = Vault__Ignore()
        result = ignore._match_doublestar('src/anything.txt', 'src**')
        assert result is True

    # --- _match_doublestar: line 117 (return False at end of parts loop) ---

    def test_doublestar_mid_parts_loop_no_match(self):
        """Line 117: src/**/readme.md with src/a/b/other.txt → all parts fail."""
        self._write_gitignore('src/**/readme.md\n')
        ignore = Vault__Ignore().load_gitignore(self.tmp_dir)
        assert ignore.should_ignore_file('src/a/b/other.txt') is False
