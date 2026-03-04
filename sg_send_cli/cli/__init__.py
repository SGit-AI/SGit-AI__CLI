import argparse
import os
import sys
from sg_send_cli.crypto.Vault__Crypto import Vault__Crypto
from sg_send_cli.api.Vault__API       import Vault__API
from sg_send_cli.sync.Vault__Sync     import Vault__Sync

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


def main():
    parser = argparse.ArgumentParser(prog='sg-send-cli',
                                     description='CLI tool for syncing encrypted vaults with SG/Send')
    parser.add_argument('--base-url', default=None, help='API base URL (default: https://send.sgraph.ai)')
    parser.add_argument('--token',    default=None, help='SG/Send access token')

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

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

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    try:
        args.func(args)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
