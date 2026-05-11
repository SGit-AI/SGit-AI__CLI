import fnmatch
import os
from   osbot_utils.type_safe.Type_Safe import Type_Safe

ALWAYS_IGNORED_DIRS = { '.sg_vault'    ,           # vault internal metadata
                        '.git'         ,           # git internals
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
    """
    patterns : list

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

    def should_ignore_dir(self, rel_dir: str) -> bool:
        dir_name = rel_dir.rsplit('/', 1)[-1] if '/' in rel_dir else rel_dir
        if dir_name in ALWAYS_IGNORED_DIRS:
            return True
        return self._matches(rel_dir, is_dir=True)

    def should_ignore_file(self, rel_path: str) -> bool:
        filename = rel_path.rsplit('/', 1)[-1] if '/' in rel_path else rel_path
        if filename in ALWAYS_IGNORED_FILES:
            return True
        if self._is_env_secret(filename):
            return True
        return self._matches(rel_path, is_dir=False)

    def _is_env_secret(self, filename: str) -> bool:
        if not filename.startswith('.env'):
            return False
        return filename not in ENV_TEMPLATE_ALLOWLIST

    def explain(self, rel_path: str, is_dir: bool = False) -> object:
        from sgit_ai.schemas.inspect.Schema__Ignore_Reason import Schema__Ignore_Reason
        name = rel_path.rsplit('/', 1)[-1] if '/' in rel_path else rel_path

        if is_dir:
            if name in ALWAYS_IGNORED_DIRS:
                return Schema__Ignore_Reason(rel_path     = rel_path,
                                             is_ignored   = True,
                                             reason_code  = 'always_ignored_dir',
                                             matched_rule = name,
                                             description  = ALWAYS_IGNORED_DIRS_DESCRIPTIONS.get(name, 'always-ignored directory'))
            if self._matches(rel_path, is_dir=True):
                matched = self._find_matching_pattern(rel_path, is_dir=True)
                return Schema__Ignore_Reason(rel_path     = rel_path,
                                             is_ignored   = True,
                                             reason_code  = 'gitignore_pattern',
                                             matched_rule = matched,
                                             description  = f'matched by .gitignore pattern \'{matched}\'')
        else:
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
