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
                        }


class Vault__Ignore(Type_Safe):
    """Parse .gitignore files and match paths against ignore patterns.

    Supports: comments (#), blank lines, negation (!), directory-only
    patterns (trailing /), wildcards (*, ?), and ** for recursive matching.
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
        if dir_name.startswith('.'):
            return True
        return self._matches(rel_dir, is_dir=True)

    def should_ignore_file(self, rel_path: str) -> bool:
        filename = rel_path.rsplit('/', 1)[-1] if '/' in rel_path else rel_path
        if filename.startswith('.'):
            return True
        return self._matches(rel_path, is_dir=False)

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
