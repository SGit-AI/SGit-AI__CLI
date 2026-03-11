import sys
import time
from osbot_utils.type_safe.Type_Safe     import Type_Safe
from sg_send_cli.crypto.Vault__Crypto    import Vault__Crypto
from sg_send_cli.api.Vault__API          import Vault__API
from sg_send_cli.sync.Vault__Sync        import Vault__Sync
from sg_send_cli.objects.Vault__Inspector import Vault__Inspector
from sg_send_cli.cli.CLI__Token_Store    import CLI__Token_Store


class CLI__Vault(Type_Safe):
    token_store : CLI__Token_Store

    def create_sync(self, base_url: str = None, access_token: str = None) -> Vault__Sync:
        api = Vault__API(base_url=base_url or '', access_token=access_token or '')
        api.setup()
        return Vault__Sync(crypto=Vault__Crypto(), api=api)

    def cmd_init(self, args):
        if not args.token:
            print('Error: --token is required for init (needed to write to the remote vault).', file=sys.stderr)
            sys.exit(1)
        sync      = self.create_sync(args.base_url, args.token)
        vault_key = getattr(args, 'vault_key', None) or None
        result    = sync.init(args.directory, vault_key=vault_key)
        self.token_store.save_token(args.token, result['directory'])
        print(f'Initialized empty vault in {result["directory"]}/')
        print(f'  Vault ID:  {result["vault_id"]}')
        print(f'  Vault key: {result["vault_key"]}')
        print()
        print('Save your vault key — you need it to clone this vault on another machine.')

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f'{size_bytes} B'
        elif size_bytes < 1024 * 1024:
            return f'{size_bytes / 1024:.1f} KB'
        elif size_bytes < 1024 * 1024 * 1024:
            return f'{size_bytes / (1024 * 1024):.1f} MB'
        else:
            return f'{size_bytes / (1024 * 1024 * 1024):.1f} GB'

    def _progress_bar(self, current: int, total: int, width: int = 30) -> str:
        filled = int(width * current / total) if total > 0 else 0
        bar    = '█' * filled + '░' * (width - filled)
        pct    = int(100 * current / total) if total > 0 else 0
        return f'[{bar}] {pct}%'

    def _clone_progress(self, event: str, detail: str = None, info: dict = None):
        info = info or {}
        if event == 'metadata':
            print(f'🔑 {detail}')
        elif event == 'tree_resolved':
            total = info.get('total_files', 0)
            name  = info.get('vault_name', '???')
            ver   = info.get('version', '?')
            print(f'📦 Vault: {name} (version {ver})')
            print(f'📂 Receiving {total} file{"s" if total != 1 else ""}...')
            print()
        elif event == 'file':
            idx   = info.get('index', 0)
            total = info.get('total', 0)
            size  = info.get('size', 0)
            bar   = self._progress_bar(idx, total)
            line  = f'\r   {bar}  ({idx}/{total})  {self._format_size(size):>8}  {detail}'
            if len(line) > 100:
                line = line[:97] + '...'
            sys.stdout.write(f'{line:<100}')
            sys.stdout.flush()
            if idx == total:
                print()
        elif event == 'done':
            total_files = info.get('total_files', 0)
            total_bytes = info.get('total_bytes', 0)
            commit_id   = info.get('commit_id', '???')
            version     = info.get('version', '?')
            elapsed     = time.time() - self._clone_start_time
            rows = [('Files'  , str(total_files)                ),
                    ('Size'   , self._format_size(total_bytes)  ),
                    ('Version', str(version)                    ),
                    ('Commit' , str(commit_id)                  ),
                    ('Time'   , f'{elapsed:.1f}s'               )]
            label_w = max(len(r[0]) for r in rows)
            value_w = max(len(r[1]) for r in rows)
            inner_w = label_w + 2 + value_w
            box_w   = inner_w + 4
            print()
            print(f'✅ Clone complete!')
            print()
            print(f'   ┌{"─" * box_w}┐')
            print(f'   │  {"Summary":<{inner_w}}  │')
            print(f'   ├{"─" * box_w}┤')
            for label, value in rows:
                print(f'   │  {label + ":":<{label_w + 1}} {value:<{value_w}}  │')
            print(f'   └{"─" * box_w}┘')

    def cmd_clone(self, args):
        sync = self.create_sync(args.base_url, args.token)
        print()
        print(f'🔒 sg-send-cli clone')
        print(f'   ─────────────────')
        self._clone_start_time = time.time()
        directory = sync.clone(args.vault_key, args.directory, on_progress=self._clone_progress)
        if args.token:
            self.token_store.save_token(args.token, directory)
        print(f'   📁 Cloned to {directory}/')

    def cmd_pull(self, args):
        token  = self.token_store.resolve_token(args.token, args.directory)
        sync   = self.create_sync(args.base_url, token)
        result = sync.pull(args.directory)
        added    = len(result['added'])
        modified = len(result['modified'])
        deleted  = len(result['deleted'])
        if added + modified + deleted == 0:
            print('Already up to date.')
        else:
            for f in result['added']:
                print(f'  + {f}')
            for f in result['modified']:
                print(f'  ~ {f}')
            for f in result['deleted']:
                print(f'  - {f}')
            print(f'Pulled: {added} added, {modified} modified, {deleted} deleted')

    def cmd_push(self, args):
        token  = self.token_store.resolve_token(args.token, args.directory)
        sync   = self.create_sync(args.base_url, token)
        result = sync.push(args.directory)
        added    = len(result['added'])
        modified = len(result['modified'])
        deleted  = len(result['deleted'])
        if added + modified + deleted == 0:
            print('Nothing to push — vault is up to date.')
        else:
            if added:
                for f in sorted(result['added']):
                    print(f'  + {f}')
            if modified:
                for f in sorted(result['modified']):
                    print(f'  ~ {f}')
            if deleted:
                for f in sorted(result['deleted']):
                    print(f'  - {f}')
            print(f'Pushed: {added} added, {modified} modified, {deleted} deleted')

    def cmd_status(self, args):
        if getattr(args, 'remote', False):
            self.cmd_remote_status(args)
            return
        sync   = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API())
        result = sync.status(args.directory)
        if result['clean']:
            print('Vault is clean — no local changes.')
        else:
            for f in result['added']:
                print(f'  + {f}')
            for f in result['modified']:
                print(f'  ~ {f}')
            for f in result['deleted']:
                print(f'  - {f}')

    def cmd_remote_status(self, args):
        token  = self.token_store.resolve_token(args.token, args.directory)
        sync   = self.create_sync(args.base_url, token)
        result = sync.remote_status(args.directory)

        remote_changes = result['remote_added'] or result['remote_modified'] or result['remote_deleted']
        local_changes  = result['local_added'] or result['local_modified'] or result['local_deleted']

        print(f'Local version:  {result["local_version"]}')
        print(f'Remote version: {result["remote_version"]}')
        print()

        if remote_changes:
            print('Remote changes (not yet pulled):')
            for f in result['remote_added']:
                print(f'  + {f}')
            for f in result['remote_modified']:
                print(f'  ~ {f}')
            for f in result['remote_deleted']:
                print(f'  - {f}')
        else:
            print('Remote: up to date.')

        if local_changes:
            print('Local changes (not yet pushed):')
            for f in result['local_added']:
                print(f'  + {f}')
            for f in result['local_modified']:
                print(f'  ~ {f}')
            for f in result['local_deleted']:
                print(f'  - {f}')
        else:
            print('Local: clean.')

    def cmd_derive_keys(self, args):
        crypto = Vault__Crypto()
        keys   = crypto.derive_keys_from_vault_key(args.vault_key)
        print(f'vault_id:         {keys["vault_id"]}')
        print(f'read_key:         {keys["read_key"]}')
        print(f'write_key:        {keys["write_key"]}')
        print(f'tree_file_id:     {keys["tree_file_id"]}')
        print(f'settings_file_id: {keys["settings_file_id"]}')
        print(f'ref_file_id:      {keys["ref_file_id"]}')

    def cmd_inspect(self, args):
        inspector = Vault__Inspector(crypto=Vault__Crypto())
        print(inspector.format_vault_summary(args.directory))

    def cmd_inspect_object(self, args):
        inspector = Vault__Inspector(crypto=Vault__Crypto())
        print(inspector.format_object_detail(args.directory, args.object_id))

    def cmd_inspect_tree(self, args):
        inspector = Vault__Inspector(crypto=Vault__Crypto())
        read_key  = self.token_store.resolve_read_key(args)
        result    = inspector.inspect_tree(args.directory, read_key=read_key)
        if result.get('error'):
            print(f'Error: {result["error"]}')
            return
        if not result.get('entries'):
            print('(no tree entries)')
            return
        print(f'Tree from commit {result["commit_id"]} (tree {result["tree_id"]})')
        print(f'  {result["file_count"]} files, {result["total_size"]} bytes total')
        print()
        for entry in result['entries']:
            print(f'  {entry["blob_id"]}  {entry["size"]:>8}  {entry["path"]}')

    def cmd_inspect_log(self, args):
        inspector = Vault__Inspector(crypto=Vault__Crypto())
        read_key  = self.token_store.resolve_read_key(args)
        chain     = inspector.inspect_commit_chain(args.directory, read_key=read_key)
        oneline   = getattr(args, 'oneline', False)
        graph     = getattr(args, 'graph', False)
        print(inspector.format_commit_log(chain, oneline=oneline, graph=graph))

    def cmd_cat_object(self, args):
        crypto    = Vault__Crypto()
        inspector = Vault__Inspector(crypto=crypto)
        read_key  = self.token_store.resolve_read_key(args)
        if not read_key:
            print('Error: no vault key found. Provide --vault-key or run from a vault directory.', file=sys.stderr)
            sys.exit(1)
        print(inspector.format_cat_object(args.directory, args.object_id, read_key))

    def cmd_inspect_stats(self, args):
        inspector = Vault__Inspector(crypto=Vault__Crypto())
        stats     = inspector.object_store_stats(args.directory)
        print(f'=== Object Store Stats ===')
        print(f'  Total objects: {stats["total_objects"]}')
        print(f'  Total size:    {stats["total_bytes"]} bytes')
        if stats['buckets']:
            print(f'  Buckets:')
            for prefix, count in sorted(stats['buckets'].items()):
                print(f'    {prefix}/ : {count} objects')

    def cmd_log(self, args):
        self.cmd_inspect_log(args)
