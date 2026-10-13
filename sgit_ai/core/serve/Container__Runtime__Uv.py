"""Container__Runtime__Uv — the SG/Send server without any container runtime.

The image's own server code is a PyPI package (`sgraph-ai-app-send`, Python >= 3.12). `uv`
(one static binary) fetches Python 3.12 and the package itself, so a machine with no Docker,
Podman or Apple container can still run the same server, as a background process
(verified 2026-10-12). "latest" is the newest release on PyPI.

The built vault UI is not in that package (the image builds it), so this engine serves the
API and, unless `--ui-dir` names a built UI folder, a small page saying how to open the
vault from the hosted UI.
"""
import os
import signal
from   sgit_ai.core.serve.Container__Runtime import Container__Runtime

PACKAGE        = 'sgraph-ai-app-send'
PYTHON_VERSION = '3.12'
BOOT = ('import sys, uvicorn\n'
        'from sgraph_ai_app_send__docker.app import create_app\n'
        'uvicorn.run(create_app(), host=sys.argv[1], port=int(sys.argv[2]), log_level="info")\n')
PLACEHOLDER = """<!doctype html><meta charset="utf-8"><title>sgit serve</title>
<body style="font-family:system-ui;max-width:40em;margin:3em auto;line-height:1.5">
<h1>Local vault server</h1>
<p>This server runs the SG/Send API without a container, so the vault UI is not bundled.</p>
<p>Open <a href="https://vault.sgraph.ai/">vault.sgraph.ai</a>, set <b>Server</b> to this page's address
(<code id="o"></code>), and open your vault. Or run <code>sgit serve</code> with Docker, Podman or
Apple container for the full local UI.</p>
<script>document.getElementById('o').textContent = location.origin</script>
"""


class Container__Runtime__Uv(Container__Runtime):

    def name(self) -> str:
        return 'uv'

    def describe(self) -> str:
        return 'uv (no container: the SG/Send server as a Python 3.12 process)'

    def is_container_runtime(self) -> bool:
        return False

    def ready_argv(self) -> list:
        return ['uv', '--version']

    def base_argv(self) -> list:
        return ['uv', 'run', '--no-project', '--python', PYTHON_VERSION, '--with', PACKAGE, '--with', 'uvicorn']

    def pull_argv(self, image: str) -> list:
        return self.base_argv()[:2] + ['--refresh-package', PACKAGE] + self.base_argv()[2:] + \
               ['python', '-c', 'import sgraph_ai_app_send__docker']

    def run_argv(self, spec: dict) -> list:
        return self.base_argv() + ['python', '-c', BOOT, str(spec['bind']), str(int(spec['host_port']))]

    def server_env(self, spec: dict) -> dict:
        env = dict(os.environ)
        env.update(SEND__STORAGE_MODE='disk', SEND__DISK_PATH=str(spec['data_dir']), SEND__STORAGE_BASE='',
                   SEND__STORAGE_VERSION='', SEND__DEPLOYMENT_ID='', SEND__VAULT_STATIC_DIR=str(spec['ui_dir']))
        env.update(spec.get('env') or {})
        return env

    def placeholder_ui(self, folder: str) -> str:
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, 'index.html'), 'w') as f:
            f.write(PLACEHOLDER)
        return folder

    def run(self, spec: dict) -> dict:
        """Start the server process; the result's `pid` is what stop() needs."""
        log_path = spec['log_path']
        pid = self.runner.spawn(self.run_argv(spec), log_path, env=self.server_env(spec), cwd=str(spec['data_dir']))
        return dict(code=0, out='', err='', pid=pid)

    def running(self, name: str, pid: int = 0) -> bool:
        if not pid:
            return False
        try:
            os.kill(int(pid), 0)
            return True
        except (OSError, ValueError):
            return False

    def stop(self, name: str, pid: int = 0) -> dict:
        if not self.running(name, pid):
            return dict(code=0, out='', err='')
        try:
            os.killpg(int(pid), signal.SIGTERM)                 # uv and the server it started
        except (OSError, AttributeError):
            os.kill(int(pid), signal.SIGTERM)
        return dict(code=0, out='', err='')

    def digest(self, image: str) -> str:
        return ''                                               # the version comes from /api/info/versions
