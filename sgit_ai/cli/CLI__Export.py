import json
import os
import sys
import time
from osbot_utils.type_safe.Type_Safe     import Type_Safe
from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.transfer.Vault__Archive     import Vault__Archive
from sgit_ai.transfer.Vault__Transfer    import Vault__Transfer
from sgit_ai.transfer.Simple_Token       import Simple_Token
from sgit_ai.transfer.Simple_Token__Wordlist import Simple_Token__Wordlist


class CLI__Export(Type_Safe):

    def cmd_export(self, args):
        directory     = getattr(args, 'directory',        '.')
        output_path   = getattr(args, 'output',           None)
        token_str     = getattr(args, 'token',            None)
        no_inner_enc  = getattr(args, 'no_inner_encrypt', False)

        print('Exporting vault archive...')

        crypto   = Vault__Crypto()
        api_stub = None   # export is local-only, no API needed
        transfer = Vault__Transfer(crypto=crypto)

        # Collect committed files at HEAD
        try:
            files = transfer.collect_head_files(directory)
        except RuntimeError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)

        # Read vault read-key (for inner encryption)
        vault_read_key = None
        vault_id       = ''
        if not no_inner_enc:
            from sgit_ai.sync.Vault__Storage import Vault__Storage
            storage        = Vault__Storage()
            vault_key_path = storage.vault_key_path(directory)
            if os.path.isfile(vault_key_path):
                try:
                    with open(vault_key_path, 'r') as f:
                        vault_key = f.read().strip()
                    keys           = crypto.derive_keys_from_vault_key(vault_key)
                    vault_read_key = keys['read_key_bytes']
                    vault_id       = keys['vault_id']
                except Exception:
                    vault_id = ''

        total_bytes = sum(len(v) for v in files.values())
        total_kb    = total_bytes / 1024

        inner_desc = 'vault key (double-encrypted)' if vault_read_key is not None else 'none (plain zip)'
        print(f'  Files:    {len(files)} file(s), {total_kb:.1f} KB')
        print(f'  Inner:    {inner_desc}')
        print()

        # Generate or accept token
        wordlist = Simple_Token__Wordlist()
        wordlist.setup()

        if token_str:
            from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token
            token_val = Safe_Str__Simple_Token(token_str)
        else:
            token_val = wordlist.generate()

        token_display = str(token_val)

        # Read branch_id from local config
        from sgit_ai.sync.Vault__Storage import Vault__Storage as VS
        storage           = VS()
        local_config_path = storage.local_config_path(directory)
        branch_id         = ''
        commit_id         = ''
        if os.path.isfile(local_config_path):
            with open(local_config_path, 'r') as f:
                local_config = json.load(f)
            branch_id = local_config.get('my_branch_id', '')

        # Build archive
        archive        = Vault__Archive(crypto=crypto)
        encrypted_blob = archive.build_archive(
            files          = files,
            token          = token_display,
            vault_read_key = vault_read_key,
            vault_id       = vault_id,
            branch_id      = branch_id,
            commit_id      = commit_id,
        )

        # Determine output filename
        if output_path is None:
            folder_name = os.path.basename(os.path.abspath(directory)).replace(' ', '')
            timestamp   = int(time.time())
            output_path = f'.vault__{folder_name}__{timestamp}.zip'

        with open(output_path, 'wb') as f:
            f.write(encrypted_blob)

        archive_kb = len(encrypted_blob) / 1024

        print('Export complete.')
        print(f'  Archive:  {output_path}  ({archive_kb:.1f} KB)')
        print(f'  Token:    {token_display}')
        print(f'  (keep this token — needed to open the archive)')
        print()
        print('Next:')
        print('  sgit publish          — upload an encrypted archive to the server')
        print('  sgit share            — share a live snapshot with a simple token')
        print('  sgit init --restore . — restore from this archive later')
