"""Vault__Repo_Ignore — the canonical repo-side .gitignore set (decision 13).

In the one-repo pattern (vault + git in the same work tree) the .gitignore
that matters guards KEY MATERIAL, and it is exactly three lines. `local/`
alone — what tabletop 10 used — is insufficient: one keyed backup plus
`git add -A` commits the write key (the zip carries it as VAULT-KEY).
Asserted literally in the QA suite so weakening it is a failing test.
"""
import os
from osbot_utils.type_safe.Type_Safe import Type_Safe

CANONICAL_REPO_GITIGNORE = (
    '.sg_vault/local/',      # live secrets: vault_key, token, PKI .pem, config
    '.sg_vault/backups/',    # backup zips carry bare/ + local config — and with
                             #   --include-key, the VAULT KEY ITSELF as `VAULT-KEY`
    '.sg_vault_new/',        # a complete second store (incl. its own local/
                             #   secrets) exists here while a vault move is in flight
)


class Vault__Repo_Ignore(Type_Safe):

    def is_git_work_tree(self, directory: str) -> bool:
        current = os.path.abspath(directory)
        while True:
            if os.path.isdir(os.path.join(current, '.git')):
                return True
            parent = os.path.dirname(current)
            if parent == current:
                return False
            current = parent

    def missing_lines(self, directory: str) -> list:
        """Canonical lines absent from directory's .gitignore ([] when covered)."""
        gitignore_path = os.path.join(directory, '.gitignore')
        existing = ''
        if os.path.isfile(gitignore_path):
            with open(gitignore_path) as f:
                existing = f.read()
        present = {line.strip().rstrip('/') for line in existing.splitlines()}
        return [line for line in CANONICAL_REPO_GITIGNORE
                if line.rstrip('/') not in present]

    def ensure(self, directory: str) -> list:
        """Append any missing canonical lines to .gitignore; returns what was
        added. Only ever appends — the user's own rules are untouched."""
        missing = self.missing_lines(directory)
        if not missing:
            return []
        gitignore_path = os.path.join(directory, '.gitignore')
        prefix = ''
        if os.path.isfile(gitignore_path):
            with open(gitignore_path) as f:
                content = f.read()
            prefix = '' if (not content or content.endswith('\n')) else '\n'
        with open(gitignore_path, 'a') as f:
            f.write(prefix + '# sgit: key material must never land in git (canonical set)\n')
            for line in missing:
                f.write(line + '\n')
        return missing
