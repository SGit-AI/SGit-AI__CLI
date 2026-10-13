"""A fake container runtime CLI for `sgit serve` unit tests: a real executable on PATH that
answers like docker/podman (`info`, `pull`, `run`, `inspect`, `image inspect`, `stop`, `rm`,
`logs`), records every argv it gets, and on `run` starts a tiny real HTTP server on the
published loopback port that answers /api/info/health — so the whole start/status/stop
lifecycle runs for real without Docker.

Behaviour knobs (files in the runtime's home folder): `info.fail` makes `info` exit 1;
`pull.fail` makes `pull` exit 1.
"""
import os
import stat
import sys

SCRIPT = r'''#!__PYTHON__
import json, os, signal, subprocess, sys, time
HOME = __HOME__
argv = sys.argv[1:]
with open(os.path.join(HOME, 'calls.log'), 'a') as f:
    f.write(json.dumps([os.path.basename(sys.argv[0])] + argv) + '\n')
def pidfile(name): return os.path.join(HOME, name + '.pid')
def alive(name):
    try:
        pid = int(open(pidfile(name)).read()); os.kill(pid, 0); return pid
    except Exception:
        return 0
cmd = argv[0] if argv else ''
if cmd == 'info':
    sys.exit(1 if os.path.exists(os.path.join(HOME, 'info.fail')) else 0)
if cmd == 'pull':
    sys.exit(1 if os.path.exists(os.path.join(HOME, 'pull.fail')) else 0)
if cmd == 'run':
    name = argv[argv.index('--name') + 1]
    publish = argv[argv.index('-p') + 1]
    host, port, _ = publish.rsplit(':', 2)
    server = ("import http.server, json\n"
              "class H(http.server.BaseHTTPRequestHandler):\n"
              "    def log_message(self, *a): pass\n"
              "    def do_GET(self):\n"
              "        body = json.dumps({'status':'ok'} if self.path == '/api/info/health' else {'sgraph_ai_app_send':'v0.0-fake'}).encode()\n"
              "        self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)\n"
              "http.server.ThreadingHTTPServer((%r, %d), H).serve_forever()\n" % (host, int(port)))
    p = subprocess.Popen([sys.executable, '-c', server], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    open(pidfile(name), 'w').write(str(p.pid))
    print('fakecontainerid'); sys.exit(0)
if cmd == 'inspect':
    print('true' if alive(argv[-1]) else 'false'); sys.exit(0 if os.path.exists(pidfile(argv[-1])) else 1)
if cmd == 'image':
    print('example/image@sha256:' + '0' * 64); sys.exit(0)
if cmd in ('stop', 'rm'):
    pid = alive(argv[-1])
    if pid:
        os.killpg(pid, signal.SIGTERM) if hasattr(os, 'killpg') else os.kill(pid, signal.SIGTERM)
    if cmd == 'rm' and os.path.exists(pidfile(argv[-1])):
        os.remove(pidfile(argv[-1]))
    sys.exit(0)
if cmd == 'logs':
    print('fake logs'); sys.exit(0)
sys.exit(0)
'''


class Fake_Container_Runtime:
    """Install fake runtime binaries named `names` in `bin_dir` (prepend it to PATH)."""

    def __init__(self, bin_dir: str, home: str, names=('docker',)):
        self.bin_dir, self.home = bin_dir, home
        os.makedirs(bin_dir, exist_ok=True)
        os.makedirs(home,    exist_ok=True)
        for name in names:
            path = os.path.join(bin_dir, name)
            with open(path, 'w') as f:
                f.write(SCRIPT.replace('__PYTHON__', sys.executable).replace('__HOME__', repr(home)))
            os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    def calls(self) -> list:
        import json
        try:
            with open(os.path.join(self.home, 'calls.log')) as f:
                return [json.loads(line) for line in f if line.strip()]
        except OSError:
            return []

    def flag(self, name: str) -> None:
        open(os.path.join(self.home, name), 'w').close()
