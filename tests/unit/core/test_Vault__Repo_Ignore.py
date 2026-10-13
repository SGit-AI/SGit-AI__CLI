"""Tests for Vault__Repo_Ignore — the canonical repo-side .gitignore set that keeps key
material (local/, backups/, an in-flight .sg_vault_new/) out of git in the one-repo pattern."""
import os
import shutil
import tempfile

from sgit_ai.core.Vault__Repo_Ignore import CANONICAL_REPO_GITIGNORE, Vault__Repo_Ignore


class Test_Vault__Repo_Ignore:

    def setup_method(self):
        self.tmp    = tempfile.mkdtemp()
        self.ignore = Vault__Repo_Ignore()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def gitignore(self) -> str:
        path = os.path.join(self.tmp, '.gitignore')
        if not os.path.isfile(path):
            return None
        with open(path) as f:
            return f.read()

    def write_gitignore(self, content: str) -> None:
        with open(os.path.join(self.tmp, '.gitignore'), 'w') as f:
            f.write(content)

    # ── the canonical set ───────────────────────────────────────────────
    def test_canonical_set_is_exactly_the_three_key_material_paths(self):
        """The set is literal and ordered: local/ secrets, backup zips, the move-in-flight store."""
        assert CANONICAL_REPO_GITIGNORE == ('.sg_vault/local/', '.sg_vault/backups/', '.sg_vault_new/')

    # ── is_git_work_tree ────────────────────────────────────────────────
    def test_directory_without_git_anywhere_above_is_not_a_work_tree(self):
        """No .git/ in the directory or any ancestor up to the filesystem root: False."""
        assert self.ignore.is_git_work_tree(self.tmp) is False

    def test_git_dir_in_the_directory_itself(self):
        """A .git/ directory right there makes it a work tree."""
        os.makedirs(os.path.join(self.tmp, '.git'))
        assert self.ignore.is_git_work_tree(self.tmp) is True

    def test_git_dir_in_an_ancestor_counts_for_a_nested_vault(self):
        """A vault folder nested inside a git repo is inside that repo's work tree."""
        os.makedirs(os.path.join(self.tmp, '.git'))
        nested = os.path.join(self.tmp, 'a', 'b', 'vault')
        os.makedirs(nested)
        assert self.ignore.is_git_work_tree(nested) is True

    def test_a_git_file_is_not_a_git_dir(self):
        """Only a .git DIRECTORY counts: a .git file (git worktree / submodule pointer) is ignored."""
        with open(os.path.join(self.tmp, '.git'), 'w') as f:
            f.write('gitdir: /elsewhere\n')
        assert self.ignore.is_git_work_tree(self.tmp) is False

    def test_relative_path_is_resolved_against_cwd(self, monkeypatch):
        """'.' is made absolute before the walk, so a relative directory works."""
        os.makedirs(os.path.join(self.tmp, '.git'))
        monkeypatch.chdir(self.tmp)
        assert self.ignore.is_git_work_tree('.') is True

    # ── missing_lines ───────────────────────────────────────────────────
    def test_no_gitignore_means_every_line_is_missing(self):
        """Without a .gitignore all three canonical lines are reported, in canonical order."""
        assert self.ignore.missing_lines(self.tmp) == list(CANONICAL_REPO_GITIGNORE)

    def test_fully_covered_gitignore_has_nothing_missing(self):
        self.write_gitignore('\n'.join(CANONICAL_REPO_GITIGNORE) + '\n')
        assert self.ignore.missing_lines(self.tmp) == []

    def test_trailing_slash_and_surrounding_whitespace_do_not_matter(self):
        """'.sg_vault/local' (no slash) and padded lines count as present."""
        self.write_gitignore('  .sg_vault/local  \n.sg_vault/backups\n\t.sg_vault_new\n')
        assert self.ignore.missing_lines(self.tmp) == []

    def test_only_local_is_insufficient_and_the_other_two_are_reported(self):
        """The tabletop-10 .gitignore (`.sg_vault/local/` alone) leaves backups/ and the
        move store exposed: both are reported, in canonical order."""
        self.write_gitignore('node_modules/\n.sg_vault/local/\n')
        assert self.ignore.missing_lines(self.tmp) == ['.sg_vault/backups/', '.sg_vault_new/']

    def test_a_broader_rule_is_not_recognised(self):
        """Matching is literal: `.sg_vault/` (which would cover everything) is NOT accepted as
        covering the three canonical lines."""
        self.write_gitignore('.sg_vault/\n')
        assert self.ignore.missing_lines(self.tmp) == list(CANONICAL_REPO_GITIGNORE)

    # ── ensure ──────────────────────────────────────────────────────────
    def test_ensure_creates_gitignore_with_header_and_all_lines(self):
        """No .gitignore: one is created with the sgit header followed by the canonical set."""
        added = self.ignore.ensure(self.tmp)
        assert added == list(CANONICAL_REPO_GITIGNORE)
        assert self.gitignore() == ('# sgit: key material must never land in git (canonical set)\n'
                                    '.sg_vault/local/\n.sg_vault/backups/\n.sg_vault_new/\n')
        assert self.ignore.missing_lines(self.tmp) == []

    def test_ensure_appends_only_the_missing_lines_and_keeps_user_rules(self):
        """Existing rules are untouched; only what is missing is appended after the header."""
        self.write_gitignore('*.pyc\n.sg_vault/local/\n')
        added = self.ignore.ensure(self.tmp)
        assert added == ['.sg_vault/backups/', '.sg_vault_new/']
        assert self.gitignore() == ('*.pyc\n.sg_vault/local/\n'
                                    '# sgit: key material must never land in git (canonical set)\n'
                                    '.sg_vault/backups/\n.sg_vault_new/\n')

    def test_ensure_adds_a_newline_when_the_file_does_not_end_with_one(self):
        """A .gitignore whose last line has no newline gets one before the header, so the
        header never glues onto the user's last rule."""
        self.write_gitignore('*.pyc')
        self.ignore.ensure(self.tmp)
        assert self.gitignore().startswith('*.pyc\n# sgit: key material')

    def test_ensure_on_an_empty_file_adds_no_leading_blank_line(self):
        self.write_gitignore('')
        self.ignore.ensure(self.tmp)
        assert self.gitignore().startswith('# sgit: key material')

    def test_ensure_is_idempotent(self):
        """A second ensure adds nothing and leaves the file byte-identical."""
        self.ignore.ensure(self.tmp)
        before = self.gitignore()
        assert self.ignore.ensure(self.tmp) == []
        assert self.gitignore() == before

    def test_ensure_when_covered_does_not_create_or_touch_the_file(self):
        """Fully covered: returns [] and the file's bytes are unchanged (no header appended)."""
        content = '\n'.join(CANONICAL_REPO_GITIGNORE) + '\n'
        self.write_gitignore(content)
        assert self.ignore.ensure(self.tmp) == []
        assert self.gitignore() == content
