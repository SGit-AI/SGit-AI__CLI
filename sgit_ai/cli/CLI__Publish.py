import sys
from osbot_utils.type_safe.Type_Safe     import Type_Safe
from sgit_ai.api.API__Transfer           import API__Transfer, DEFAULT_BASE_URL
from sgit_ai.cli.CLI__Token_Store        import CLI__Token_Store
from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.transfer.Vault__Archive     import Vault__Archive
from sgit_ai.transfer.Vault__Transfer    import Vault__Transfer
from sgit_ai.transfer.Simple_Token       import Simple_Token
from sgit_ai.transfer.Simple_Token__Wordlist import Simple_Token__Wordlist


class CLI__Publish(Type_Safe):
    token_store : CLI__Token_Store
    debug_log   : object = None

    def cmd_publish(self, args):
        directory       = getattr(args, 'directory',         '.')
        token_str       = getattr(args, 'token',             None)
        no_inner_enc    = getattr(args, 'no_inner_encrypt',  False)
        base_url        = getattr(args, 'base_url',          None)

        base_url     = base_url or self.token_store.load_base_url(directory) or DEFAULT_BASE_URL
        access_token = self.token_store.load_token(directory)
        if not access_token and sys.stdin.isatty():
            access_token = input('Access token: ').strip()
            if not access_token:
                print('error: an access token is required to publish.', file=sys.stderr)
                sys.exit(1)
            self.token_store.save_token(access_token, directory)

        print('Publishing vault snapshot...')

        crypto   = Vault__Crypto()
        api      = API__Transfer(base_url=base_url, access_token=access_token,
                                 debug_log=self.debug_log)
        api.setup()
        transfer = Vault__Transfer(api=api, crypto=crypto)

        # Collect committed files at HEAD
        try:
            files = transfer.collect_head_files(directory)
        except RuntimeError as e:
            print(f'error: {e}', file=sys.stderr)
            sys.exit(1)

        # Read vault read-key (for inner encryption)
        vault_read_key = None
        if not no_inner_enc:
            from sgit_ai.sync.Vault__Storage import Vault__Storage
            storage        = Vault__Storage()
            vault_key_path = storage.vault_key_path(directory)
            try:
                import os
                if os.path.isfile(vault_key_path):
                    with open(vault_key_path, 'r') as f:
                        vault_key = f.read().strip()
                    keys           = crypto.derive_keys_from_vault_key(vault_key)
                    vault_read_key = keys['read_key_bytes']
                    vault_id       = keys['vault_id']
                else:
                    vault_id = ''
            except Exception:
                vault_id = ''
        else:
            vault_id = ''

        total_bytes = sum(len(v) for v in files.values())
        total_kb    = total_bytes / 1024

        # Generate or accept token
        wordlist = Simple_Token__Wordlist()
        wordlist.setup()

        if token_str:
            from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token
            token_val = Safe_Str__Simple_Token(token_str)
        else:
            token_val = wordlist.generate()

        token_display = str(token_val)

        inner_desc = 'vault key (double-encrypted)' if vault_read_key is not None else 'none (plain zip)'
        print(f'  Files:    {len(files)} file(s), {total_kb:.1f} KB')
        print(f'  Token:    {token_display}')
        print(f'  Inner:    {inner_desc}')
        print()

        # Build archive
        archive = Vault__Archive(crypto=crypto)
        import json, os
        from sgit_ai.sync.Vault__Storage import Vault__Storage as VS
        storage        = VS()
        local_config_path = storage.local_config_path(directory)
        branch_id = ''
        commit_id = ''
        if os.path.isfile(local_config_path):
            with open(local_config_path, 'r') as f:
                local_config = json.load(f)
            branch_id = local_config.get('my_branch_id', '')

        encrypted_blob = archive.build_archive(
            files         = files,
            token         = token_display,
            vault_read_key = vault_read_key,
            vault_id      = vault_id,
            branch_id     = branch_id,
            commit_id     = commit_id,
        )

        # Upload
        try:
            transfer_id = transfer.upload(encrypted_blob)
        except Exception as e:
            print(f'error: upload failed — {e}', file=sys.stderr)
            sys.exit(1)

        st   = Simple_Token(token=token_val)
        url  = f'https://send.sgraph.ai/en-gb/browse/#{token_display}'
        split_url = f'https://send.sgraph.ai/en-gb/download/#{transfer_id}'

        print('Upload complete.')
        print()
        print(f'  Token:  {token_display}')
        print(f'  URL:    {url}')
        print()
        print(f'  (split: {split_url}  +  key: {token_display})')
        print()
        print('Next:')
        print('  sgit share            — share a live snapshot with a simple token')
        print('  sgit export           — save an encrypted archive locally')
        print('  sgit status           — check vault state')
