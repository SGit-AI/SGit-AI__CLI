"""Tests for `sgit dev plugins list/show/enable/disable`."""
import json
import os
import sys
import tempfile

from sgit_ai.cli.CLI__Main import CLI__Main


def _run(argv):
    cli    = CLI__Main()
    parser = cli.build_parser()
    return parser.parse_args(argv)


class Test_Plugin__Dev__Plugins_Cmds:

    def test_plugins_list_parses(self):
        args = _run(['dev', 'plugins', 'list'])
        assert args.command    == 'dev'
        assert args.dev_command == 'plugins'

    def test_plugins_show_parses(self):
        args = _run(['dev', 'plugins', 'show', 'history'])
        assert args.name == 'history'

    def test_plugins_enable_parses(self):
        args = _run(['dev', 'plugins', 'enable', 'inspect'])
        assert args.name == 'inspect'

    def test_plugins_disable_parses(self):
        args = _run(['dev', 'plugins', 'disable', 'check'])
        assert args.name == 'check'

    def test_plugins_list_output(self, capsys):
        cli  = CLI__Main()
        args = _run(['dev', 'plugins', 'list'])
        cli.plugin_loader.load_enabled({})
        args.json = False
        from sgit_ai.plugins.dev.CLI__Dev import CLI__Dev
        dev       = CLI__Dev()
        dev.vault_ref = cli.vault
        dev.dump_ref  = cli.dump
        dev.main_ref  = cli
        dev.cmd_plugins_list(args)
        out = capsys.readouterr().out
        assert 'history' in out
        assert 'inspect' in out
        assert 'check'   in out

    def test_plugins_list_json_output(self, capsys):
        from sgit_ai.plugins.dev.CLI__Dev import CLI__Dev
        cli = CLI__Main()
        dev = CLI__Dev()
        dev.vault_ref = cli.vault
        dev.dump_ref  = cli.dump
        dev.main_ref  = cli

        import argparse
        args      = argparse.Namespace()
        args.json = True
        dev.cmd_plugins_list(args)
        out  = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)
        names = [item['name'] for item in data]
        assert 'history' in names

    def test_plugins_show_valid(self, capsys):
        from sgit_ai.plugins.dev.CLI__Dev import CLI__Dev
        import argparse
        dev       = CLI__Dev()
        args      = argparse.Namespace()
        args.name = 'history'
        dev.cmd_plugins_show(args)
        out  = capsys.readouterr().out
        data = json.loads(out)
        assert data.get('name') == 'history'

    def test_plugins_enable_disable(self):
        from sgit_ai.plugins._base.Plugin__Loader import Plugin__Loader
        import sgit_ai.plugins._base.Plugin__Loader as mod
        import argparse

        with tempfile.TemporaryDirectory() as tmp:
            config_path = os.path.join(tmp, 'config.json')
            orig = mod.os.path.expanduser

            def patch(p):
                if p == '~/.sgit':
                    return tmp
                if p == '~/.sgit/config.json':
                    return config_path
                return orig(p)

            mod.os.path.expanduser = patch
            try:
                from sgit_ai.plugins.dev.CLI__Dev import CLI__Dev
                dev  = CLI__Dev()
                args = argparse.Namespace()
                args.name = 'history'
                dev.cmd_plugins_disable(args)
                loader = Plugin__Loader()
                cfg    = loader._user_config()
                assert cfg.get('history', {}).get('enabled') is False

                dev.cmd_plugins_enable(args)
                cfg = loader._user_config()
                assert cfg.get('history', {}).get('enabled') is True
            finally:
                mod.os.path.expanduser = orig
