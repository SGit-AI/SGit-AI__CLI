"""Vault__Serve — `sgit serve`: run a working vault on this machine.

It runs the SG/Send vault image (`diniscruz/sg-send-vault`: the vault UI, the full API and a
disk store, always the latest release) with whatever container runtime this machine has
(Container__Runtimes), or the same server code under `uv` when there is none. Inside a clone
the server's data lives in `.sg_vault/serve/data` and the clone is pushed into it
(Vault__Serve__Mirror), so the browser opens exactly this clone's state.

Defaults that matter:
  * bound to 127.0.0.1 (a container's `-p 8080:8080` alone would publish on every interface);
  * the container runs as the host user (the image runs as uid 10001, so the data folder
    would not be writable otherwise);
  * the image digest that actually ran is recorded, so "latest" is never ambiguous later.
"""
import hashlib
import json
import os
import socket
import time
import urllib.request
from   osbot_utils.type_safe.Type_Safe                    import Type_Safe
from   sgit_ai.core.Vault__Errors                         import Vault__Serve_Error
from   sgit_ai.core.serve.Container__Command_Runner        import Container__Command_Runner
from   sgit_ai.core.serve.Container__Host                  import Container__Host
from   sgit_ai.core.serve.Container__Runtimes              import Container__Runtimes
from   sgit_ai.core.serve.Container__Runtime__Installer    import Container__Runtime__Installer
from   sgit_ai.schemas.serve.Schema__Serve__State          import Schema__Serve__State

IMAGE_DEFAULT  = 'diniscruz/sg-send-vault:latest'
PORT_DEFAULT   = 8420
BIND_DEFAULT   = '127.0.0.1'
STATE_FILE     = 'serve.json'
HEALTH_TIMEOUT = {'uv': 300}                              # the first uv run downloads Python and the server
HEALTH_DEFAULT = 90


class Vault__Serve(Type_Safe):
    runner : Container__Command_Runner
    host   : Container__Host

    def setup(self):
        if not self.host.system:
            self.host.detect()
        return self

    def runtimes(self) -> Container__Runtimes:
        return Container__Runtimes(runner=self.runner, host=self.host)

    def installer(self) -> Container__Runtime__Installer:
        return Container__Runtime__Installer(runner=self.runner, host=self.host)

    # -------------------------------------------------------------- places
    def vault_root(self, directory: str) -> str:
        current = os.path.abspath(directory or '.')
        while True:
            if os.path.isdir(os.path.join(current, '.sg_vault')):
                return current
            parent = os.path.dirname(current)
            if parent == current:
                return ''
            current = parent

    def places(self, directory: str, data: str = None) -> dict:
        """dict(vault_root, state_dir, data_dir, state_file, log_path)."""
        root = self.vault_root(directory) if not data else ''
        if data:
            data_dir  = os.path.abspath(data)
            state_dir = os.path.join(data_dir, '.sgit-serve')
        elif root:
            state_dir = os.path.join(root, '.sg_vault', 'serve')
            data_dir  = os.path.join(state_dir, 'data')
        else:
            raise Vault__Serve_Error('not inside a vault: run this in a clone, or give a data folder with '
                                     '--data DIR (an empty folder starts an empty local server)')
        return dict(vault_root=root, state_dir=state_dir, data_dir=data_dir,
                    state_file=os.path.join(state_dir, STATE_FILE), log_path=os.path.join(state_dir, 'server.log'))

    def container_name(self, places: dict) -> str:
        digest = hashlib.sha256(os.path.realpath(places['data_dir']).encode()).hexdigest()[:10]
        return f'sgit-serve-{digest}'

    def load_state(self, places: dict):
        try:
            with open(places['state_file']) as f:
                return Schema__Serve__State.from_json(json.load(f))
        except (OSError, ValueError):
            return None

    def save_state(self, places: dict, state: Schema__Serve__State) -> None:
        os.makedirs(places['state_dir'], exist_ok=True)
        tmp = places['state_file'] + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(state.json(), f, indent=2)
        os.replace(tmp, places['state_file'])

    def url(self, state) -> str:
        bind = str(state.bind or BIND_DEFAULT)
        host = 'localhost' if bind in ('127.0.0.1', '0.0.0.0', '::1') else bind     # nosec B104: compared, never bound (localhost: a secure context)
        return f'http://{host}:{int(state.host_port)}'

    # ------------------------------------------------------------ probing
    def health(self, url: str) -> bool:
        try:
            with urllib.request.urlopen(f'{url}/api/info/health', timeout=3) as response:   # nosec B310: http://<loopback>:<port> this command started  # nosemgrep
                return response.status == 200
        except Exception:
            return False

    def wait_healthy(self, url: str, seconds: int) -> bool:
        deadline = time.time() + seconds
        while time.time() < deadline:
            if self.health(url):
                return True
            time.sleep(1)
        return False

    def versions(self, url: str) -> dict:
        try:
            with urllib.request.urlopen(f'{url}/api/info/versions', timeout=3) as response:   # nosec B310: http://<loopback>:<port> this command started  # nosemgrep
                return json.loads(response.read().decode())
        except Exception:
            return {}

    def port_free(self, bind: str, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)    # health checks leave TIME_WAIT sockets
            try:
                s.bind((bind if bind != '0.0.0.0' else '', port))   # nosec B104: only with an explicit --bind 0.0.0.0, warned
                return True
            except OSError:
                return False

    def free_port(self, bind: str, preferred: int, wait: float = 0) -> int:
        """`preferred` if free (waiting up to `wait` seconds: a server just stopped releases its
        port a moment later), else the next free one."""
        deadline = time.time() + wait
        while time.time() < deadline and not self.port_free(bind, preferred):
            time.sleep(0.5)
        for port in [preferred] + list(range(preferred + 1, preferred + 50)):
            if self.port_free(bind, port):
                return port
        raise Vault__Serve_Error(f'no free port from {preferred} to {preferred + 49}; pass --port')

    def is_running(self, runtime, state) -> bool:
        if runtime is None or state is None:
            return False
        if runtime.is_container_runtime():
            return runtime.running(str(state.container_name))
        return runtime.running(str(state.container_name), int(state.pid))

    # ---------------------------------------------------------- lifecycle
    def start(self, directory: str, data: str = None, port: int = PORT_DEFAULT, bind: str = BIND_DEFAULT,
              runtime_name: str = None, image: str = IMAGE_DEFAULT, pull: bool = True, ui_dir: str = None,
              on_progress: callable = None) -> dict:
        _p     = on_progress or (lambda *a: None)
        places = self.places(directory, data)
        state  = self.load_state(places)
        if state is not None:
            runtime = self.runtimes().by_name(str(state.runtime))
            if self.is_running(runtime, state) and self.health(self.url(state)):
                return dict(status='already_running', url=self.url(state), state=state, places=places)

        try:
            runtime = self.runtimes().pick(runtime_name)
        except ValueError as error:
            raise Vault__Serve_Error(str(error))
        if runtime is None:
            first = self.installer().recommended()[0]
            raise Vault__Serve_Error(f'no container runtime found (Docker, Podman, Apple container) and no uv. '
                                     f'Install one with: sgit serve install {first}   '
                                     f'(sgit serve runtimes lists the options)')
        _p('runtime', runtime.describe())

        if pull:
            _p('pull', image if runtime.is_container_runtime() else 'sgraph-ai-app-send (latest, via uv)')
            result = runtime.pull(image)
            if result['code'] != 0 and not (runtime.is_container_runtime() and runtime.digest(image)):
                raise Vault__Serve_Error(f'could not get {image} with {runtime.name()}: '
                                         f'{(result["err"] or result["out"]).strip()[-400:]}')
            if result['code'] != 0:
                _p('warn', f'could not check for a newer image ({(result["err"] or "").strip()[:200]}); '
                           f'using the one already here')

        os.makedirs(places['data_dir'], exist_ok=True)
        if state is not None and int(port) == PORT_DEFAULT and int(state.host_port):
            port = int(state.host_port)                               # the same address as last time
        host_port = self.free_port(bind, int(port), wait=5 if state is not None else 0)
        name      = self.container_name(places)
        spec      = dict(image=image, name=name, bind=bind, host_port=host_port, data_dir=places['data_dir'],
                         user=self.host.user_spec(), env={}, log_path=places['log_path'],
                         ui_dir=ui_dir or '')
        if not runtime.is_container_runtime():
            os.makedirs(places['state_dir'], exist_ok=True)
            spec['ui_dir'] = ui_dir or runtime.placeholder_ui(os.path.join(places['state_dir'], 'ui'))
        _p('start', ' '.join(runtime.run_argv(spec)) if runtime.is_container_runtime() else 'uv run … (SG/Send server)')
        result = runtime.run(spec)
        if result['code'] != 0:
            raise Vault__Serve_Error(f'{runtime.name()} could not start the server: '
                                     f'{(result["err"] or result["out"]).strip()[-600:]}')
        state = Schema__Serve__State(runtime=runtime.name(), container_name=name, image=image,
                                     image_digest=runtime.digest(image) if runtime.is_container_runtime() else '',
                                     bind=bind, host_port=host_port, data_dir=places['data_dir'],
                                     pid=int(result.get('pid') or 0), started_at=int(time.time() * 1000))
        self.save_state(places, state)
        url = self.url(state)
        _p('wait', f'{url}/api/info/health')
        if not self.wait_healthy(url, HEALTH_TIMEOUT.get(runtime.name(), HEALTH_DEFAULT)):
            raise Vault__Serve_Error(f'the server did not answer on {url} in time; see `sgit serve logs`')
        return dict(status='started', url=url, state=state, places=places, versions=self.versions(url))

    def stop(self, directory: str, data: str = None) -> dict:
        places = self.places(directory, data)
        state  = self.load_state(places)
        if state is None:
            return dict(status='not_started', places=places)
        runtime = self.runtimes().by_name(str(state.runtime))
        if runtime is None:
            raise Vault__Serve_Error(f'{state.runtime} is not available on this machine any more')
        if runtime.is_container_runtime():
            runtime.stop(str(state.container_name))
        else:
            runtime.stop(str(state.container_name), int(state.pid))
        return dict(status='stopped', places=places, state=state)

    def status(self, directory: str, data: str = None) -> dict:
        places = self.places(directory, data)
        state  = self.load_state(places)
        if state is None:
            return dict(status='not_started', places=places)
        runtime = self.runtimes().by_name(str(state.runtime))
        running = self.is_running(runtime, state)
        url     = self.url(state)
        healthy = running and self.health(url)
        return dict(status='running' if healthy else ('starting' if running else 'stopped'), url=url, state=state,
                    places=places, versions=self.versions(url) if healthy else {})

    def logs(self, directory: str, data: str = None, follow: bool = False) -> int:
        places = self.places(directory, data)
        state  = self.load_state(places)
        if state is None:
            raise Vault__Serve_Error('no server has been started here (sgit serve)')
        runtime = self.runtimes().by_name(str(state.runtime))
        if runtime is not None and runtime.is_container_runtime():
            return runtime.logs(str(state.container_name), follow)
        argv = (['tail', '-f', places['log_path']] if follow else ['cat', places['log_path']])
        return self.runner.run_visible(argv)
