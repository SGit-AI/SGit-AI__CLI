"""Vault__Publish — `sgit publish`: generate the plaintext surface (P2).

The vault is entirely ciphertext; publish deliberately inverts that for a
small, FIXED, declared set of generated files — and that is the whole output:

  .sg_vault/publish/
  ├── index.html               the loader — always sgit's bundled template (I4)
  ├── cover.json               public face of the closed vault
  ├── manifest.json            enumerates the store: ids, sizes, sha256 (01 §4)
  └── sgit_public_read_<hex>   only at --visibility public

Publish copies NO ciphertext (r9): the store already exists, complete and
correct, at .sg_vault/bare/**, one directory away; the served root is
composed at deployment (or virtually, by `sgit vault serve`). There is no
output-directory argument — the only path that changes is .sg_vault/publish/
(invariant I6), so publish → push → publish cannot amplify the store.

The plaintext surface is a fixed allow-list of names IN CODE (below), never a
pattern and never vault content: nobody with vault write access can widen it
by naming a file. Publish needs only the read key, so a read-only clone (and
a zero-secret CI runner for a public vault) can republish.
"""
import json
import os
import shutil
from   datetime import datetime, timezone

from   sgit_ai._version                                   import VERSION
from   sgit_ai.core.Vault__Sync__Base                     import Vault__Sync__Base
from   sgit_ai.core.actions.publish.Loader__Template      import LOADER_TEMPLATE
from   sgit_ai.safe_types.Enum__Published_Layout          import Enum__Published_Layout
from   sgit_ai.safe_types.Enum__Visibility                import Enum__Visibility
from   sgit_ai.schemas.publish.Schema__Plaintext_Entry    import Schema__Plaintext_Entry
from   sgit_ai.schemas.publish.Schema__Published_Manifest import (PUBLISHED_SCHEMA_VERSION,
                                                                  Schema__Published_Manifest)
from   sgit_ai.schemas.publish.Schema__Published_Object   import Schema__Published_Object
from   sgit_ai.schemas.publish.Schema__Vault_Cover        import Schema__Vault_Cover
from   sgit_ai.storage.Vault__Commit                      import Vault__Commit

PUBLISH_DIR_NAME = 'publish'

# The plaintext allow-list: the ONLY names publish may emit, all generated.
# api/* entries are P4b's optional artefacts; bundles/ is P6's.
PLAINTEXT_ALLOW_LIST = ('index.html', 'cover.json', 'manifest.json',
                        'api/openapi.json', 'api/docs/index.html')


class Vault__Publish(Vault__Sync__Base):

    def publish(self, directory: str,
                visibility : Enum__Visibility       = None,
                layout     : Enum__Published_Layout = None,
                api_spec   : bool = False,
                api_docs   : str  = None,
                bundles    : bool = False) -> dict:
        """Write .sg_vault/publish/ and nothing else. Deterministic: the same
        vault head publishes to identical bytes."""
        visibility = visibility or Enum__Visibility.BARE
        layout     = layout or Enum__Published_Layout.API_PATH

        c      = self._init_components(directory)                # read key is enough
        sg_dir = c.sg_dir
        head   = c.ref_manager.read_ref(str(c.ref_file_id), c.read_key)
        if not head:
            raise RuntimeError('vault has no published head — the named branch has no '
                               'commits yet. Commit and push before publishing.')

        commits  = self._walk_commit_parents(c, head)
        objects  = self._enumerate_store(sg_dir)
        self._refuse_unverifiable_store(objects)
        head_ms  = self._head_timestamp_ms(c, head)

        plaintext = {}
        plaintext['index.html'] = LOADER_TEMPLATE.encode('utf-8')
        plaintext['cover.json'] = self._cover_bytes(c, head_ms, visibility)
        if visibility == Enum__Visibility.PUBLIC:
            key_file_name            = self.crypto.format_read_key(c.read_key.hex(), public=True)
            plaintext[key_file_name] = b''

        if api_docs or api_spec:
            from sgit_ai.core.actions.publish.Vault__Publish__Api_Docs import Vault__Publish__Api_Docs
            api_files = Vault__Publish__Api_Docs(crypto=self.crypto, api=self.api).build(
                vault_id=str(c.vault_id), objects=objects, mode=api_docs)
            plaintext.update(api_files)

        manifest = Schema__Published_Manifest(
            schema       = PUBLISHED_SCHEMA_VERSION,
            vault_id     = str(c.vault_id),
            generated_by = f'sgit {VERSION}',
            layout       = layout,
            visibility   = visibility,
            head         = head)
        for file_id, size, sha in objects:
            manifest.objects.append(Schema__Published_Object(file_id=file_id, size=size, sha256=sha))
        for commit_id in commits:
            manifest.commits.append(commit_id)
        for path in sorted(plaintext):
            manifest.plaintext_surface.append(Schema__Plaintext_Entry(
                path=path, sha256=self.crypto.hash_data(plaintext[path])))
        manifest.plaintext_surface.append(Schema__Plaintext_Entry(path='manifest.json', sha256=None))
        plaintext['manifest.json'] = (json.dumps(manifest.json(), indent=2) + '\n').encode('utf-8')

        out_dir = os.path.join(sg_dir, PUBLISH_DIR_NAME)         # the ONLY path that changes (I6)
        if os.path.isdir(out_dir):
            shutil.rmtree(out_dir)
        os.makedirs(out_dir)
        if bundles:
            from sgit_ai.core.actions.publish.Vault__Publish__Bundles import Vault__Publish__Bundles
            Vault__Publish__Bundles(crypto=self.crypto, api=self.api).build(
                sg_dir=sg_dir, out_dir=out_dir, commits=commits, read_key=c.read_key)
        for path in sorted(plaintext):
            full = os.path.join(out_dir, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'wb') as f:
                f.write(plaintext[path])

        self._record_visibility(directory, c, visibility)

        return dict(vault_id    = str(c.vault_id),
                    out_dir     = out_dir,
                    head        = head,
                    visibility  = visibility.value,
                    layout      = layout.value,
                    n_objects   = len(objects),
                    total_bytes = sum(size for _fid, size, _sha in objects),
                    n_commits   = len(commits),
                    surface     = sorted(plaintext))

    def preflight(self, directory: str, requested: Enum__Visibility = None) -> dict:
        """Resolve visibility and detect the downgrade case BEFORE publishing.

        Resolution: explicit flag > this clone's stored choice > bare. The
        downgrade warning exists because a CI runner is always a fresh clone
        (resolves bare): republishing over a PUBLIC output without
        --visibility public would silently drop the key file and lock readers
        out (R3)."""
        stored = None
        try:
            config = self._read_local_config(directory, self._init_components(directory).storage)
            stored = config.publish_visibility
        except Exception:
            pass
        resolved = requested or stored or Enum__Visibility.BARE
        previous = self._previous_visibility(directory)
        return dict(resolved     = resolved,
                    stored       = stored,
                    previous     = previous,
                    is_downgrade = (previous == Enum__Visibility.PUBLIC
                                    and resolved != Enum__Visibility.PUBLIC
                                    and requested is None))

    def is_stale(self, directory: str) -> bool:
        """Keyless staleness check (P3/R4/R7): the manifest's recorded sha256
        for each bare/refs/* file is compared against the bytes on disk. True
        when the store moved on after the last publish (or no publish exists)."""
        manifest = self._read_manifest(directory)
        if not manifest:
            return True
        recorded = {str(entry.file_id): str(entry.sha256) for entry in manifest.objects
                    if str(entry.file_id).startswith('bare/refs/')}
        sg_dir   = os.path.join(directory, '.sg_vault')
        refs_dir = os.path.join(sg_dir, 'bare', 'refs')
        on_disk  = {}
        if os.path.isdir(refs_dir):
            for name in os.listdir(refs_dir):
                path = os.path.join(refs_dir, name)
                if os.path.isfile(path):
                    with open(path, 'rb') as f:
                        on_disk[f'bare/refs/{name}'] = self.crypto.hash_data(f.read())
        return recorded != on_disk

    # --- internals ----------------------------------------------------------

    def _walk_commit_parents(self, c, head: str) -> list:
        """Head-first BFS over parents — a commit log would miss the init
        commit's empty trees; the parent walk cannot."""
        vault_commit = Vault__Commit(crypto=self.crypto, pki=c.pki,
                                     object_store=c.obj_store, ref_manager=c.ref_manager)
        ordered, visited, queue = [], set(), [head]
        while queue:
            commit_id = queue.pop(0)
            if not commit_id or commit_id in visited:
                continue
            visited.add(commit_id)
            ordered.append(commit_id)
            try:
                commit = vault_commit.load_commit(commit_id, c.read_key)
            except Exception:
                continue                                          # fail-soft per object
            for parent in (commit.parents or []):
                if str(parent) and str(parent) not in visited:
                    queue.append(str(parent))
        return ordered

    def _refuse_unverifiable_store(self, objects: list) -> None:
        """A store whose content-addressed objects do not hash to their ids
        (the signature of a vault moved by an older sgit) would publish fine
        and then be REFUSED by every current-version reader — and the
        publisher would never know (review finding B2). Refuse at publish
        time, naming the remedy, since the publisher is exactly the party
        who holds the key and can normalise the store."""
        prefix = 'bare/data/obj-cas-imm-'
        bad    = [file_id for file_id, _size, sha in objects
                  if file_id.startswith(prefix)
                  and file_id.rsplit('/', 1)[-1] != f'obj-cas-imm-{sha[:12]}']
        if not bad:
            return
        from sgit_ai.core.Vault__Errors import Vault__Integrity_Error
        raise Vault__Integrity_Error(
            f'{len(bad)} of this store\'s content-addressed objects do not hash to '
            f'their ids (first: {bad[0].rsplit("/", 1)[-1]}), so every current-version '
            f'reader would refuse the published vault. This is the signature of a vault '
            f'moved by an older sgit. Run `sgit vault move` to normalise the store, '
            f'then publish again.')

    def _enumerate_store(self, sg_dir: str) -> list:
        """(file_id, size, sha256) for every file under bare/** — enumerated,
        NEVER copied (r9). Sorted for determinism."""
        bare_dir = os.path.join(sg_dir, 'bare')
        entries  = []
        for root, _dirs, files in os.walk(bare_dir):
            for name in files:
                full = os.path.join(root, name)
                rel  = os.path.relpath(full, sg_dir).replace(os.sep, '/')
                with open(full, 'rb') as f:
                    data = f.read()
                entries.append((rel, len(data), self.crypto.hash_data(data)))
        return sorted(entries)

    def _head_timestamp_ms(self, c, head: str) -> int:
        try:
            vault_commit = Vault__Commit(crypto=self.crypto, pki=c.pki,
                                         object_store=c.obj_store, ref_manager=c.ref_manager)
            return int(vault_commit.load_commit(head, c.read_key).timestamp_ms)
        except Exception:
            return 0

    def _cover_bytes(self, c, head_ms: int, visibility: Enum__Visibility) -> bytes:
        updated = ''
        if head_ms:                                               # head commit time, never wall clock
            updated = datetime.fromtimestamp(head_ms / 1000, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        cover = Schema__Vault_Cover(title       = str(c.vault_id),
                                    description = 'Published sgit vault. Contents are encrypted; '
                                                  'this page and the host cannot read them.',
                                    updated     = updated,
                                    public      = visibility == Enum__Visibility.PUBLIC)
        return (json.dumps(cover.json(), indent=2) + '\n').encode('utf-8')

    def _record_visibility(self, directory: str, c, visibility: Enum__Visibility) -> None:
        """Remember this clone's choice (decision 5) — per clone, never in the vault."""
        try:
            config_path = c.storage.local_config_path(directory)
            config      = self._read_local_config(directory, c.storage)
            config.publish_visibility = visibility
            with open(config_path, 'w') as f:
                json.dump(config.json(), f)
        except Exception:
            pass

    def _previous_visibility(self, directory: str) -> Enum__Visibility:
        manifest = self._read_manifest(directory)
        return manifest.visibility if manifest else None

    def _read_manifest(self, directory: str) -> Schema__Published_Manifest:
        manifest_path = os.path.join(directory, '.sg_vault', PUBLISH_DIR_NAME, 'manifest.json')
        if not os.path.isfile(manifest_path):
            return None
        try:
            with open(manifest_path) as f:
                return Schema__Published_Manifest.from_json(json.load(f))
        except Exception:
            return None
