"""0.20.0 field report, against the real SG/Send server (access-token middleware on).

doctor reported "401 — token rejected" with the token push was using (it sent the
token as Bearer only); history log on a read-only clone printed "(no commits)"."""
import json
import os
from types import SimpleNamespace

from sgit_ai.cli.CLI__Doctor       import CLI__Doctor
from sgit_ai.cli.CLI__Token_Store  import CLI__Token_Store
from sgit_ai.cli.CLI__Vault        import CLI__Vault
from sgit_ai.core.Vault__Sync      import Vault__Sync


class Test_Field_Report__0_20_0__Integration:

    def _pushed_vault(self, send_server, vault_api, crypto, temp_dir):
        sync      = Vault__Sync(crypto=crypto, api=vault_api)
        directory = os.path.join(temp_dir, 'vault')
        vault_key = sync.init(directory)['vault_key']
        with open(os.path.join(directory, 'a.md'), 'w') as f:
            f.write('a')
        sync.commit(directory, message='field report commit')
        sync.push(directory)
        store = CLI__Token_Store()
        store.save_token(send_server.access_token, directory)            # what `push --token` saves
        store.save_base_url(send_server.server_url, directory)
        return sync, directory, vault_key

    def test_doctor_passes_with_the_token_push_uses(self, send_server, vault_api, crypto, temp_dir, capsys):
        _, directory, _ = self._pushed_vault(send_server, vault_api, crypto, temp_dir)
        capsys.readouterr()
        args = SimpleNamespace(directory=directory, remote=None, json=True, timeout=5, write_probe=True,
                               token=None, base_url=None, verify_tls=None)
        CLI__Doctor().cmd_doctor(args)                                   # exits 1 on an overall FAIL
        out    = capsys.readouterr().out
        checks = {c['name']: c for c in json.loads(out[out.index('{'):])['checks']}
        assert checks['vault_known']['status']  == 'pass'
        assert checks['write_probe']['status']  == 'pass'
        assert checks['token_verify']['status'] != 'fail'
        assert checks['api_info']['status']     != 'fail'

    def test_read_only_clone_history_log(self, send_server, vault_api, crypto, temp_dir, capsys):
        _, directory, vault_key = self._pushed_vault(send_server, vault_api, crypto, temp_dir)
        keys   = crypto.derive_keys_from_vault_key(vault_key)
        ro_dir = os.path.join(temp_dir, 'ro')
        Vault__Sync(crypto=crypto, api=vault_api).clone_read_only(keys['vault_id'], keys['read_key'], ro_dir)
        capsys.readouterr()
        CLI__Vault().cmd_log(SimpleNamespace(directory=ro_dir, oneline=True, graph=False, limit=None, grep=None,
                                             since=None, until=None, author=None, stat=False, vault_key=None))
        out = capsys.readouterr().out
        assert 'field report commit' in out
        assert '(no commits)' not in out
