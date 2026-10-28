"""Vault__Pathspec — which paths `sgit commit <pathspec>` takes (design__03 §5.1)."""
import os

import pytest

from sgit_ai.core.Vault__Errors                  import Vault__Pathspec_Error
from sgit_ai.core.actions.commit.Vault__Pathspec import Vault__Pathspec
from sgit_ai.safe_types.Safe_Str__Pathspec       import Safe_Str__Pathspec

PATHS = {'README.md', 'a.txt', 'docs/guide.md', 'docs/api/ref.md', 'src/app.py', 'src/lib/util.py',
         'src/b.txt', 'ü/naïve.txt', 'trailing .txt'}


class Test_Vault__Pathspec:

    def setup_method(self):
        self.root = os.path.realpath('/tmp') + '/vault-root-x'                 # never touched: paths only

    def match(self, *args, cwd=None):
        spec = Vault__Pathspec().from_args(list(args), cwd or self.root, self.root)
        return spec.match(PATHS)

    def test_literal_file(self):
        assert self.match('a.txt') == ({'a.txt'}, [])

    def test_literal_folder_with_and_without_slash(self):
        assert self.match('docs')[0]  == {'docs/guide.md', 'docs/api/ref.md'}
        assert self.match('docs/')[0] == {'docs/guide.md', 'docs/api/ref.md'}

    def test_a_folder_prefix_is_not_a_name_prefix(self):
        assert self.match('src/li') == (set(), ['src/li'])

    def test_dot_at_the_root_and_in_a_folder(self):
        assert self.match('.')[0] == PATHS
        assert self.match('.', cwd=self.root + '/src')[0] == {'src/app.py', 'src/lib/util.py', 'src/b.txt'}

    def test_star_crosses_slash_as_in_git(self):
        assert self.match('*.md')[0] == {'README.md', 'docs/guide.md', 'docs/api/ref.md'}
        assert self.match('src/*.py')[0] == {'src/app.py', 'src/lib/util.py'}

    def test_question_mark_and_brackets(self):
        assert self.match('?.txt')[0]     == {'a.txt'}
        assert self.match('src/[ab]*')[0] == {'src/app.py', 'src/b.txt'}
        assert self.match('src/[!a]*')[0] == {'src/lib/util.py', 'src/b.txt'}

    def test_globs_are_case_sensitive(self):
        assert self.match('*.MD') == (set(), ['*.MD'])

    def test_relative_to_the_current_folder(self):
        assert self.match('app.py', cwd=self.root + '/src')[0] == {'src/app.py'}
        assert self.match('../a.txt', cwd=self.root + '/src')[0] == {'a.txt'}

    def test_a_cwd_outside_the_vault_means_relative_to_the_root(self):
        assert self.match('a.txt', cwd='/')[0] == {'a.txt'}

    def test_escaping_the_vault_is_refused(self):
        with pytest.raises(Vault__Pathspec_Error, match="'../x' is outside the vault"):
            self.match('../x')
        with pytest.raises(Vault__Pathspec_Error, match='outside the vault'):
            self.match('/etc/passwd')

    def test_absolute_path_inside_the_vault(self):
        assert self.match(self.root + '/src/app.py')[0] == {'src/app.py'}

    def test_unicode_and_trailing_space_names(self):
        assert self.match('ü/naïve.txt')[0] == {'ü/naïve.txt'}
        assert self.match('trailing .txt')[0] == {'trailing .txt'}

    def test_unmatched_patterns_are_named_as_typed(self):
        matched, unmatched = self.match('a.txt', 'zzz', 'nope/*.c')
        assert matched == {'a.txt'} and unmatched == ['zzz', 'nope/*.c']

    def test_safe_str_keeps_glob_characters_and_replaces_control_characters(self):
        assert Safe_Str__Pathspec('src/[ab]*?.py ') == 'src/[ab]*?.py '
        assert '\n' not in Safe_Str__Pathspec('a\nb')

    def test_round_trip(self):
        spec = Vault__Pathspec().from_args(['a.txt', '*.md'], self.root, self.root)
        assert Vault__Pathspec.from_json(spec.json()).json() == spec.json()
