"""Container__Command_Runner — the one place `sgit serve` runs an external program.

Every runtime adapter builds an argv list (never a shell string, so nothing in a path or
an image name is interpreted by a shell) and hands it here."""
import shutil
import subprocess
from   osbot_utils.type_safe.Type_Safe import Type_Safe


class Container__Command_Runner(Type_Safe):

    def which(self, binary: str) -> str:
        return shutil.which(binary) or ''

    def run(self, argv: list, timeout: int = 600, env: dict = None) -> dict:
        """dict(code, out, err). A missing binary or a timeout is a failed run, not a crash."""
        try:
            done = subprocess.run([str(a) for a in argv], capture_output=True, text=True, timeout=timeout, env=env)
            return dict(code=done.returncode, out=done.stdout or '', err=done.stderr or '')
        except FileNotFoundError as error:
            return dict(code=127, out='', err=str(error))
        except subprocess.TimeoutExpired:
            return dict(code=124, out='', err=f'timed out after {timeout}s: {" ".join(map(str, argv[:3]))} …')

    def run_visible(self, argv: list, env: dict = None) -> int:
        """Run with the user's terminal attached (installers that ask for a password, `logs -f`)."""
        try:
            return subprocess.call([str(a) for a in argv], env=env)
        except FileNotFoundError:
            return 127
        except KeyboardInterrupt:
            return 130

    def spawn(self, argv: list, log_path: str, env: dict = None, cwd: str = None) -> int:
        """Start a detached background process (the uv engine), output to log_path. Returns its pid."""
        log = open(log_path, 'ab')
        process = subprocess.Popen([str(a) for a in argv], stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                   env=env, cwd=cwd, start_new_session=True)
        return process.pid
