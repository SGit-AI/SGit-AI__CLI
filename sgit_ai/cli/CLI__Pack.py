"""CLI__Pack — `sgit pack import | export | compact | ls | verify | stats`.

A pack vault keeps its objects on the host as zips (bare/packs/) instead of loose
files; blobs are deflated before encryption. `sgit init --packs` starts one;
`sgit pack import` turns a full clone of a normal vault into a new pack vault, and
`sgit pack export` turns a pack-vault clone back into a new normal vault — the two
halves of the round trip. Pack vaults are CLI-only (no web view) and gated by
min_client, so an older sgit refuses them by name.
"""
import json
import sys

from osbot_utils.type_safe.Type_Safe         import Type_Safe


class CLI__Pack(Type_Safe):
    vault_ref : object = None       # CLI__Vault, for token/remote resolution and create_sync

    def _sync(self, args, directory: str):
        token  = self.vault_ref.token_store.resolve_token(getattr(args, 'token', None), directory)
        remote = self.vault_ref.token_store.resolve_remote(args, directory)
        return self.vault_ref.create_sync(remote['base_url'], token, tls_verify=remote['tls_verify'],
                                          transport=getattr(args, 'transport', 'auto'))

    def _progress(self, kind, message, detail=''):
        if kind in ('step', 'warning', 'stats'):
            print(f'  {message}' + (f' — {detail}' if detail else ''), flush=True)   # a file or a pipe sees each line now

    def _convert(self, args, packs: bool):
        from sgit_ai.core.actions.pack.Vault__Pack_Convert import Vault__Pack_Convert
        source = getattr(args, 'source', '.') or '.'
        target = getattr(args, 'target')
        sync   = self._sync(args, source)
        conv   = Vault__Pack_Convert(crypto=sync.crypto, api=sync.api)
        deflate = None if packs and not getattr(args, 'no_deflate', False) else (False if packs else None)
        as_json = getattr(args, 'json', False)
        stats  = conv.convert(source, target, packs=packs, vault_key=getattr(args, 'vault_key', None),
                              deflate=deflate, on_progress=None if as_json else self._progress)
        server = self.vault_ref.token_store.resolve_remote(args, source)['base_url']
        self.vault_ref.token_store.save_base_url(server, target)       # the new vault lives on the same server
        token = self.vault_ref.token_store.resolve_token(getattr(args, 'token', None), source)
        if token:
            self.vault_ref.token_store.save_token(token, target)
        if getattr(args, 'json', False):
            print(json.dumps(stats, indent=2)); return
        kind = 'pack vault' if packs else 'normal vault'
        print()
        print(f'{"Imported" if packs else "Exported"} into a new {kind}: {target}/')
        print(f'  Vault ID:  {stats["vault_id"]}')
        print(f'  Vault key: {stats["vault_key"]}')
        print(f'  History:   {stats["commits"]} commits, {stats["trees"]} trees, {stats["blobs"]} blobs '
              f'(head {stats["source_head"]} -> {stats["target_head"]})')
        print(f'  Blobs:     {stats["blob_cipher_bytes_source"] / 1e6:.1f} MB -> {stats["blob_cipher_bytes_target"] / 1e6:.1f} MB '
              f'(x{stats["blob_ratio"]:.2f}, {stats["deflated"]} deflated) in {stats["elapsed_s"]:.1f}s')
        print()
        print('  Save the new vault key — this is a new vault; the source is untouched.')
        print()
        print('Next step:')
        print(f'  cd {target} && sgit push     — first push: ' + ('one snapshot pack' if packs else 'loose objects'))

    def cmd_import(self, args):
        self._convert(args, packs=True)

    def cmd_export(self, args):
        self._convert(args, packs=False)

    def cmd_compact(self, args):
        from sgit_ai.core.actions.pack.Vault__Pack_Maintain import Vault__Pack_Maintain
        directory = getattr(args, 'directory', '.') or '.'
        sync      = self._sync(args, directory)
        as_json   = getattr(args, 'json', False)
        result    = Vault__Pack_Maintain(crypto=sync.crypto, api=sync.api).compact(
            directory, dry_run=getattr(args, 'dry_run', False), on_progress=None if as_json else self._progress)
        if getattr(args, 'json', False):
            print(json.dumps(result, indent=2, default=str)); return
        plan = result['plan']
        verb = 'Would' if result['dry_run'] else 'Did'
        snap = plan['snapshot']
        print(f'{verb} snapshot head {plan["head"]}: ' + ('already on the host' if snap['existing'] else (snap['name'] or 'new')))
        for kind, label in (('absorbed', 'absorbed by the snapshot'), ('superseded', 'superseded snapshots'),
                            ('orphans', 'orphans older than a day')):
            if plan[kind]:
                print(f'  {len(plan[kind])} pack(s) {label} -> archive/')
        if plan['kept']:
            print(f'  {len(plan["kept"])} recent pack(s) not on the branch kept in commits/')
        if not result['dry_run']:
            already = result.get('already_archived', 0)
            print(f'{result["moved"]} pack(s) archived' + (f' ({already} already in archive)' if already else '')
                  + '. Nothing was deleted without its copy in archive/.')

    def cmd_ls(self, args):
        from sgit_ai.core.actions.pack.Vault__Pack_Maintain import Vault__Pack_Maintain
        directory = getattr(args, 'directory', '.') or '.'
        sync      = self._sync(args, directory)
        listed    = Vault__Pack_Maintain(crypto=sync.crypto, api=sync.api).ls(directory)
        if getattr(args, 'json', False):
            print(json.dumps(listed, indent=2)); return
        absorbed = set(listed['absorbed'])
        for folder in ('snapshots', 'commits', 'archive'):
            entries = listed[folder]
            print(f'{folder}/  ({len(entries)} pack(s), {sum(e["size"] for e in entries) / 1e6:.1f} MB)')
            for e in entries:
                mark = '*' if e['name'] in absorbed else ' '
                print(f'  {mark} {e["name"]}')
        print('  * = absorbed by this clone')

    def cmd_verify(self, args):
        from sgit_ai.core.actions.pack.Vault__Pack_Maintain import Vault__Pack_Maintain
        directory = getattr(args, 'directory', '.') or '.'
        sync      = self._sync(args, directory)
        report    = Vault__Pack_Maintain(crypto=sync.crypto, api=sync.api).verify(directory)
        if getattr(args, 'json', False):
            print(json.dumps(report, indent=2)); return
        print(f'{report["packs"]} pack(s), {report["members"]} member(s) checked against their ids')
        for bad in report['bad']:
            print(f'  BAD  {bad["pack"]}: {bad["member"]}')
        for wrong in report['sizes_wrong']:
            print(f'  BAD  {wrong["name"]}: {wrong["error"]}')
        print('ok' if report['ok'] else 'FAILED')
        if not report['ok']:
            sys.exit(1)

    def cmd_stats(self, args):
        from sgit_ai.core.actions.pack.Vault__Pack_Maintain import Vault__Pack_Maintain
        directory = getattr(args, 'directory', '.') or '.'
        sync      = self._sync(args, directory)
        stats     = Vault__Pack_Maintain(crypto=sync.crypto, api=sync.api).stats(directory)
        if getattr(args, 'json', False):
            print(json.dumps(stats, indent=2)); return
        host, local = stats['host'], stats['local']
        print(f'Vault {stats["vault_id"]}  head {stats["head"]}')
        print('Host:')
        for folder in ('snapshots', 'commits', 'archive'):
            print(f'  {folder:<10} {host[folder]["packs"]:>5} pack(s)  {host[folder]["bytes"] / 1e6:>8.1f} MB')
        print(f'  loose objects under bare/data/: {host["loose_objects"]}' + ('' if host['loose_objects'] == 0 else '  (should be 0 on a pack vault)'))
        print('Local store:')
        print(f'  {local["objects"]} objects; {local["blobs"]} blobs on the branch, {local["deflated"]} deflated; '
              f'{local["plain_bytes"] / 1e6:.1f} MB plaintext -> {local["cipher_bytes"] / 1e6:.1f} MB stored (x{local["ratio"]:.2f})')

    # ------------------------------------------------------------------ sgit pack store ...
    def _pack_store(self, args, directory: str):
        import os
        from sgit_ai.storage.Vault__Pack_Store import Vault__Pack_Store
        from sgit_ai.storage.Vault__Storage    import SG_VAULT_DIR
        sync  = self._sync(args, directory)
        store = Vault__Pack_Store(vault_path=os.path.join(directory, SG_VAULT_DIR), crypto=sync.crypto).setup()
        if store is None:
            print('error: this clone keeps no packs in place (clone with --pack-store)', file=sys.stderr)
            sys.exit(1)
        return sync, store

    def cmd_store_status(self, args):
        import os
        from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
        from sgit_ai.storage.Vault__Storage      import SG_VAULT_DIR
        directory   = getattr(args, 'directory', '.') or '.'
        sync, store = self._pack_store(args, directory)
        try:
            packs  = store.packs()
            loose  = Vault__Object_Store(vault_path=os.path.join(directory, SG_VAULT_DIR), crypto=sync.crypto).loose_object_ids()
            report = dict(packs=packs, packed_objects=store.object_count(), loose_objects=len(loose),
                          bytes=sum(p['size'] for p in packs))
        finally:
            store.close()
        if getattr(args, 'json', False):
            print(json.dumps(report, indent=2)); return
        print(f'Pack store: {len(report["packs"])} pack(s) kept, {report["bytes"] / 1e6:.1f} MB; '
              f'{report["packed_objects"]} object(s) read from them; {report["loose_objects"]} loose object(s) (not pushed yet)')
        for p in report['packs']:
            print(f'  {p["rel"]:<70} {p["members"]:>7} object(s)  {p["size"] / 1e6:>8.1f} MB')

    def cmd_store_extract(self, args):
        import os
        from sgit_ai.storage.Vault__Object_Store import Vault__Object_Store
        from sgit_ai.storage.Vault__Storage      import SG_VAULT_DIR, Vault__Storage
        directory   = getattr(args, 'directory', '.') or '.'
        sync, store = self._pack_store(args, directory)
        n = store.extract_all(Vault__Object_Store(vault_path=os.path.join(directory, SG_VAULT_DIR), crypto=sync.crypto))
        cfg = sync._read_local_config(directory, Vault__Storage())
        cfg.pack_store = False
        Vault__Storage().write_local_config(directory, cfg.json())
        print(f'Extracted {n} object(s) into the loose store; the kept packs are gone and this is an ordinary clone now.')

    def cmd_store_rebuild(self, args):
        directory   = getattr(args, 'directory', '.') or '.'
        sync, store = self._pack_store(args, directory)
        try:
            r = store.rebuild()
        finally:
            store.close()
        print(f'Rebuilt: {r["packs"]} pack(s), {r["objects"]} object(s)' + (f', {len(r["refused"])} member(s) refused' if r['refused'] else ''))

    # ------------------------------------------------------------------ sgit pack index ...
    def cmd_index_build(self, args):
        from sgit_ai.core.actions.pack.Vault__Pack_Index import Vault__Pack_Index
        directory = getattr(args, 'directory', '.') or '.'
        sync      = self._sync(args, directory)
        as_json   = getattr(args, 'json', False)
        result    = Vault__Pack_Index(crypto=sync.crypto, api=sync.api).build_missing(
            directory, rebuild_snapshot=getattr(args, 'all', False), on_progress=None if as_json else self._progress)
        if as_json:
            print(json.dumps(result, indent=2)); return
        print(f'{len(result["written"])} index pack(s) written' + (f', {len(result["skipped"])} skipped (commit not local)' if result['skipped'] else ''))
        if result['gaps']:
            print(f'  {len(result["gaps"])} gap(s) still recorded locally: ' + ', '.join(result['gaps'][:3]))

    def cmd_index_verify(self, args):
        from sgit_ai.core.actions.pack.Vault__Pack_Index import Vault__Pack_Index
        directory = getattr(args, 'directory', '.') or '.'
        sync      = self._sync(args, directory)
        as_json   = getattr(args, 'json', False)
        report    = Vault__Pack_Index(crypto=sync.crypto, api=sync.api).verify_indexes(
            directory, on_progress=None if as_json else self._progress, last=int(getattr(args, 'last', 0) or 0))
        if as_json:
            print(json.dumps(report, indent=2)); return
        print(f'{report["packs"]} index pack(s), {report["members"]} member(s) checked against the trees in {report["seconds"]}s')
        for bad in report['bad']:
            print(f'  BAD  {bad["pack"]}: {bad["member"]}: {bad["error"]}')
        for name in report['unsigned']:
            print(f'  unsigned  {name}')
        for name in report['orphans']:
            print(f'  orphan (no data pack)  {name}')
        for name in report['gaps']:
            print(f'  gap (no index)  {name}')
        print('ok' if report['ok'] else 'FAILED')
        if not report['ok']:
            sys.exit(1)

    def cmd_index_stats(self, args):
        from sgit_ai.core.actions.pack.Vault__Pack_Index import Vault__Pack_Index
        directory = getattr(args, 'directory', '.') or '.'
        sync      = self._sync(args, directory)
        stats     = Vault__Pack_Index(crypto=sync.crypto, api=sync.api).index_stats(directory)
        if getattr(args, 'json', False):
            print(json.dumps(stats, indent=2)); return
        print(f'Vault {stats["vault_id"]}')
        for folder, f in stats['folders'].items():
            print(f'  {folder:<10} {f["index_packs"]:>5} index pack(s) for {f["data_packs"]:>5} data pack(s)  {f["index_bytes"] / 1e3:>9.1f} KB'
                  + (f'  ({len(f["without_index"])} without an index)' if f['without_index'] else ''))
        print(f'  local generation memo: {stats["generations_known"]} commit(s) (highest {stats["highest_generation"]}); '
              f'local gaps: {stats["local_gaps"]}')
        if not stats['generations_known']:
            print('    (the memo is filled when this clone writes an index; a clone that only reads them has none: that is fine)')
