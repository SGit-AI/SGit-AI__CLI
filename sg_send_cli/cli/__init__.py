import argparse
import os
import sys
from sg_send_cli.crypto.Vault__Crypto        import Vault__Crypto
from sg_send_cli.api.Vault__API              import Vault__API
from sg_send_cli.sync.Vault__Sync            import Vault__Sync
from sg_send_cli.sync.Vault__Legacy_Guard    import Legacy_Vault_Error
from sg_send_cli.objects.Vault__Inspector    import Vault__Inspector

TOKEN_FILE = 'token'


def _resolve_token(token: str, directory: str) -> str:
    if token:
        _save_token(token, directory)
        return token
    return _load_token(directory)


def _save_token(token: str, directory: str):
    sg_vault_dir = os.path.join(directory, '.sg_vault')
    if os.path.isdir(sg_vault_dir):
        token_path = os.path.join(sg_vault_dir, TOKEN_FILE)
        with open(token_path, 'w') as f:
            f.write(token)


def _load_token(directory: str) -> str:
    token_path = os.path.join(directory, '.sg_vault', TOKEN_FILE)
    if os.path.isfile(token_path):
        with open(token_path, 'r') as f:
            return f.read().strip()
    return ''


def create_sync(base_url: str = None, access_token: str = None) -> Vault__Sync:
    api = Vault__API(base_url=base_url or '', access_token=access_token or '')
    api.setup()
    return Vault__Sync(crypto=Vault__Crypto(), api=api)


def cmd_init(args):
    if not args.token:
        print('Error: --token is required for init (needed to write to the remote vault).', file=sys.stderr)
        sys.exit(1)
    sync      = create_sync(args.base_url, args.token)
    vault_key = getattr(args, 'vault_key', None) or None
    result    = sync.init(args.directory, vault_key=vault_key)
    _save_token(args.token, result['directory'])
    print(f'Initialized empty vault in {result["directory"]}/')
    print(f'  Vault ID:  {result["vault_id"]}')
    print(f'  Vault key: {result["vault_key"]}')
    print()
    print('Save your vault key — you need it to clone this vault on another machine.')


def cmd_clone(args):
    sync      = create_sync(args.base_url, args.token)
    directory = sync.clone(args.vault_key, args.directory)
    if args.token:
        _save_token(args.token, directory)
    print(f'Cloned vault to {directory}/')


def cmd_pull(args):
    token  = _resolve_token(args.token, args.directory)
    sync   = create_sync(args.base_url, token)
    result = sync.pull(args.directory)
    added  = len(result['added'])
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


def cmd_push(args):
    token  = _resolve_token(args.token, args.directory)
    sync   = create_sync(args.base_url, token)
    result = sync.push(args.directory)
    added  = len(result['added'])
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


def cmd_status(args):
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


def cmd_remote_status(args):
    token  = _resolve_token(args.token, args.directory)
    sync   = create_sync(args.base_url, token)
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


def cmd_derive_keys(args):
    crypto = Vault__Crypto()
    keys   = crypto.derive_keys_from_vault_key(args.vault_key)
    print(f'vault_id:         {keys["vault_id"]}')
    print(f'read_key:         {keys["read_key"]}')
    print(f'write_key:        {keys["write_key"]}')
    print(f'tree_file_id:     {keys["tree_file_id"]}')
    print(f'settings_file_id: {keys["settings_file_id"]}')
    print(f'ref_file_id:      {keys["ref_file_id"]}')


def cmd_inspect(args):
    inspector = Vault__Inspector(crypto=Vault__Crypto())
    print(inspector.format_vault_summary(args.directory))


def _load_vault_key(directory: str) -> str:
    vault_key_path = os.path.join(directory, '.sg_vault', 'VAULT-KEY')
    if os.path.isfile(vault_key_path):
        with open(vault_key_path, 'r') as f:
            return f.read().strip()
    return ''


def _resolve_read_key(args) -> bytes:
    vault_key = getattr(args, 'vault_key', None)
    if not vault_key:
        directory = getattr(args, 'directory', '.')
        vault_key = _load_vault_key(directory)
    if not vault_key:
        return None
    crypto = Vault__Crypto()
    keys   = crypto.derive_keys_from_vault_key(vault_key)
    return keys['read_key_bytes']


def cmd_inspect_object(args):
    inspector = Vault__Inspector(crypto=Vault__Crypto())
    print(inspector.format_object_detail(args.directory, args.object_id))


def cmd_inspect_tree(args):
    inspector = Vault__Inspector(crypto=Vault__Crypto())
    read_key  = _resolve_read_key(args)
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


def cmd_inspect_log(args):
    inspector = Vault__Inspector(crypto=Vault__Crypto())
    read_key  = _resolve_read_key(args)
    chain     = inspector.inspect_commit_chain(args.directory, read_key=read_key)
    oneline   = getattr(args, 'oneline', False)
    graph     = getattr(args, 'graph', False)
    print(inspector.format_commit_log(chain, oneline=oneline, graph=graph))


def cmd_cat_object(args):
    crypto    = Vault__Crypto()
    inspector = Vault__Inspector(crypto=crypto)
    read_key  = _resolve_read_key(args)
    if not read_key:
        print('Error: no vault key found. Provide --vault-key or run from a vault directory.', file=sys.stderr)
        sys.exit(1)
    print(inspector.format_cat_object(args.directory, args.object_id, read_key))


def cmd_inspect_stats(args):
    inspector = Vault__Inspector(crypto=Vault__Crypto())
    stats     = inspector.object_store_stats(args.directory)
    print(f'=== Object Store Stats ===')
    print(f'  Total objects: {stats["total_objects"]}')
    print(f'  Total size:    {stats["total_bytes"]} bytes')
    if stats['buckets']:
        print(f'  Buckets:')
        for prefix, count in sorted(stats['buckets'].items()):
            print(f'    {prefix}/ : {count} objects')


def main():
    parser = argparse.ArgumentParser(prog='sg-send-cli',
                                     description='CLI tool for syncing encrypted vaults with SG/Send')
    parser.add_argument('--base-url', default=None, help='API base URL (default: https://send.sgraph.ai)')
    parser.add_argument('--token',    default=None, help='SG/Send access token')

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    init_parser = subparsers.add_parser('init', help='Create a new empty vault and register it on the server')
    init_parser.add_argument('directory',   help='Directory to create the vault in (must be empty or non-existent)')
    init_parser.add_argument('--vault-key', default=None, help='Vault key ({passphrase}:{vault_id}). Generated randomly if omitted.')
    init_parser.set_defaults(func=cmd_init)

    clone_parser = subparsers.add_parser('clone', help='Clone a remote vault to a local directory')
    clone_parser.add_argument('vault_key',  help='Vault key ({passphrase}:{vault_id})')
    clone_parser.add_argument('directory',  nargs='?', default=None, help='Target directory (default: vault_id)')
    clone_parser.set_defaults(func=cmd_clone)

    pull_parser = subparsers.add_parser('pull', help='Pull remote changes to local directory')
    pull_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
    pull_parser.set_defaults(func=cmd_pull)

    push_parser = subparsers.add_parser('push', help='Push local changes to the remote vault')
    push_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
    push_parser.set_defaults(func=cmd_push)

    status_parser = subparsers.add_parser('status', help='Show local changes vs vault tree')
    status_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
    status_parser.set_defaults(func=cmd_status)

    remote_status_parser = subparsers.add_parser('remote-status', help='Compare local vault against remote')
    remote_status_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
    remote_status_parser.set_defaults(func=cmd_remote_status)

    keys_parser = subparsers.add_parser('derive-keys', help='Derive and display vault keys (debug)')
    keys_parser.add_argument('vault_key', help='Vault key ({passphrase}:{vault_id})')
    keys_parser.set_defaults(func=cmd_derive_keys)

    inspect_parser = subparsers.add_parser('inspect', help='Show vault state overview (dev tool)')
    inspect_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
    inspect_parser.set_defaults(func=cmd_inspect)

    inspect_obj_parser = subparsers.add_parser('inspect-object', help='Show object details (dev tool)')
    inspect_obj_parser.add_argument('object_id', help='Object ID (12-char hex)')
    inspect_obj_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
    inspect_obj_parser.set_defaults(func=cmd_inspect_object)

    inspect_tree_parser = subparsers.add_parser('inspect-tree', help='Show current tree entries (dev tool)')
    inspect_tree_parser.add_argument('--vault-key', default=None, help='Vault key (auto-read from .sg_vault/VAULT-KEY if omitted)')
    inspect_tree_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
    inspect_tree_parser.set_defaults(func=cmd_inspect_tree)

    inspect_log_parser = subparsers.add_parser('inspect-log', help='Show commit chain (dev tool)')
    inspect_log_parser.add_argument('--vault-key', default=None, help='Vault key (auto-read from .sg_vault/VAULT-KEY if omitted)')
    inspect_log_parser.add_argument('--oneline', action='store_true', help='Compact one-line-per-commit format')
    inspect_log_parser.add_argument('--graph', action='store_true', help='Show graph with connectors')
    inspect_log_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
    inspect_log_parser.set_defaults(func=cmd_inspect_log)

    cat_obj_parser = subparsers.add_parser('cat-object', help='Decrypt and display object contents (dev tool)')
    cat_obj_parser.add_argument('object_id', help='Object ID (12-char hex)')
    cat_obj_parser.add_argument('--vault-key', default=None, help='Vault key (auto-read from .sg_vault/VAULT-KEY if omitted)')
    cat_obj_parser.add_argument('--directory', '-d', default='.', help='Vault directory (default: .)')
    cat_obj_parser.set_defaults(func=cmd_cat_object)

    inspect_stats_parser = subparsers.add_parser('inspect-stats', help='Show object store statistics (dev tool)')
    inspect_stats_parser.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
    inspect_stats_parser.set_defaults(func=cmd_inspect_stats)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    try:
        args.func(args)
    except Legacy_Vault_Error as e:
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(2)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
