"""CLI__Publish — the `sgit publish` command surface (P2/P4).

User-facing strings follow 02__commands-and-ux.md; several are load-bearing
(the --visibility public confirmation is the only moment a user is told
publication is irreversible)."""
import sys

from osbot_utils.type_safe.Type_Safe                   import Type_Safe
from sgit_ai.cli.CLI__Input                            import CLI__Input
from sgit_ai.crypto.Vault__Crypto                      import Vault__Crypto
from sgit_ai.network.api.Vault__API                    import Vault__API
from sgit_ai.core.actions.publish.Vault__Publish       import Vault__Publish
from sgit_ai.safe_types.Enum__Published_Layout         import Enum__Published_Layout
from sgit_ai.safe_types.Enum__Visibility               import Enum__Visibility


class CLI__Publish(Type_Safe):
    prompt_answers : object = None       # canned answers for tests

    def _prompt(self, message: str) -> str:
        if self.prompt_answers is not None:
            return self.prompt_answers.pop(0) if self.prompt_answers else None
        return CLI__Input().prompt(message)

    def cmd_publish(self, args) -> None:
        directory  = getattr(args, 'directory', '.') or '.'
        skip_prompt = getattr(args, 'yes', False)
        requested  = getattr(args, 'visibility', None)
        requested  = Enum__Visibility(requested) if requested else None
        layout     = Enum__Published_Layout(getattr(args, 'layout', None) or 'api-path')
        api_docs   = getattr(args, 'api_docs', None)
        api_spec   = getattr(args, 'api_spec', False) or bool(api_docs)
        bundles    = getattr(args, 'bundles', False)

        publisher = Vault__Publish(crypto=Vault__Crypto(), api=Vault__API())
        pre       = publisher.preflight(directory, requested)
        resolved  = pre['resolved']

        if pre['is_downgrade']:
            print('warning: this output was last published as PUBLIC, but this clone resolves\n'
                  f'         visibility={resolved.value} — the key file would be REMOVED and readers locked out.\n'
                  '         Pass --visibility public to keep it, or --yes to downgrade deliberately.',
                  file=sys.stderr)
            if not skip_prompt:
                sys.exit(1)

        if resolved == Enum__Visibility.PUBLIC and requested == Enum__Visibility.PUBLIC \
                and not skip_prompt:
            print()
            print('  ⚠ This publishes the READ KEY alongside the vault.')
            print('    Anyone with the URL can read every file in it, now and in every future')
            print('    publish of this content. This cannot be undone: copies cannot be recalled.')
            answer = self._prompt('    Continue? [y/N] ')
            if not answer or answer.strip().lower() not in ('y', 'yes'):
                print('Aborted. Nothing written.')
                sys.exit(1)

        result = publisher.publish(directory, visibility=resolved, layout=layout,
                                   api_spec=api_spec, api_docs=api_docs, bundles=bundles)
        self._print_result(result, resolved, api_docs)

    def _print_result(self, result: dict, visibility: Enum__Visibility, api_docs: str) -> None:
        total_kb    = max(1, result['total_bytes'] // 1024)
        surface     = [p for p in result['surface']]
        print(f'Publishing vault {result["vault_id"]} → .sg_vault/publish/')
        print()
        print(f'  Store (referenced)   {result["n_objects"]} objects ({total_kb} KB)   '
              f'enumerated in manifest.json — NOT copied')
        print(f'  Plaintext surface     {len(surface)}               {", ".join(surface)}')
        if visibility == Enum__Visibility.BARE:
            print( '  Visibility           bare             unlisted, NOT access-controlled — no key')
            print( '                                          published; manifest.json still shows object')
            print( '                                          count/sizes/cadence (needed for custody)')
        elif visibility == Enum__Visibility.PUBLIC:
            print( '  Visibility           public           key published in the folder')
        else:
            print(f'  Visibility           {visibility.value}')
        if api_docs:
            self._print_api_docs_note(api_docs)
        print()
        # SP-7: the static target drops properties the live API had — say so.
        print('  note: a static target has no server-side revocation, no auth and no read')
        print('        audit; "bare" means unlisted, NOT access-controlled.')
        if visibility == Enum__Visibility.PUBLIC:
            print()
            print('  note: if you deploy this folder into a git repository, the published bytes')
            print('        stay in its history after any later deletion, so rotation cannot')
            print('        revoke access to what you publish now.')
            print('        Deploy to object storage instead if you may need to revoke.')
        print()
        print('Published. Next:')
        print('  sgit vault serve               — browse it locally (a local folder cannot be opened directly)')
        print(f'  sgit clone <read-key>:{result["vault_id"]} — clone it back from any GET host')

    def _print_api_docs_note(self, api_docs: str) -> None:
        if api_docs == 'cdn':
            print('  note: Swagger UI loads from cdn.jsdelivr.net, pinned to an exact version with')
            print('        SRI hashes and no-referrer, so the CDN cannot change the code or learn')
            print('        which vault this is. It does mean the docs page needs the network.')
            print('        Use --api-docs=bundled for an offline or no-third-parties deployment.')
        elif api_docs == 'bundled':
            print('  note: vendoring Swagger UI adds 1.53 MB to this folder — about 2.7× a')
            print('        typical vault — and to every copy, zip and mirror of it.')
