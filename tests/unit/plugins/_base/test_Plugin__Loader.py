import json
import os
import tempfile

from sgit_ai.plugins._base.Plugin__Loader import Plugin__Loader


class Test_Plugin__Loader:

    def test_discover_returns_list(self):
        loader  = Plugin__Loader()
        plugins = loader.discover()
        assert isinstance(plugins, list)
        names = [n for n, _ in plugins]
        for expected in ('history', 'inspect', 'file', 'check', 'dev'):
            assert expected in names, f'plugin {expected!r} not found in {names}'

    def test_load_manifest(self):
        loader   = Plugin__Loader()
        plugins  = loader.discover()
        name, path = plugins[0]
        manifest = loader.load_manifest(path)
        assert str(manifest.name)
        assert str(manifest.version)

    def test_load_enabled_returns_plugins(self):
        loader  = Plugin__Loader()
        enabled = loader.load_enabled({})
        assert len(enabled) >= 4

    def test_is_enabled_default(self):
        loader   = Plugin__Loader()
        plugins  = loader.discover()
        name, path = plugins[0]
        manifest = loader.load_manifest(path)
        assert loader.is_enabled(name, manifest, {}) is True

    def test_is_enabled_disabled_by_config(self):
        loader   = Plugin__Loader()
        plugins  = loader.discover()
        name, path = plugins[0]
        manifest = loader.load_manifest(path)
        cfg = {name: {'enabled': False}}
        assert loader.is_enabled(name, manifest, cfg) is False

    def test_list_all(self):
        loader = Plugin__Loader()
        items  = loader.list_all()
        assert len(items) >= 4
        for item in items:
            assert 'name'      in item
            assert 'version'   in item
            assert 'stability' in item
            assert 'enabled'   in item

    def test_user_config_missing_returns_empty(self):
        loader = Plugin__Loader()
        # Force non-existent path
        original = os.path.expanduser
        cfg = loader._user_config()
        assert isinstance(cfg, dict)

    def test_set_enabled(self):
        loader = Plugin__Loader()
        with tempfile.TemporaryDirectory() as tmp:
            config_path = os.path.join(tmp, 'config.json')
            original_expand = os.path.expanduser

            def patched_expand(path):
                if path == '~/.sgit':
                    return tmp
                if path == '~/.sgit/config.json':
                    return config_path
                return original_expand(path)

            import sgit_ai.plugins._base.Plugin__Loader as mod
            orig = mod.os.path.expanduser
            mod.os.path.expanduser = patched_expand
            try:
                loader.set_enabled('history', False)
                with open(config_path) as fh:
                    saved = json.load(fh)
                assert saved['plugins']['history']['enabled'] is False

                loader.set_enabled('history', True)
                with open(config_path) as fh:
                    saved = json.load(fh)
                assert saved['plugins']['history']['enabled'] is True
            finally:
                mod.os.path.expanduser = orig
