import importlib
import json
import os

from osbot_utils.type_safe.Type_Safe                          import Type_Safe
from sgit_ai.plugins._base.Schema__Plugin_Manifest import Schema__Plugin_Manifest

_PLUGINS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Plugin__Loader(Type_Safe):

    def _plugins_dir(self) -> str:
        return _PLUGINS_DIR

    def _user_config(self) -> dict:
        config_path = os.path.expanduser('~/.sgit/config.json')
        if os.path.isfile(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                return data.get('plugins', {})
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_user_config_plugins(self, plugins_cfg: dict):
        config_dir  = os.path.expanduser('~/.sgit')
        config_path = os.path.join(config_dir, 'config.json')
        os.makedirs(config_dir, exist_ok=True)
        existing = {}
        if os.path.isfile(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as fh:
                    existing = json.load(fh)
            except (json.JSONDecodeError, OSError):
                pass
        existing['plugins'] = plugins_cfg
        with open(config_path, 'w', encoding='utf-8') as fh:
            json.dump(existing, fh, indent=2)

    def discover(self) -> list:
        """Return list of (name, manifest_path) for all installed plugins."""
        plugins_dir = self._plugins_dir()
        found = []
        if not os.path.isdir(plugins_dir):
            return found
        for entry in sorted(os.listdir(plugins_dir)):
            if entry.startswith('_'):
                continue
            manifest_path = os.path.join(plugins_dir, entry, 'plugin.json')
            if os.path.isfile(manifest_path):
                found.append((entry, manifest_path))
        return found

    def load_manifest(self, manifest_path: str) -> Schema__Plugin_Manifest:
        with open(manifest_path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        m = Schema__Plugin_Manifest()
        m.name      = data.get('name', '')
        m.version   = data.get('version', '0.0.1')
        m.stability = data.get('stability', 'stable')
        m.commands  = data.get('commands', [])
        m.enabled   = data.get('enabled', True)
        return m

    def is_enabled(self, name: str, manifest: Schema__Plugin_Manifest, user_cfg: dict) -> bool:
        plugin_cfg = user_cfg.get(name, {})
        if not plugin_cfg.get('enabled', True):
            return False
        stability_required = plugin_cfg.get('stability_required', 'stable')
        stability_order    = {'stable': 0, 'experimental': 1, 'deprecated': 2}
        plugin_stability   = stability_order.get(str(manifest.stability), 0)
        required_stability = stability_order.get(stability_required, 0)
        return plugin_stability <= required_stability

    def load_enabled(self, context: dict = None) -> list:
        """Discover all plugins, filter by config, instantiate enabled ones."""
        if context is None:
            context = {}
        user_cfg  = self._user_config()
        instances = []
        for name, manifest_path in self.discover():
            manifest = self.load_manifest(manifest_path)
            if not self.is_enabled(name, manifest, user_cfg):
                continue
            try:
                module  = importlib.import_module(f'sgit_ai.plugins.{name}.Plugin__{name.capitalize()}')
                cls_name = f'Plugin__{name.capitalize()}'
                cls     = getattr(module, cls_name)
                plugin  = cls(manifest=manifest)
                instances.append(plugin)
            except (ImportError, AttributeError):
                pass
        return instances

    def list_all(self) -> list:
        """Return list of dicts with name/version/stability/enabled for display."""
        user_cfg = self._user_config()
        result   = []
        for name, manifest_path in self.discover():
            manifest = self.load_manifest(manifest_path)
            enabled  = self.is_enabled(name, manifest, user_cfg)
            result.append({
                'name'      : name,
                'version'   : str(manifest.version),
                'stability' : str(manifest.stability),
                'enabled'   : enabled,
            })
        return result

    def set_enabled(self, name: str, enabled: bool):
        plugins_cfg = self._user_config()
        if name not in plugins_cfg:
            plugins_cfg[name] = {}
        plugins_cfg[name]['enabled'] = enabled
        self._save_user_config_plugins(plugins_cfg)
