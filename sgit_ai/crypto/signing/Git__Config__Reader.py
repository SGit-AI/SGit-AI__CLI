"""Git__Config__Reader — the user's own Git config, global then system (design__02 §5.6.2).

Never the repository-level config (D3): nothing next to a vault can change signing.
With `git` installed: `git config --global|--system --includes --null --list`, which
honours GIT_CONFIG_GLOBAL / GIT_CONFIG_SYSTEM / GIT_CONFIG_NOSYSTEM / XDG_CONFIG_HOME.
Without it: a small reader for the global file (no includes; a warning names them).
Keys are returned lower-cased (sections and names; subsections as written, as git
prints them); the last value wins, global over system."""
import os
import sys
from   osbot_utils.type_safe.Type_Safe                    import Type_Safe
from   sgit_ai.crypto.signing.Signing__Command_Runner     import Signing__Command_Runner, TIMEOUT_CONFIG

BOOL_TRUE  = ('true', 'yes', 'on', '1', '')
BOOL_FALSE = ('false', 'no', 'off', '0')


class Git__Config__Reader(Type_Safe):
    runner : Signing__Command_Runner

    def read(self) -> dict:
        if self.runner.which('git'):
            values = {} if self.as_bool(os.environ.get('GIT_CONFIG_NOSYSTEM')) else self.read_with_git('--system')
            values.update(self.read_with_git('--global'))              # an explicit --system ignores NOSYSTEM
            return values
        return self.read_files()

    def read_with_git(self, scope: str) -> dict:
        result = self.runner.run(['git', 'config', scope, '--includes', '--null', '--list'], timeout=TIMEOUT_CONFIG)
        if result['code'] != 0:
            return {}                                               # no such file: git exits non-zero
        values = {}
        for record in result['out'].decode('utf-8', 'replace').split('\0'):
            if not record:
                continue
            key, _, value = record.partition('\n')
            values[self.normalise_key(key)] = value
        return values

    def normalise_key(self, key: str) -> str:
        section, _, rest = key.partition('.')
        if '.' in rest:
            subsection, _, name = rest.rpartition('.')
            return f'{section.lower()}.{subsection}.{name.lower()}'
        return f'{section.lower()}.{rest.lower()}'

    def global_file(self) -> str:
        if os.environ.get('GIT_CONFIG_GLOBAL'):
            return os.environ['GIT_CONFIG_GLOBAL']
        xdg = os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'), 'git', 'config')
        return xdg if os.path.isfile(xdg) else os.path.expanduser('~/.gitconfig')

    def read_files(self) -> dict:
        path = self.global_file()
        if not os.path.isfile(path):
            return {}
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return self.parse(f.read())

    def parse(self, text: str) -> dict:
        values, section = {}, ''
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line[0] in '#;':
                continue
            if line.startswith('['):
                header = line[1:line.index(']')] if ']' in line else line[1:]
                name, _, sub = header.partition(' ')
                section = name.lower() + ('.' + sub.strip().strip('"').replace('\\"', '"') if sub.strip() else '')
                if section.startswith(('include', 'includeif')):
                    print(f'  warning: {self.global_file()}: [{header}] is not read without git installed',
                          file=sys.stderr)
                continue
            key, has_value, value = line.partition('=')
            values[f'{section}.{key.strip().lower()}'] = self.unquote(value.strip()) if has_value else 'true'
        return values

    def unquote(self, value: str) -> str:
        out, quoted, i = [], False, 0
        while i < len(value):
            ch = value[i]
            if ch == '"':
                quoted = not quoted
            elif ch == '\\' and i + 1 < len(value):
                i  += 1
                out.append({'n': '\n', 't': '\t', 'b': '\b'}.get(value[i], value[i]))
            elif ch in '#;' and not quoted:
                break
            else:
                out.append(ch)
            i += 1
        return ''.join(out).strip()

    def as_bool(self, value) -> bool:
        return value is not None and str(value).strip().lower() in BOOL_TRUE
