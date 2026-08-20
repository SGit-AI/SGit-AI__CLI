import fnmatch
import os
from   osbot_utils.type_safe.Type_Safe import Type_Safe

ALWAYS_IGNORED_DIRS = { '.sg_vault'    ,           # vault internal metadata
                        '.sg_vault_new',           # vault move temp dir
                        '.git'         ,           # git internals
                        '.github'      ,           # CI/workflow config — not vault content (decision 17)
                        'node_modules' ,           # npm packages
                        '__pycache__'  ,           # Python bytecode cache
                        '.venv'        ,           # Python virtual environments
                        '.tox'         ,           # tox test runner
                        '.nox'         ,           # nox test runner
                        '.eggs'        ,           # setuptools build
                        '.mypy_cache'  ,           # mypy type checker
                        '.pytest_cache',           # pytest cache
                        '.ruff_cache'  ,           # ruff linter cache
                        '.idea'        ,           # JetBrains IDE workspace
                        '.vscode'      ,           # VS Code workspace settings
                        '.cache'       ,           # generic build/tooling cache
                        '.parcel-cache',           # Parcel bundler cache
                        '.next'        ,           # Next.js build output
                        '.nuxt'        ,           # Nuxt.js build output
                        '.terraform'   ,           # Terraform local state cache
                        '.svelte-kit'  ,           # SvelteKit build output
                        '.turbo'       ,           # Turbo cache
                        '.DS_Store'    ,           # macOS Finder metadata
                        '.AppleDouble' ,           # macOS metadata
                        }

# Prefix-matched dirs — vault move backup dirs use a timestamp suffix (.sg_vault_old_<ts>)
ALWAYS_IGNORED_DIR_PREFIXES = ('.sg_vault_old_',)

ALWAYS_IGNORED_FILES = { '.env'              ,     # environment file with secrets
                         '.env.local'        ,     # environment file with secrets
                         '.env.production'   ,     # environment file with secrets
                         '.env.development'  ,     # environment file with secrets
                         '.netrc'            ,     # FTP/HTTP credentials
                         '.pgpass'           ,     # PostgreSQL credentials
                         '.git-credentials'  ,     # git credentials file
                         'id_rsa'            ,     # SSH private key
                         'id_ed25519'        ,     # SSH private key
                         'id_ecdsa'          ,     # SSH private key
                         'id_dsa'            ,     # SSH private key
                         '.npmrc'            ,     # may contain auth tokens
                         '.pypirc'           ,     # PyPI credentials
                         }

# .env.example / .env.sample / .env.template are NOT in the set —
# templates without secrets should be tracked.
ENV_TEMPLATE_ALLOWLIST = {'.env.example', '.env.sample', '.env.template'}


class Vault__Ignore(Type_Safe):
    """Parse .gitignore files and match paths against ignore patterns.

    Supports: comments (#), blank lines, negation (!), directory-only
    patterns (trailing /), wildcards (*, ?), and ** for recursive matching.

    Dotfiles are tracked by default unless they appear in ALWAYS_IGNORED_DIRS,
    ALWAYS_IGNORED_FILES, the .env* secret glob, or a .gitignore pattern.

    Tracked-wins (decision 17, P0): ignore rules govern UNTRACKED files only,
    matching git. A path already present in the vault head is never dropped by
    an ignore rule — otherwise adding a rule (e.g. `.github` joining
    ALWAYS_IGNORED_DIRS on a version bump) would record every tracked file
    under it as a deletion on the next commit: silent content loss. Callers
    that scan a vault work tree load the head's path set via
    load_tracked_from_vault(); matching without it keeps the pre-decision-17
    behaviour for non-vault uses of this class.
    """
    patterns      : list
    tracked_paths : set
    tracked_dirs  : set

    def load_gitignore(self, directory: str) -> 'Vault__Ignore':
        gitignore_path = os.path.join(directory, '.gitignore')
        if os.path.isfile(gitignore_path):
            with open(gitignore_path, 'r') as f:
                for line in f:
                    line = line.rstrip('\n').rstrip('\r')
                    parsed = self._parse_line(line)
                    if parsed:
                        self.patterns.append(parsed)
        return self

    def load_tracked_paths(self, paths) -> 'Vault__Ignore':
        for path in paths:
            self.tracked_paths.add(path)
            parts = path.split('/')
            for i in range(1, len(parts)):
                self.tracked_dirs.add('/'.join(parts[:i]))
        return self

    def load_tracked_from_vault(self, directory: str, crypto=None) -> 'Vault__Ignore':
        """Best-effort load of the vault head's path set, enabling tracked-wins.

        Never raises: a directory that is not (yet) a vault, a missing key, or
        an empty history simply leaves the tracked set empty, which restores
        plain ignore-rule matching.
        """
        from sgit_ai.core.Vault__Head_Paths import Vault__Head_Paths
        helper = Vault__Head_Paths(crypto=crypto)
        self.load_tracked_paths(helper.paths(directory))
        self._emit_github_migration_notice_once(directory)
        return self

    def should_ignore_dir(self, rel_dir: str) -> bool:
        if not self._dir_matches_ignore_rule(rel_dir):
            return False
        if rel_dir in self.tracked_dirs:            # tracked-wins: descend so the
            return False                            # per-file rule can decide
        return True

    def _dir_matches_ignore_rule(self, rel_dir: str) -> bool:
        dir_name = rel_dir.rsplit('/', 1)[-1] if '/' in rel_dir else rel_dir
        if dir_name in ALWAYS_IGNORED_DIRS:
            return True
        if any(dir_name.startswith(p) for p in ALWAYS_IGNORED_DIR_PREFIXES):
            return True
        return self._matches(rel_dir, is_dir=True)

    def should_ignore_file(self, rel_path: str) -> bool:
        if rel_path in self.tracked_paths:          # tracked-wins
            return False
        filename = rel_path.rsplit('/', 1)[-1] if '/' in rel_path else rel_path
        if filename in ALWAYS_IGNORED_FILES:
            return True
        if self._is_env_secret(filename):
            return True
        if self._matches(rel_path, is_dir=False):
            return True
        # A walk only descends into an ignored directory when it holds tracked
        # files (should_ignore_dir above). Untracked files inside it must still
        # be ignored, so check the ancestors — but only when the tracked set is
        # loaded, since otherwise ignored directories are pruned before their
        # files are ever seen.
        if self.tracked_dirs and '/' in rel_path:
            parts = rel_path.split('/')
            for i in range(1, len(parts)):
                if self._dir_matches_ignore_rule('/'.join(parts[:i])):
                    return True
        return False

    def _emit_github_migration_notice_once(self, directory: str) -> None:
        """One-time notice when a vault head tracks .github/** (decision 17)."""
        import json
        import sys
        if not any(p == '.github' or p.startswith('.github/') for p in self.tracked_paths):
            return
        local_dir = os.path.join(directory, '.sg_vault', 'local')
        if not os.path.isdir(local_dir):
            return
        notices_path = os.path.join(local_dir, 'notices.json')
        try:
            notices = {}
            if os.path.isfile(notices_path):
                with open(notices_path, 'r') as f:
                    notices = json.load(f)
            if notices.get('github_tracked_notice'):
                return
            notices['github_tracked_notice'] = True
            with open(notices_path, 'w') as f:
                json.dump(notices, f, indent=2)
        except Exception:
            return
        print('note: this vault tracks files under .github/, which is now an ignored\n'
              '      folder by default (workflow files in a vault can turn vault-write\n'
              '      into code execution on a publisher\'s CI runner). Your tracked\n'
              '      .github/ files are grandfathered and stay in the vault; new files\n'
              '      under .github/ will not be added.\n'
              '      To remove them from the vault deliberately, in one visible commit\n'
              '      and without touching your work tree:\n'
              '        sgit vault ignore --apply .github',
              file=sys.stderr)

    def _is_env_secret(self, filename: str) -> bool:
        if not filename.startswith('.env'):
            return False
        return filename not in ENV_TEMPLATE_ALLOWLIST

    def explain(self, rel_path: str, is_dir: bool = False) -> object:
        from sgit_ai.schemas.inspect.Schema__Ignore_Reason import Schema__Ignore_Reason
        name = rel_path.rsplit('/', 1)[-1] if '/' in rel_path else rel_path

        if is_dir:
            reason = self._explain_dir_rule(rel_path)
            if reason.is_ignored and rel_path in self.tracked_dirs:
                return Schema__Ignore_Reason(rel_path    = rel_path,
                                             is_ignored  = False,
                                             reason_code = 'tracked',
                                             description = f'contains files tracked in the vault head '
                                                           f'(grandfathered — {reason.description}); '
                                                           f'new files under it are still ignored')
            return reason
        else:
            if rel_path in self.tracked_paths:
                return Schema__Ignore_Reason(rel_path    = rel_path,
                                             is_ignored  = False,
                                             reason_code = 'tracked',
                                             description = 'tracked in the vault head — ignore rules '
                                                           'apply to untracked files only')
            if name in ALWAYS_IGNORED_FILES:
                return Schema__Ignore_Reason(rel_path     = rel_path,
                                             is_ignored   = True,
                                             reason_code  = 'always_ignored_file',
                                             matched_rule = name,
                                             description  = ALWAYS_IGNORED_FILES_DESCRIPTIONS.get(name, 'always-ignored file'))
            if self._is_env_secret(name):
                return Schema__Ignore_Reason(rel_path     = rel_path,
                                             is_ignored   = True,
                                             reason_code  = 'env_secret_glob',
                                             matched_rule = '.env*',
                                             description  = 'environment file matching .env* (not a known template)')
            # Check if any parent directory is ignored (by rule — the tracked
            # exemption applies to already-tracked files, checked above, not to
            # untracked files inside a grandfathered directory)
            parts = rel_path.split('/')
            for i in range(1, len(parts)):
                parent = '/'.join(parts[:i])
                parent_reason = self._explain_dir_rule(parent)
                if parent_reason.is_ignored:
                    return Schema__Ignore_Reason(rel_path     = rel_path,
                                                 is_ignored   = True,
                                                 reason_code  = parent_reason.reason_code,
                                                 matched_rule = parent_reason.matched_rule,
                                                 description  = f'parent directory \'{parent}\' is ignored ({parent_reason.description})')
            if self._matches(rel_path, is_dir=False):
                matched = self._find_matching_pattern(rel_path, is_dir=False)
                return Schema__Ignore_Reason(rel_path     = rel_path,
                                             is_ignored   = True,
                                             reason_code  = 'gitignore_pattern',
                                             matched_rule = matched,
                                             description  = f'matched by .gitignore pattern \'{matched}\'')

        return Schema__Ignore_Reason(rel_path    = rel_path,
                                     is_ignored  = False,
                                     reason_code = 'tracked',
                                     description = 'not matched by any ignore rule')

    def _explain_dir_rule(self, rel_path: str) -> object:
        """Ignore reason for a directory from the rules alone (no tracked exemption)."""
        from sgit_ai.schemas.inspect.Schema__Ignore_Reason import Schema__Ignore_Reason
        name = rel_path.rsplit('/', 1)[-1] if '/' in rel_path else rel_path
        if name in ALWAYS_IGNORED_DIRS:
            return Schema__Ignore_Reason(rel_path     = rel_path,
                                         is_ignored   = True,
                                         reason_code  = 'always_ignored_dir',
                                         matched_rule = name,
                                         description  = ALWAYS_IGNORED_DIRS_DESCRIPTIONS.get(name, 'always-ignored directory'))
        prefix_match = next((p for p in ALWAYS_IGNORED_DIR_PREFIXES if name.startswith(p)), None)
        if prefix_match:
            return Schema__Ignore_Reason(rel_path     = rel_path,
                                         is_ignored   = True,
                                         reason_code  = 'always_ignored_dir',
                                         matched_rule = prefix_match + '*',
                                         description  = 'always-ignored vault internal directory')
        if self._matches(rel_path, is_dir=True):
            matched = self._find_matching_pattern(rel_path, is_dir=True)
            return Schema__Ignore_Reason(rel_path     = rel_path,
                                         is_ignored   = True,
                                         reason_code  = 'gitignore_pattern',
                                         matched_rule = matched,
                                         description  = f'matched by .gitignore pattern \'{matched}\'')
        return Schema__Ignore_Reason(rel_path    = rel_path,
                                     is_ignored  = False,
                                     reason_code = 'tracked',
                                     description = 'not matched by any ignore rule')

    def _find_matching_pattern(self, rel_path: str, is_dir: bool) -> str:
        last_match = None
        for pattern in self.patterns:
            negate   = pattern['negate'  ]
            dir_only = pattern['dir_only']
            pat      = pattern['pattern' ]
            if dir_only and not is_dir:
                continue
            if self._path_matches(rel_path, pat, is_dir):
                last_match = None if negate else pat
        return last_match or ''

    def _matches(self, rel_path: str, is_dir: bool) -> bool:
        ignored = False
        for pattern in self.patterns:
            negate   = pattern['negate'  ]
            dir_only = pattern['dir_only']
            pat      = pattern['pattern' ]

            if dir_only and not is_dir:
                continue

            if self._path_matches(rel_path, pat, is_dir):
                ignored = not negate
        return ignored

    def _path_matches(self, rel_path: str, pattern: str, is_dir: bool) -> bool:
        if '/' in pattern.rstrip('/'):
            return self._match_anchored(rel_path, pattern, is_dir)
        else:
            return self._match_basename(rel_path, pattern, is_dir)

    def _match_basename(self, rel_path: str, pattern: str, is_dir: bool) -> bool:
        name = rel_path.rsplit('/', 1)[-1] if '/' in rel_path else rel_path
        if fnmatch.fnmatch(name, pattern):
            return True
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        return False

    def _match_anchored(self, rel_path: str, pattern: str, is_dir: bool) -> bool:
        if '**' in pattern:
            return self._match_doublestar(rel_path, pattern)
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        return False

    def _match_doublestar(self, rel_path: str, pattern: str) -> bool:
        if pattern == '**':
            return True
        if pattern.startswith('**/'):
            rest = pattern[3:]
            if fnmatch.fnmatch(rel_path, rest):
                return True
            parts = rel_path.split('/')
            for i in range(len(parts)):
                sub = '/'.join(parts[i:])
                if fnmatch.fnmatch(sub, rest):
                    return True
            return False
        if pattern.endswith('/**'):
            prefix = pattern[:-3]
            if rel_path == prefix or rel_path.startswith(prefix + '/'):
                return True
            return False
        before, after = pattern.split('**', 1)
        if before and not rel_path.startswith(before):
            return False
        remainder = rel_path[len(before):]
        after = after.lstrip('/')
        if not after:
            return True
        parts = remainder.split('/')
        for i in range(len(parts)):
            sub = '/'.join(parts[i:])
            if fnmatch.fnmatch(sub, after):
                return True
        return False

    def _parse_line(self, line: str) -> dict:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            return None
        negate = False
        if stripped.startswith('!'):
            negate   = True
            stripped = stripped[1:]
        dir_only = stripped.endswith('/')
        if dir_only:
            stripped = stripped.rstrip('/')
        if stripped.startswith('/'):
            stripped = stripped[1:]
        if not stripped:
            return None
        return dict(pattern  = stripped,
                    negate   = negate  ,
                    dir_only = dir_only)


ALWAYS_IGNORED_DIRS_DESCRIPTIONS = {
    '.sg_vault'    : 'vault internal metadata',
    '.git'         : 'git internals',
    '.github'      : 'CI/workflow config — not vault content (decision 17)',
    'node_modules' : 'npm packages',
    '__pycache__'  : 'Python bytecode cache',
    '.venv'        : 'Python virtual environments',
    '.tox'         : 'tox test runner',
    '.nox'         : 'nox test runner',
    '.eggs'        : 'setuptools build',
    '.mypy_cache'  : 'mypy type checker',
    '.pytest_cache': 'pytest cache',
    '.ruff_cache'  : 'ruff linter cache',
    '.idea'        : 'JetBrains IDE workspace',
    '.vscode'      : 'VS Code workspace settings',
    '.cache'       : 'generic build/tooling cache',
    '.parcel-cache': 'Parcel bundler cache',
    '.next'        : 'Next.js build output',
    '.nuxt'        : 'Nuxt.js build output',
    '.terraform'   : 'Terraform local state cache',
    '.svelte-kit'  : 'SvelteKit build output',
    '.turbo'       : 'Turbo cache',
    '.DS_Store'    : 'macOS Finder metadata',
    '.AppleDouble' : 'macOS metadata',
}

ALWAYS_IGNORED_FILES_DESCRIPTIONS = {
    '.env'             : 'environment file with secrets',
    '.env.local'       : 'environment file with secrets',
    '.env.production'  : 'environment file with secrets',
    '.env.development' : 'environment file with secrets',
    '.netrc'           : 'FTP/HTTP credentials',
    '.pgpass'          : 'PostgreSQL credentials',
    '.git-credentials' : 'git credentials file',
    'id_rsa'           : 'SSH private key',
    'id_ed25519'       : 'SSH private key',
    'id_ecdsa'         : 'SSH private key',
    'id_dsa'           : 'SSH private key',
    '.npmrc'           : 'may contain auth tokens',
    '.pypirc'          : 'PyPI credentials',
}
