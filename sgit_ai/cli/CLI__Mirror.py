"""CLI__Mirror — `sgit vault mirror` (P5): custody without access."""
import sys

from osbot_utils.type_safe.Type_Safe               import Type_Safe
from sgit_ai.crypto.Vault__Crypto                  import Vault__Crypto
from sgit_ai.network.api.Vault__API                import Vault__API
from sgit_ai.core.actions.mirror.Vault__Mirror     import Vault__Mirror


class CLI__Mirror(Type_Safe):

    def cmd_mirror(self, args) -> None:
        source     = getattr(args, 'source', None)
        dest       = getattr(args, 'dest', None)
        verify_dir = getattr(args, 'verify', None)
        mirror     = Vault__Mirror(crypto=Vault__Crypto(), api=Vault__API())

        if verify_dir:
            try:
                result = mirror.verify(verify_dir)
            except RuntimeError as error:
                print(f'error: {error}', file=sys.stderr)
                sys.exit(1)
            print(f'  Verified   {len(result["ok"])} object(s)')
            if result['host_attested']:
                print(f'  Host-attested only (not content-addressed): '
                      f'{len(result["host_attested"])} — refs/indexes/keys carry no '
                      f'self-verifying name until a signed head exists')
            if result['failed']:
                print(f'  FAILED     {len(result["failed"])}:', file=sys.stderr)
                for file_id, reason in result['failed']:
                    print(f'    {file_id}: {reason}', file=sys.stderr)
                sys.exit(1)
            print('  Mirror is intact.')
            return

        if not source or not dest:
            print('usage: sgit vault mirror <source-url-or-folder> <dest>  |  '
                  'sgit vault mirror --verify <dest>', file=sys.stderr)
            sys.exit(1)

        try:
            result = mirror.mirror(source, dest)
        except RuntimeError as error:
            print(f'error: {error}', file=sys.stderr)
            sys.exit(1)

        total = len(result['copied']) + len(result['refused'])
        print(f'  Mirroring   {len(result["copied"])}/{total}   done')
        if result['refused']:
            print(f'  Refused     {len(result["refused"])} (per object — run continued):',
                  file=sys.stderr)
            for file_id, reason in result['refused']:
                print(f'    {file_id}: {reason}', file=sys.stderr)
        if result['host_attested']:
            print(f'  note: {len(result["host_attested"])} file(s) verified only against the '
                  f'manifest\'s own hashes (host-attested) — refs/indexes/keys are not '
                  f'content-addressed.')
        print()
        print('  Custody without access.')
        if result['vault_id']:
            print(f'  You now hold a complete, verifiable copy of vault {result["vault_id"]}.')
        print('  You cannot read it: no key was used, and none is stored here.')
        print(f'  Verify:  sgit vault mirror --verify {dest}     (checks every object hash)')
        if result['vault_id']:
            print(f'  Read it: sgit clone <read-key>:{result["vault_id"]} ./work   (when you have a key)')
