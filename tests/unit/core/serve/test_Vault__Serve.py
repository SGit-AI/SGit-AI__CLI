"""`sgit serve` lifecycle against a fake runtime CLI that starts a real loopback server,
and the clone <-> local server mirror against an in-memory server."""
import os

import pytest

from sgit_ai.core.Vault__Errors                       import Vault__Serve_Error
from sgit_ai.core.serve.Container__Command_Runner      import Container__Command_Runner
from sgit_ai.core.serve.Container__Host                import Container__Host
from sgit_ai.core.serve.Vault__Serve                   import Vault__Serve
from sgit_ai.core.serve.Vault__Serve__Mirror           import Vault__Serve__Mirror
from sgit_ai.network.api.Vault__API__In_Memory         import Vault__API__In_Memory
from sgit_ai.schemas.serve.Schema__Serve__State        import Schema__Serve__State
from tests._helpers.fake_container_runtime             import Fake_Container_Runtime
from tests._helpers.vault_test_env                     import Vault__Test_Env


def _write(d, rel, content):
    full = os.path.join(d, rel)
    os.makedirs(os.path.dirname(full) or d, exist_ok=True)
    with open(full, 'w') as f:
        f.write(content)


class Test_Vault__Serve__Lifecycle:

    def _serve(self, monkeypatch, tmp_path, names=('docker',)):
        fake = Fake_Container_Runtime(str(tmp_path / 'bin'), str(tmp_path / 'home'), names)
        monkeypatch.setenv('PATH', fake.bin_dir + os.pathsep + os.environ.get('PATH', ''))
        host = Container__Host(system='linux', machine='x86_64', os_version='6', uid=1000, gid=1000, has_ids=True)
        return fake, Vault__Serve(runner=Container__Command_Runner(), host=host)

    def test_start_status_stop_with_a_data_folder(self, monkeypatch, tmp_path):
        fake, serve = self._serve(monkeypatch, tmp_path)
        data = str(tmp_path / 'data')
        info = serve.start('.', data=data, port=18420)
        try:
            assert info['status'] == 'started' and info['url'] == 'http://localhost:18420'
            run = [c for c in fake.calls() if c[1] == 'run'][0]
            assert run[run.index('-p') + 1] == '127.0.0.1:18420:8080' and run[run.index('--user') + 1] == '1000:1000'
            state = info['state']
            assert str(state.image_digest).startswith('example/image@sha256:')
            assert serve.status('.', data=data)['status'] == 'running'
            assert serve.start('.', data=data, port=18420)['status'] == 'already_running'
        finally:
            serve.stop('.', data=data)
        assert serve.status('.', data=data)['status'] == 'stopped'

    def test_a_failed_pull_uses_the_image_already_here(self, monkeypatch, tmp_path):
        fake, serve = self._serve(monkeypatch, tmp_path)
        fake.flag('pull.fail')
        warnings = []
        data = str(tmp_path / 'data')
        try:
            serve.start('.', data=data, port=18430, on_progress=lambda kind, text: warnings.append(kind))
            assert 'warn' in warnings
        finally:
            serve.stop('.', data=data)

    def test_no_runtime_says_how_to_install_one(self, monkeypatch, tmp_path):
        fake, serve = self._serve(monkeypatch, tmp_path, names=())
        monkeypatch.setenv('PATH', fake.bin_dir)
        with pytest.raises(Vault__Serve_Error, match='sgit serve install podman'):
            serve.start('.', data=str(tmp_path / 'data'))

    def test_places(self, tmp_path):
        serve = Vault__Serve(host=Container__Host(system='linux'))
        clone = tmp_path / 'clone'
        (clone / '.sg_vault').mkdir(parents=True)
        (clone / 'docs').mkdir()
        places = serve.places(str(clone / 'docs'))                                     # found from a subfolder
        assert places['data_dir'] == str(clone / '.sg_vault' / 'serve' / 'data')
        assert places['vault_root'] == str(clone)
        with pytest.raises(Vault__Serve_Error, match='not inside a vault'):
            serve.places(str(tmp_path / 'nowhere'))
        assert serve.container_name(places) == serve.container_name(serve.places(str(clone)))   # stable

    def test_state_round_trip(self):
        state = Schema__Serve__State(runtime='podman', container_name='sgit-serve-1', image='a/b:latest',
                                     image_digest='a/b@sha256:' + '1' * 64, bind='127.0.0.1', host_port=8420,
                                     data_dir='C:\\Users\\Dinis Cruz\\vault', pid=0, started_at=1)
        assert Schema__Serve__State.from_json(state.json()).json() == state.json()

    def test_a_taken_port_moves_to_the_next(self):
        import socket
        serve = Vault__Serve(host=Container__Host(system='linux'))
        with socket.socket() as taken:
            taken.bind(('127.0.0.1', 0))
            taken.listen()
            port = taken.getsockname()[1]
            assert serve.free_port('127.0.0.1', port) != port


class Test_Vault__Serve__Mirror:
    """The clone pushes into the local server and fast-forwards from it; its own tracking of
    the real server (named-ref copy, rewind baselines) is never touched."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.md': 'a', 'docs/b.md': 'b'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s      = self._env.restore()
        self.local  = Vault__API__In_Memory()
        self.local.setup()
        self.mirror = Vault__Serve__Mirror(crypto=self.s.crypto, api=self.local)

    def teardown_method(self):
        self.s.cleanup()

    def _browser(self):
        """A second clone of the local server: what the browser does when it edits."""
        from sgit_ai.core.Vault__Sync import Vault__Sync
        sync = Vault__Sync(crypto=self.s.crypto, api=self.local)
        path = os.path.join(self.s.tmp_dir, 'browser')
        sync.clone(self.s.vault_key, path)
        return sync, path

    def _tracking(self):
        c = self.s.sync._init_components(self.s.vault_dir)
        baselines = os.path.join(c.storage.local_dir(self.s.vault_dir), 'remote_heads.json')
        return open(baselines).read() if os.path.isfile(baselines) else ''

    def test_push_copies_the_clone_and_pull_brings_browser_work_back(self):
        tracking = self._tracking()
        assert self.mirror.push(self.s.vault_dir)['moved']
        sync, browser = self._browser()
        assert open(os.path.join(browser, 'docs', 'b.md')).read() == 'b'
        _write(browser, 'web.md', 'from the browser')
        sync.commit(browser, 'web edit')
        sync.push(browser)
        result = self.mirror.pull(self.s.vault_dir)
        assert result['status'] == 'updated'
        assert open(os.path.join(self.s.vault_dir, 'web.md')).read() == 'from the browser'
        assert self._tracking() == tracking                                          # the real server's tracking is untouched
        assert self.s.sync.status(self.s.vault_dir)['push_status'] in ('ahead', 'diverged', 'behind', 'unknown')

    def test_push_after_new_local_commits_moves_the_server_forward(self):
        self.mirror.push(self.s.vault_dir)
        _write(self.s.vault_dir, 'c.md', 'c')
        head = self.s.sync.commit(self.s.vault_dir, 'c')['commit_id']
        result = self.mirror.push(self.s.vault_dir)
        assert result['moved'] and result['head'] == head
        assert self.mirror.push(self.s.vault_dir)['moved'] is False                  # nothing new

    def test_browser_work_is_never_overwritten_and_divergence_is_refused(self):
        self.mirror.push(self.s.vault_dir)
        sync, browser = self._browser()
        _write(browser, 'web.md', 'web'); sync.commit(browser, 'web'); sync.push(browser)
        _write(self.s.vault_dir, 'mine.md', 'mine'); self.s.sync.commit(self.s.vault_dir, 'mine')
        with pytest.raises(Vault__Serve_Error, match='sgit serve pull'):
            self.mirror.push(self.s.vault_dir)
        with pytest.raises(Vault__Serve_Error, match='diverged'):
            self.mirror.pull(self.s.vault_dir)
        assert not os.path.exists(os.path.join(self.s.vault_dir, 'web.md'))         # nothing changed
        assert self.mirror.push(self.s.vault_dir, force=True)['moved']               # on purpose

    def test_pull_refuses_with_uncommitted_changes(self):
        self.mirror.push(self.s.vault_dir)
        sync, browser = self._browser()
        _write(browser, 'web.md', 'web'); sync.commit(browser, 'web'); sync.push(browser)
        _write(self.s.vault_dir, 'a.md', 'edited, not committed')
        with pytest.raises(Vault__Serve_Error, match='uncommitted'):
            self.mirror.pull(self.s.vault_dir)

    def test_sent_objects_are_remembered(self, tmp_path):
        record = str(tmp_path / 'sent.json')
        first  = self.mirror.push(self.s.vault_dir, record_path=record)
        assert first['uploaded'] > 0
        self.local.list_files = lambda vault_id, prefix='': []                      # the server's list endpoint returns nothing (v0.34.0)
        assert self.mirror.push(self.s.vault_dir, record_path=record)['uploaded'] == 0
