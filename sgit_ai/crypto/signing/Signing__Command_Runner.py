"""Signing__Command_Runner — the one place user signing runs a program (design__02 §5.5).

argv lists only, never a shell; bytes on stdin and stdout; cwd is the home folder, never
the vault; a small inherited environment (agent sockets, pinentry, Git's own config
variables) plus LC_ALL=C. A missing program is code 127 and a timeout code 124, as the
serve runner does, so callers turn both into their own messages."""
import os
import shutil
import subprocess                                                   # nosec B404 - argv lists only, no shell
from   osbot_utils.type_safe.Type_Safe              import Type_Safe

INHERITED_ENV = ('HOME', 'PATH', 'USER', 'LOGNAME', 'SSH_AUTH_SOCK', 'SSH_ASKPASS', 'SSH_ASKPASS_REQUIRE',
                 'GNUPGHOME', 'GPG_TTY', 'GPG_AGENT_INFO', 'DISPLAY', 'WAYLAND_DISPLAY', 'XDG_RUNTIME_DIR',
                 'XDG_CONFIG_HOME', 'GIT_CONFIG_GLOBAL', 'GIT_CONFIG_SYSTEM', 'GIT_CONFIG_NOSYSTEM',
                 'SYSTEMROOT', 'APPDATA', 'LOCALAPPDATA', 'USERPROFILE', 'TEMP', 'TMP')
TIMEOUT_SIGN   = 120
TIMEOUT_VERIFY = 30
TIMEOUT_CONFIG = 10


class Signing__Command_Runner(Type_Safe):

    def which(self, program: str) -> str:
        """The program's path: a configured path as is (when it exists), else a PATH lookup; '' if none."""
        if not program:
            return ''
        if os.sep in program or (os.altsep and os.altsep in program):
            expanded = os.path.expanduser(program)
            return expanded if os.path.isfile(expanded) else ''
        return shutil.which(program) or ''

    def env(self) -> dict:
        env = {name: os.environ[name] for name in INHERITED_ENV if name in os.environ}
        env['LC_ALL'] = 'C'
        return env

    def run(self, argv: list, stdin: bytes = b'', timeout: int = TIMEOUT_VERIFY) -> dict:
        program = self.which(str(argv[0]))
        if not program:
            return dict(code=127, out=b'', err=f'{argv[0]}: not found'.encode())
        try:
            done = subprocess.run([program] + [str(a) for a in argv[1:]], input=stdin,  # nosec B603 - argv list, no shell
                                  capture_output=True, timeout=timeout, env=self.env(),
                                  cwd=os.path.expanduser('~'), close_fds=True)
        except subprocess.TimeoutExpired:
            return dict(code=124, out=b'', err=f'{argv[0]}: timed out after {timeout} s'.encode())
        except OSError as e:
            return dict(code=126, out=b'', err=f'{argv[0]}: {e}'.encode())
        return dict(code=done.returncode, out=done.stdout, err=done.stderr)
