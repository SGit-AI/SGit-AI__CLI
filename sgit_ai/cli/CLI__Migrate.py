"""CLI__Migrate — sgit migrate plan / apply / status."""
import os
from osbot_utils.type_safe.Type_Safe import Type_Safe
from sgit_ai.migrations.Migration__Registry import Migration__Registry
from sgit_ai.migrations.Migration__Runner   import Migration__Runner


class CLI__Migrate(Type_Safe):

    def _runner(self):
        return Migration__Runner(registry=Migration__Registry())

    def _vault_dir(self, args) -> str:
        return getattr(args, 'directory', None) or '.'

    def _read_key(self, vault_dir: str) -> bytes:
        from sgit_ai.core.Vault__Sync import Vault__Sync
        from sgit_ai.crypto.Vault__Crypto import Vault__Crypto
        sync      = Vault__Sync(crypto=Vault__Crypto())
        vault_key = sync._read_vault_key(vault_dir)
        keys      = sync._derive_keys_from_stored_key(vault_key)
        return bytes.fromhex(keys['read_key'])

    def cmd_migrate_plan(self, args):
        vault_dir = self._vault_dir(args)
        read_key  = self._read_key(vault_dir)
        pending   = self._runner().plan(vault_dir, read_key)
        if not pending:
            print('No pending migrations.')
        else:
            print('Pending migrations:')
            for name in pending:
                print(f'  - {name}')

    def cmd_migrate_apply(self, args):
        vault_dir = self._vault_dir(args)
        read_key  = self._read_key(vault_dir)
        done      = self._runner().apply(vault_dir, read_key)
        if not done:
            print('Nothing to migrate — vault is already up to date.')
        else:
            for name in done:
                print(f'Applied: {name}')

    def cmd_migrate_status(self, args):
        vault_dir = self._vault_dir(args)
        records   = self._runner().status(vault_dir)
        if not records:
            print('No migrations applied.')
        else:
            for r in records:
                print(f"  {r['name']}  applied={r.get('applied_at','')}  "
                      f"trees={r.get('n_trees',0)}  commits={r.get('n_commits',0)}")
