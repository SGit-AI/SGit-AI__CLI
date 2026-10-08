"""CLI__Tag — `sgit history tag`: named, signed release pointers.

  sgit history tag                               list the tags (same as `… tag list`)
  sgit history tag create <name> [<commit>] -m   tag a pushed commit (default: this clone's head)
  sgit history tag show <name>                   the tag, its commit, its message, its signature
  sgit history tag delete <name>                 delete it (a tombstone every clone respects)

A tag name also works wherever a commit id does in `sgit history show/reset`.
"""
import argparse
import datetime
import sys
from   osbot_utils.type_safe.Type_Safe     import Type_Safe

STATUS_TEXT = {'verified': 'signature verified',
               'bad'     : 'SIGNATURE DOES NOT VERIFY (or the entry names a different tag)',
               'unsigned': 'unsigned',
               'no-key'  : "signed, but the tagger's key is not available",
               'missing' : 'tag object not available (offline?)'}


class CLI__Tag(Type_Safe):
    vault        : object = None                           # CLI__Vault: token store and create_sync
    network_args : object = None                           # the shared --token / --base-url parent parser

    def register(self, subparsers):
        network_args = self.network_args
        if network_args is None:
            network_args = argparse.ArgumentParser(add_help=False)
            network_args.add_argument('--token',    default=None, help='SG/Send access token')
            network_args.add_argument('--base-url', default=None, help='API base URL')
        tag_p   = subparsers.add_parser('tag', help='Named, signed release pointers', parents=[network_args])
        tag_sub = tag_p.add_subparsers(dest='tag_command')
        tag_p.add_argument('--directory', default='.', help=argparse.SUPPRESS)
        tag_p.set_defaults(func=self.cmd_list)

        list_p = tag_sub.add_parser('list', help='List the tags', parents=[network_args])
        list_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        list_p.set_defaults(func=self.cmd_list)

        create_p = tag_sub.add_parser('create', help='Tag a pushed commit (default: this clone\'s head)',
                                      parents=[network_args])
        create_p.add_argument('name', help='Tag name, e.g. v1.0 or release/2026-10')
        create_p.add_argument('commit', nargs='?', default=None, help='Commit id, short id or tag (default: HEAD)')
        create_p.add_argument('-m', '--message', default='', help='Tag message')
        create_p.add_argument('--force', action='store_true', help='Re-point an existing tag on purpose')
        create_p.add_argument('--directory', default='.', help='Vault directory (default: .)')
        create_p.set_defaults(func=self.cmd_create)

        show_p = tag_sub.add_parser('show', help='Show a tag and verify its signature', parents=[network_args])
        show_p.add_argument('name')
        show_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        show_p.set_defaults(func=self.cmd_show)

        delete_p = tag_sub.add_parser('delete', help='Delete a tag', parents=[network_args])
        delete_p.add_argument('name')
        delete_p.add_argument('directory', nargs='?', default='.', help='Vault directory (default: .)')
        delete_p.set_defaults(func=self.cmd_delete)

    def _sync(self, args):
        directory = getattr(args, 'directory', '.') or '.'
        token     = self.vault.token_store.resolve_token(getattr(args, 'token', None), directory)
        base_url  = self.vault.token_store.resolve_base_url(getattr(args, 'base_url', None), directory)
        return self.vault.create_sync(base_url, token), directory

    def _short(self, cid: str) -> str:
        return cid[len('obj-cas-imm-'):] if cid.startswith('obj-cas-imm-') else cid

    def _when(self, ms: int) -> str:
        return datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC') if ms else ''

    def cmd_list(self, args):
        sync, directory = self._sync(args)
        tags = sync.tag_list(directory)
        if not tags:
            print('No tags yet. Create one with: sgit history tag create <name> -m "<message>"')
            return
        width = max(len(t['name']) for t in tags)
        for t in tags:
            mark = {'verified': '✓', 'bad': '!', 'unsigned': '·', 'no-key': '?', 'missing': '?'}.get(t['status'], '?')
            print(f'  {mark} {t["name"]:<{width}}  {self._short(t["commit_id"]) or "(unavailable)"}  '
                  f'{self._when(t["timestamp_ms"])}  {t["message"].splitlines()[0] if t["message"] else ""}')
        if any(t['status'] == 'bad' for t in tags):
            print('\n! = signature does not verify: do not trust that tag; sgit history tag show <name>')

    def cmd_create(self, args):
        sync, directory = self._sync(args)
        r = sync.tag_create(directory, args.name, args.commit, args.message, force=args.force)
        moved = f' (moved from {self._short(r["moved_from"])})' if r.get('moved_from') else ''
        print(f'Tagged {self._short(r["commit_id"])} as {r["name"]}{moved}, signed by this clone.')

    def cmd_show(self, args):
        sync, directory = self._sync(args)
        t = sync.tag_show(directory, args.name)
        print(f'tag     {t["name"]}')
        print(f'commit  {t["commit_id"] or "(unavailable)"}')
        print(f'date    {self._when(t["timestamp_ms"])}')
        print(f'tagger  {t["tagger_key_id"] or "(unknown)"}')
        print(f'status  {STATUS_TEXT.get(t["status"], t["status"])}')
        if t['message']:
            print()
            for line in t['message'].splitlines():
                print(f'    {line}')
        if t['status'] == 'bad':
            sys.exit(1)

    def cmd_delete(self, args):
        sync, directory = self._sync(args)
        r = sync.tag_delete(directory, args.name)
        print(f'Deleted tag {r["name"]}.')
