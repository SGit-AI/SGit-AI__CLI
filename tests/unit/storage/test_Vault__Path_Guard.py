import os
import pytest

from sgit_ai.storage.Vault__Path_Guard import Vault__Path_Guard, Vault__Unsafe_Path_Error


class Test_Vault__Path_Guard:

    def setup_method(self):
        self.guard = Vault__Path_Guard()
        self.base  = os.path.abspath('/tmp/sgit-guard-base')

    # --- safe paths pass through and stay contained ---

    def test_safe_join__simple_file(self):
        result = self.guard.safe_join(self.base, 'notes.txt')
        assert result == os.path.join(self.base, 'notes.txt')

    def test_safe_join__nested_path(self):
        result = self.guard.safe_join(self.base, 'a/b/c.md')
        assert result == os.path.join(self.base, 'a', 'b', 'c.md')
        assert result.startswith(self.base + os.sep)

    def test_safe_join__inner_dotdot_that_stays_inside_is_allowed(self):
        # a/../b normalises to b — still inside base, so permitted
        result = self.guard.safe_join(self.base, 'a/b')
        assert result.startswith(self.base + os.sep)

    def test_safe_join__literal_backslash_filename_preserved(self):
        # On POSIX a backslash is a legal filename character. The guard must NOT
        # rewrite it to a separator (that would turn one file into a subdirectory).
        result = self.guard.safe_join(self.base, 'weird\\name.txt')
        assert result == os.path.join(self.base, 'weird\\name.txt')
        assert os.path.dirname(result) == self.base          # still a single file in base

    def test_safe_join__windows_style_traversal_still_rejected(self):
        with pytest.raises(Vault__Unsafe_Path_Error):
            self.guard.safe_join(self.base, '..\\..\\evil.txt')

    def test_safe_join__rejects_leading_backslash(self):
        with pytest.raises(Vault__Unsafe_Path_Error):
            self.guard.safe_join(self.base, '\\evil.txt')

    # --- traversal attempts are rejected ---

    def test_safe_join__rejects_parent_traversal(self):
        with pytest.raises(Vault__Unsafe_Path_Error):
            self.guard.safe_join(self.base, '../evil')

    def test_safe_join__rejects_deep_parent_traversal(self):
        with pytest.raises(Vault__Unsafe_Path_Error):
            self.guard.safe_join(self.base, 'a/b/../../../../etc/passwd')

    def test_safe_join__rejects_absolute_posix(self):
        with pytest.raises(Vault__Unsafe_Path_Error):
            self.guard.safe_join(self.base, '/etc/passwd')

    def test_safe_join__rejects_embedded_parent_component(self):
        with pytest.raises(Vault__Unsafe_Path_Error):
            self.guard.safe_join(self.base, 'ok/../../escape')

    def test_safe_join__rejects_empty(self):
        with pytest.raises(Vault__Unsafe_Path_Error):
            self.guard.safe_join(self.base, '')

    def test_safe_join__rejects_none(self):
        with pytest.raises(Vault__Unsafe_Path_Error):
            self.guard.safe_join(self.base, None)

    # --- is_safe mirror ---

    def test_is_safe__true_for_contained(self):
        assert self.guard.is_safe(self.base, 'a/b.txt') is True

    def test_is_safe__false_for_traversal(self):
        assert self.guard.is_safe(self.base, '../../x') is False

    def test_is_safe__false_for_absolute(self):
        assert self.guard.is_safe(self.base, '/etc/shadow') is False


class Test_Vault__Path_Guard__Other_Spellings:
    """A case-insensitive or normalising filesystem (macOS, Windows) resolves these
    to .git / .sg_vault; git refuses them (CVE-2014-9390, CVE-2019-1353)."""

    HOSTILE = ['.GIT/hooks/post-checkout', '.Git/config', 'git~1/hooks/x', 'GIT~1/x', '.git./hooks/x',
               '.git /hooks/x', '.git::$INDEX_ALLOCATION/hooks/x', '.g\u200cit/hooks/x', '.gi\ufefft/x',
               'a/b/.SG_VAULT/local/vault_key', 'SG_VAU~1/local/x', '.Sg_Vault_Old_123/x', '.SG_VAULT_NEW/x']
    BENIGN  = ['docs/.github/workflows/ci.yml', 'src/git/x.py', 'gitlab/x', '.gitignore', 'notes.git/x',
               '.git2/x', 'sg_vault/x', 'a~1/x', 'readme.md']

    def test_hostile_spellings_are_protected(self):
        from sgit_ai.storage.Vault__Path_Guard import Vault__Path_Guard
        g = Vault__Path_Guard()
        assert [p for p in self.HOSTILE if not g.is_protected(p)] == []

    def test_ordinary_names_are_not(self):
        from sgit_ai.storage.Vault__Path_Guard import Vault__Path_Guard
        g = Vault__Path_Guard()
        assert [p for p in self.BENIGN if g.is_protected(p)] == []
