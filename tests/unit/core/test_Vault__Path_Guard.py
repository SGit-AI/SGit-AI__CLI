import os
import pytest

from sgit_ai.core.Vault__Path_Guard import Vault__Path_Guard
from sgit_ai.core.Vault__Errors     import Vault__Unsafe_Path_Error


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

    def test_safe_join__windows_separators_normalised(self):
        result = self.guard.safe_join(self.base, 'a\\b\\c.txt')
        assert result == os.path.join(self.base, 'a', 'b', 'c.txt')

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
