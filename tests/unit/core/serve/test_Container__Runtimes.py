"""`sgit serve` runtime layer: exact command lines per runtime, detection order, install plans."""
import os

import pytest

from sgit_ai.core.serve.Container__Command_Runner    import Container__Command_Runner
from sgit_ai.core.serve.Container__Host              import Container__Host
from sgit_ai.core.serve.Container__Runtime__Apple    import Container__Runtime__Apple
from sgit_ai.core.serve.Container__Runtime__Docker   import Container__Runtime__Docker
from sgit_ai.core.serve.Container__Runtime__Installer import Container__Runtime__Installer
from sgit_ai.core.serve.Container__Runtime__Uv       import Container__Runtime__Uv
from sgit_ai.core.serve.Container__Runtimes          import Container__Runtimes
from tests._helpers.fake_container_runtime           import Fake_Container_Runtime

SPEC = dict(image='diniscruz/sg-send-vault:latest', name='sgit-serve-abc', bind='127.0.0.1', host_port=8420,
            data_dir='/home/me/My Vault/.sg_vault/serve/data', user='1000:1000', env={})


def _host(system='linux', machine='x86_64', version='6.8', ids=True):
    return Container__Host(system=system, machine=machine, os_version=version, uid=1000, gid=1000, has_ids=ids)


class Test_Command_Lines:

    def test_docker_publishes_on_loopback_only_and_runs_as_the_host_user(self):
        argv = Container__Runtime__Docker(cli='docker', host=_host()).run_argv(SPEC)
        assert argv[:6] == ['docker', 'run', '-d', '--rm', '--name', 'sgit-serve-abc']
        assert argv[argv.index('-p') + 1] == '127.0.0.1:8420:8080'                     # never a bare 8420:8080
        assert argv[argv.index('--user') + 1] == '1000:1000'                           # the image runs as uid 10001
        assert argv[argv.index('-v') + 1] == '/home/me/My Vault/.sg_vault/serve/data:/data'   # one argv item: no shell
        assert argv[-1] == SPEC['image']

    def test_podman_maps_the_user_and_relabels_on_linux_only(self):
        linux = Container__Runtime__Docker(cli='podman', host=_host()).run_argv(SPEC)
        mac   = Container__Runtime__Docker(cli='podman', host=_host('darwin', 'arm64', '26.0')).run_argv(SPEC)
        assert '--userns=keep-id' in linux and '--userns=keep-id' in mac
        assert linux[linux.index('-v') + 1].endswith(':/data:Z')
        assert mac[mac.index('-v') + 1].endswith(':/data')

    def test_vm_runtimes_start_their_machine_first(self):
        assert Container__Runtime__Docker(cli='podman', host=_host('darwin')).start_service_argvs() == \
               [['podman', 'machine', 'init'], ['podman', 'machine', 'start']]
        assert Container__Runtime__Docker(cli='podman', host=_host()).start_service_argvs() == []
        assert Container__Runtime__Docker(cli='finch', host=_host('darwin')).start_service_argvs()[-1] == ['finch', 'vm', 'start']

    def test_no_user_flag_where_the_host_has_no_ids(self):
        argv = Container__Runtime__Docker(cli='docker', host=_host('windows', ids=False)).run_argv(dict(SPEC, user=''))
        assert '--user' not in argv

    def test_apple_container_commands(self):
        apple = Container__Runtime__Apple(host=_host('darwin', 'arm64', '26.0'))
        argv  = apple.run_argv(SPEC)
        assert argv[:4] == ['container', 'run', '-d', '--rm']
        assert argv[argv.index('-p') + 1] == '127.0.0.1:8420:8080'
        assert apple.pull_argv('img') == ['container', 'image', 'pull', 'img']
        assert apple.start_service_argvs() == [['container', 'system', 'start']]
        assert apple.remove_argv('n') == ['container', 'delete', '--force', 'n']

    def test_apple_container_applies_only_on_apple_silicon(self):
        assert Container__Runtime__Apple(host=_host('darwin', 'arm64', '26.0')).applies()
        assert not Container__Runtime__Apple(host=_host('darwin', 'x86_64', '15.0')).applies()
        assert not Container__Runtime__Apple(host=_host()).applies()

    def test_uv_engine_runs_the_server_package_with_python_3_12(self):
        uv   = Container__Runtime__Uv(host=_host())
        argv = uv.run_argv(SPEC)
        assert argv[:6] == ['uv', 'run', '--no-project', '--python', '3.12', '--with']
        assert 'sgraph-ai-app-send' in argv and argv[-2:] == ['127.0.0.1', '8420']
        env = uv.server_env(dict(SPEC, ui_dir='/ui'))
        assert env['SEND__STORAGE_MODE'] == 'disk' and env['SEND__DISK_PATH'] == SPEC['data_dir']
        assert env['SEND__STORAGE_BASE'] == ''                                         # the image's flat layout


class Test_Detection:

    def _runtimes(self, monkeypatch, tmp_path, names, host=None):
        fake = Fake_Container_Runtime(str(tmp_path / 'bin'), str(tmp_path / 'home'), names)
        monkeypatch.setenv('PATH', fake.bin_dir)
        return fake, Container__Runtimes(runner=Container__Command_Runner(), host=host or _host())

    def test_order_per_os(self):
        assert [r.name() for r in Container__Runtimes(host=_host('darwin', 'arm64', '26.0')).all()] == \
               ['container', 'docker', 'podman', 'nerdctl', 'finch', 'uv']
        assert [r.name() for r in Container__Runtimes(host=_host()).all()] == ['docker', 'podman', 'nerdctl', 'finch', 'uv']
        assert [r.name() for r in Container__Runtimes(host=_host('windows', ids=False)).all()] == ['docker', 'podman', 'uv']

    def test_the_first_answering_runtime_wins(self, monkeypatch, tmp_path):
        fake, runtimes = self._runtimes(monkeypatch, tmp_path, ['podman'])
        assert runtimes.pick().name() == 'podman'

    def test_an_installed_but_stopped_docker_is_passed_over(self, monkeypatch, tmp_path):
        fake, runtimes = self._runtimes(monkeypatch, tmp_path, ['docker'])
        fake.flag('info.fail')
        assert runtimes.pick() is None
        with pytest.raises(ValueError, match='daemon is not running'):
            runtimes.pick('docker')

    def test_nothing_installed(self, monkeypatch, tmp_path):
        fake, runtimes = self._runtimes(monkeypatch, tmp_path, [])
        assert runtimes.pick() is None
        with pytest.raises(ValueError, match='not installed: sgit serve install docker'):
            runtimes.pick('docker')
        with pytest.raises(ValueError, match='unknown runtime'):
            runtimes.pick('kubernetes')

    def test_a_container_runtime_beats_uv(self, monkeypatch, tmp_path):
        fake, runtimes = self._runtimes(monkeypatch, tmp_path, ['uv', 'podman'])
        assert runtimes.pick().name() == 'podman'

    def test_report_lists_every_runtime(self, monkeypatch, tmp_path):
        fake, runtimes = self._runtimes(monkeypatch, tmp_path, ['docker'])
        rows = {r['name']: r for r in runtimes.report()}
        assert rows['docker']['installed'] and rows['docker']['ready']
        assert not rows['podman']['installed']


class Test_Install_Plans:

    def test_recommendations(self):
        assert Container__Runtime__Installer(host=_host('darwin', 'arm64', '26.0')).recommended()[:2] == ['container', 'podman']
        assert Container__Runtime__Installer(host=_host('darwin', 'x86_64', '15.0')).recommended()[0] == 'podman'
        assert Container__Runtime__Installer(host=_host()).recommended()[0] == 'podman'

    def test_a_plan_says_what_where_licence_and_every_command(self, monkeypatch):
        monkeypatch.setattr(Container__Host, 'package_manager', lambda self: 'apt-get')
        installer = Container__Runtime__Installer(host=_host())
        plan      = installer.plan('podman')
        assert plan['commands'] == [['sudo', 'apt-get', 'install', '-y', 'podman']] and plan['admin']
        text = '\n'.join(installer.describe(plan))
        assert 'Licence: Apache-2.0' in text and '$ sudo apt-get install -y podman' in text and 'password' in text

    def test_docker_desktop_and_apple_container_are_refused_where_they_do_not_apply(self):
        with pytest.raises(ValueError, match='licence'):
            Container__Runtime__Installer(host=_host('darwin', 'arm64', '26.0')).plan('docker')
        with pytest.raises(ValueError, match='Apple silicon'):
            Container__Runtime__Installer(host=_host()).plan('container')

    def test_a_release_that_cannot_be_looked_up_is_never_guessed(self):
        with pytest.raises(ValueError, match='could not look up'):
            Container__Runtime__Installer().require_release(dict(version='', asset='', url='', size_mb=''), 'page')

    def test_execute_stops_at_the_first_failing_step(self, tmp_path):
        marker = tmp_path / 'ran'
        plan   = dict(commands=[['true'], ['false'], ['touch', str(marker)]])
        assert Container__Runtime__Installer().execute(plan) != 0
        assert not marker.exists()

    def test_windows_podman_and_uv(self):
        win = Container__Runtime__Installer(host=_host('windows', ids=False))
        assert win.plan('podman')['commands'][0][:2] == ['winget', 'install']
        assert win.plan('uv')['commands'][0][0] == 'powershell'
        assert Container__Runtime__Installer(host=_host()).plan('uv')['admin'] is False
