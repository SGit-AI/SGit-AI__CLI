import sys
from osbot_utils.type_safe.Type_Safe         import Type_Safe
from sgit_ai.api.API__Transfer               import API__Transfer, DEFAULT_BASE_URL
from sgit_ai.crypto.Vault__Crypto            import Vault__Crypto
from sgit_ai.transfer.Vault__Transfer        import Vault__Transfer


class CLI__Share(Type_Safe):

    def cmd_share(self, args):
        directory  = getattr(args, 'directory', '.')
        token_str  = getattr(args, 'token', None)
        base_url   = getattr(args, 'base_url', None) or DEFAULT_BASE_URL

        print('Generating share token...')

        api      = API__Transfer(base_url=base_url)
        api.setup()
        transfer = Vault__Transfer(api=api, crypto=Vault__Crypto())
        transfer.setup()

        try:
            result = transfer.share(directory, token_str=token_str)
        except RuntimeError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)

        token       = result['token']
        transfer_id = result['transfer_id']
        file_count  = result['file_count']
        total_kb    = result['total_bytes'] / 1024

        print(f'  Token:       {token}')
        print(f'  Transfer ID: {transfer_id}')
        print(f'  Files:       {file_count} file(s), {total_kb:.1f} KB')
        print()
        print('Upload complete. Share this token:')
        print()
        print(f'  {token}')
        print()
        print('Anyone with this token can download and decrypt the vault snapshot at:')
        print(f'  https://send.sgraph.ai/#{token}')
        print()
        print('Next:')
        print('  sgit publish          — create a shareable encrypted archive')
        print('  sgit export           — save an encrypted archive locally')
        print('  sgit status           — check vault state')
