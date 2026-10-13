"""`sgit serve` command surface: top-level `serve` with its actions, `--static` for a published
vault, and `sgit vault serve` moved (rule 9: the old name runs nothing and says where it went)."""
import pytest

from sgit_ai.cli.CLI__Main import CLI__Main


class Test_CLI__Serve__Commands:

    def _parse(self, *argv):
        return CLI__Main().build_parser().parse_args(list(argv))

    def test_serve_and_its_actions(self):
        assert self._parse('serve').func.__name__ == 'cmd_serve'
        for action in ('stop', 'status', 'logs', 'update', 'push', 'pull', 'runtimes', 'install'):
            assert self._parse('serve', action).func.__name__ == f'cmd_{action}'
        args = self._parse('serve', '--runtime', 'podman', '--port', '9000', '--data', '/tmp/d')
        assert (args.runtime, args.port, args.data, args.bind) == ('podman', 9000, '/tmp/d', '127.0.0.1')
        assert self._parse('serve', 'install', 'container', '--yes').runtime == 'container'

    def test_static_mode(self):
        assert self._parse('serve', '--static').static == ''
        assert self._parse('serve', '--static', 'published').static == 'published'
        assert self._parse('serve').static is None

    def test_vault_serve_moved(self, capsys):
        with pytest.raises(SystemExit) as exit_:
            CLI__Main().run(['vault', 'serve'])
        assert exit_.value.code == 2
        assert "'vault serve' is now 'sgit serve --static'" in capsys.readouterr().err
