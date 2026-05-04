import json
import sys

from osbot_utils.type_safe.Type_Safe  import Type_Safe
from sgit_ai.network.api.Vault__API           import Vault__API
from sgit_ai.cli.CLI__Token_Store     import CLI__Token_Store
from sgit_ai.crypto.Vault__Crypto     import Vault__Crypto
from sgit_ai.core.actions.dump.Vault__Dump         import Vault__Dump
from sgit_ai.storage.Vault__Storage      import Vault__Storage


class CLI__Dump(Type_Safe):
    """CLI handler for 'sgit-ai dump' and 'sgit-ai dump-diff' commands."""

    crypto      : Vault__Crypto
    token_store : CLI__Token_Store
    api         : object          = None   # optional API override (used in tests)

    def cmd_dump(self, args):
        """Produce a complete structural dump of a local or remote vault."""
        directory      = getattr(args, 'directory', '.') or '.'
        use_remote     = getattr(args, 'remote',    False)
        struct_key_hex = getattr(args, 'structure_key', None)
        output_file    = getattr(args, 'output',    None)

        dumper = Vault__Dump(crypto=self.crypto)

        try:
            if use_remote:
                storage   = Vault__Storage()
                vault_key = self._read_vault_key(directory, storage)
                keys      = self.crypto.derive_keys_from_vault_key(vault_key)
                vault_id  = keys['vault_id']
                read_key  = keys['read_key_bytes']
                token     = self.token_store.resolve_token(getattr(args, 'token', None), directory)
                base_url  = self.token_store.resolve_base_url(getattr(args, 'base_url', None), directory)
                if self.api is not None:
                    api = self.api
                else:
                    api = Vault__API(base_url=base_url or '', access_token=token or '')
                    api.setup()
                result    = dumper.dump_remote(api, vault_id, read_key)

            elif struct_key_hex:
                try:
                    structure_key = bytes.fromhex(struct_key_hex)
                except ValueError:
                    print('error: --structure-key must be a hex string (64 hex chars)',
                          file=sys.stderr)
                    sys.exit(1)
                result = dumper.dump_with_structure_key(directory, structure_key)
            else:
                result = dumper.dump_local(directory)

        except FileNotFoundError as exc:
            print(f'error: {exc}', file=sys.stderr)
            sys.exit(1)
        except RuntimeError as exc:
            print(f'error: {exc}', file=sys.stderr)
            sys.exit(1)

        output_data = json.dumps(result.json(), indent=2)

        if output_file:
            with open(output_file, 'w') as fh:
                fh.write(output_data)
            print(f'Dump written to {output_file}')
        else:
            print(output_data)

    def cmd_dump_diff(self, args):
        """Compare two dump snapshots and report divergences."""
        from sgit_ai.core.actions.diff.Vault__Dump_Diff import Vault__Dump_Diff

        file_a   = getattr(args, 'dump_a',   None)
        file_b   = getattr(args, 'dump_b',   None)
        use_local  = getattr(args, 'local',  False)
        use_remote = getattr(args, 'remote', False)
        directory  = getattr(args, 'directory', '.') or '.'

        diff_engine = Vault__Dump_Diff()
        dumper      = Vault__Dump(crypto=self.crypto)

        try:
            # -- two-file mode --
            if file_a and file_b:
                diff_result = diff_engine.diff_from_files(file_a, file_b)

            # -- inline mode: produce dumps on the fly then diff --
            elif use_local and use_remote:
                local_dump  = dumper.dump_local(directory)
                print('error: --remote dump not yet implemented', file=sys.stderr)
                sys.exit(1)

            else:
                print('error: provide either two dump files (DUMP_A DUMP_B) or '
                      '--local --remote', file=sys.stderr)
                sys.exit(1)

        except FileNotFoundError as exc:
            print(f'error: {exc}', file=sys.stderr)
            sys.exit(1)
        except RuntimeError as exc:
            print(f'error: {exc}', file=sys.stderr)
            sys.exit(1)

        self._print_diff(diff_result)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _print_diff(self, diff_result) -> None:
        label_a = str(diff_result.label_a) if diff_result.label_a else 'A'
        label_b = str(diff_result.label_b) if diff_result.label_b else 'B'
        print(f'Comparing: {label_a}  vs  {label_b}')
        print()

        if diff_result.identical:
            print('No differences found — dumps are identical.')
            return

        total = int(diff_result.total_diffs)

        # Refs
        for ref_id in diff_result.refs_only_in_a:
            print(f'  ref only in {label_a}: {ref_id}')
        for ref_id in diff_result.refs_only_in_b:
            print(f'  ref only in {label_b}: {ref_id}')
        for ref_id in diff_result.refs_diverged:
            print(f'  ref diverged: {ref_id}')

        # Objects
        for oid in diff_result.objects_only_in_a:
            print(f'  object only in {label_a}: {oid}')
        for oid in diff_result.objects_only_in_b:
            print(f'  object only in {label_b}: {oid}')

        # Branches
        for bid in diff_result.branches_only_in_a:
            print(f'  branch only in {label_a}: {bid}')
        for bid in diff_result.branches_only_in_b:
            print(f'  branch only in {label_b}: {bid}')
        for bid in diff_result.branches_head_differ:
            print(f'  branch head differs: {bid}')

        # Dangling objects
        for oid in diff_result.dangling_in_a:
            print(f'  dangling in {label_a}: {oid}')
        for oid in diff_result.dangling_in_b:
            print(f'  dangling in {label_b}: {oid}')

        # Commits
        for cid in diff_result.commits_only_in_a:
            print(f'  commit only in {label_a}: {cid}')
        for cid in diff_result.commits_only_in_b:
            print(f'  commit only in {label_b}: {cid}')

        print()
        print(f'Total differences: {total}')

    def _read_vault_key(self, directory: str, storage: Vault__Storage) -> str:
        vault_key_path = storage.vault_key_path(directory)
        with open(vault_key_path, 'r') as f:
            return f.read().strip()
