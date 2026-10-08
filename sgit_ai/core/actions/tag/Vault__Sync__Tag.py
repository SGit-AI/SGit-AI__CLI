"""Vault__Sync__Tag — named, signed, encrypted release pointers (sgit vault tag).

A tag is two things:
  * a tag OBJECT (Schema__Object_Tag) in bare/data: name, commit, message,
    tagger key, timestamp and an ECDSA signature over its canonical form,
    encrypted under the read key and content-addressed like every object, so
    the host can neither read it nor alter it undetected;
  * a tag ENTRY (Schema__Tag_Ref) in the encrypted branch index: name -> tag
    object. The index is a shared document (Vault__Index_Sync): entries merge
    per name, the later one wins, deletes are tombstones.

Verification of a tag checks the content address (on fetch), the signature
(the tagger's key, fetched if this clone lacks it) and that the index entry's
name is the name inside the signed object, so an entry cannot point "v1.0" at
an object signed for another name. Tagging a commit the server does not have
is refused (push first); tags never move unless created again with --force,
and a pull reports any tag that moved.
"""
import base64
import json
import time
from   sgit_ai.core.Vault__Sync__Base                   import Vault__Sync__Base
from   sgit_ai.core.Vault__Errors                       import Vault__Tag_Error
from   sgit_ai.core.actions.index.Vault__Index_Sync     import Vault__Index_Sync
from   sgit_ai.core.actions.verify.Vault__Key_Fetch     import Vault__Key_Fetch
from   sgit_ai.crypto.PKI__Crypto                       import PKI__Crypto
from   sgit_ai.schemas.Schema__Object_Tag               import Schema__Object_Tag
from   sgit_ai.schemas.Schema__Tag_Ref                  import Schema__Tag_Ref
from   sgit_ai.safe_types.Safe_Str__Tag_Name            import TAG_NAME__REGEX
from   sgit_ai.storage.Vault__Commit                    import Vault__Commit

VERIFIED = 'verified'
BAD      = 'bad'
UNSIGNED = 'unsigned'
NO_KEY   = 'no-key'
MISSING  = 'missing'


class Vault__Sync__Tag(Vault__Sync__Base):

    # ------------------------------------------------------------------ read
    def list_tags(self, directory: str, refresh: bool = True) -> list:
        """Every live tag, sorted by name, each dict(name, tag_id, commit_id,
        message, timestamp_ms, tagger_key_id, status)."""
        c     = self._init_components(directory)
        index = self._index(c, directory, refresh)
        return [self._describe(c, t) for t in sorted(index.tags or [], key=lambda t: str(t.name)) if not t.deleted]

    def show(self, directory: str, name: str, refresh: bool = True) -> dict:
        c   = self._init_components(directory)
        ref = self._live_ref(self._index(c, directory, refresh), name)
        if ref is None:
            raise Vault__Tag_Error(f'no tag named {name!r} (sgit vault tag list shows the tags this vault has)')
        return self._describe(c, ref)

    def resolve(self, directory: str, name: str) -> str:
        """The commit a tag names, from this clone's own copy (no network), or ''."""
        try:
            if not TAG_NAME__REGEX.match(str(name or '')):
                return ''
            c   = self._init_components(directory)
            ref = self._live_ref(c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key), name)
            if ref is None:
                return ''
            return str(self._load_tag(c, str(ref.tag_id)).commit_id or '')
        except Exception:
            return ''

    # ----------------------------------------------------------------- write
    def create(self, directory: str, name: str, commit_id: str = None, message: str = '',
               force: bool = False) -> dict:
        if not TAG_NAME__REGEX.match(str(name or '')):
            raise Vault__Tag_Error(f'{name!r} is not a valid tag name (letters, digits, . _ - /; '
                                   f'no "..", no leading "-", no trailing "/" or ".")')
        c      = self._init_components(directory)
        index  = self._index(c, directory, refresh=True)
        config = self._read_local_config(directory, c.storage)
        meta   = c.branch_manager.get_branch_by_id(index, str(config.my_branch_id)) if config.my_branch_id else None
        if meta is None:
            raise Vault__Tag_Error('this clone has no branch of its own to sign with (a read-only clone cannot tag)')
        existing = self._live_ref(index, name)
        if existing is not None and not force:
            raise Vault__Tag_Error(f'tag {name!r} already exists (it names {self._commit_of(c, existing)}); '
                                   f'tags do not move. Use --force to re-point it on purpose.')
        target = self._resolve_commit(c, directory, commit_id or c.ref_manager.read_ref(str(meta.head_ref_id), c.read_key))
        if not self._on_server(c, target):
            raise Vault__Tag_Error(f'commit {target} is not on the server yet: push it first, then tag it')

        signing_key = c.key_manager.load_private_key_locally(str(meta.public_key_id), c.storage.local_dir(directory))
        tag = Schema__Object_Tag(schema='tag_v1', name=name, commit_id=target, message=message or '',
                                 timestamp_ms=int(time.time() * 1000), tagger_branch=str(meta.branch_id),
                                 tagger_key_id=str(meta.public_key_id))
        tag.signature = base64.b64encode(PKI__Crypto().sign(signing_key, self._signing_bytes(tag))).decode()
        ciphertext    = self.crypto.encrypt(c.read_key, json.dumps(tag.json()).encode())
        tag_id        = c.obj_store.store(ciphertext)
        self.api.batch(str(c.vault_id), str(c.write_key),
                       [dict(op='write', file_id=f'bare/data/{tag_id}', data=base64.b64encode(ciphertext).decode('ascii'))])
        entry = Schema__Tag_Ref(name=name, tag_id=tag_id, timestamp_ms=int(tag.timestamp_ms), deleted=False)
        self._write_entry(c, directory, entry)
        return dict(name=name, tag_id=tag_id, commit_id=target, moved_from=self._commit_of(c, existing) if existing else '')

    def delete(self, directory: str, name: str) -> dict:
        c     = self._init_components(directory)
        index = self._index(c, directory, refresh=True)
        ref   = self._live_ref(index, name)
        if ref is None:
            raise Vault__Tag_Error(f'no tag named {name!r}')
        stamp = max(int(time.time() * 1000), int(ref.timestamp_ms or 0) + 1)   # a tombstone must sort after what it deletes
        self._write_entry(c, directory, Schema__Tag_Ref(name=name, tag_id=str(ref.tag_id), timestamp_ms=stamp, deleted=True))
        return dict(name=name, tag_id=str(ref.tag_id))

    # --------------------------------------------------------------- helpers
    def _index(self, c, directory: str, refresh: bool):
        if refresh:
            try:
                Vault__Index_Sync(crypto=self.crypto, api=self.api).refresh(c, directory)   # read-only: no write-back
            except Exception:
                pass                                                                         # offline: this clone's copy
        return c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)

    def _live_ref(self, index, name: str):
        for t in index.tags or []:
            if str(t.name) == str(name) and not t.deleted:
                return t
        return None

    def _write_entry(self, c, directory: str, entry: Schema__Tag_Ref) -> None:
        """Merge the entry into the remote index and write it with compare-and-swap;
        save the result locally. Needs write access."""
        sync  = Vault__Index_Sync(crypto=self.crypto, api=self.api)
        local = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
        local.tags = sync.merge_tags(local.tags, [entry])
        raw, remote = sync.read_remote(c.vault_id, c.branch_index_file_id, c.read_key)
        merged = sync.merge(local, remote) if remote is not None else local
        try:
            merged = sync.upload(c.vault_id, c.branch_index_file_id, c.read_key, c.write_key, merged, expected_raw=raw)
        except Exception as error:
            if sync._is_no_write_access(error):
                raise Vault__Tag_Error('the server refused the write (no write access): pass --token, then try again')
            raise
        c.branch_manager.save_branch_index(directory, merged, c.read_key, index_file_id=c.branch_index_file_id)

    def _signing_bytes(self, tag: Schema__Object_Tag) -> bytes:
        body = {k: v for k, v in tag.json().items() if k != 'signature'}
        return json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')

    def _load_tag(self, c, tag_id: str) -> Schema__Object_Tag:
        if not c.obj_store.exists(tag_id):
            blob = (self.api.batch_read(str(c.vault_id), [f'bare/data/{tag_id}']) or {}).get(f'bare/data/{tag_id}')
            if not blob:
                raise FileNotFoundError(tag_id)
            if not self.crypto.object_id_matches(tag_id, blob):              # content address: the host cannot substitute it
                raise Vault__Tag_Error(f'the server sent bytes that do not match tag object {tag_id}; refused')
            c.obj_store.store_raw(tag_id, blob)
        return Schema__Object_Tag.from_json(json.loads(self.crypto.decrypt(c.read_key, c.obj_store.load(tag_id))))

    def _status(self, c, ref, tag: Schema__Object_Tag) -> str:
        if str(tag.name) != str(ref.name):
            return BAD                                                         # entry and signed object disagree on the name
        if not tag.signature or not tag.tagger_key_id:
            return UNSIGNED
        kid = str(tag.tagger_key_id)
        if not c.key_manager.key_exists(kid):
            Vault__Key_Fetch(crypto=self.crypto, api=self.api).fetch_missing(c, [kid])
        if not c.key_manager.key_exists(kid):
            return NO_KEY
        try:
            key = c.key_manager.load_public_key(kid, c.read_key)
            ok  = PKI__Crypto().verify(key, base64.b64decode(str(tag.signature)), self._signing_bytes(tag))
        except Exception:
            ok  = False
        return VERIFIED if ok else BAD

    def _describe(self, c, ref) -> dict:
        out = dict(name=str(ref.name), tag_id=str(ref.tag_id), commit_id='', message='', timestamp_ms=int(ref.timestamp_ms or 0),
                   tagger_key_id='', status=MISSING)
        try:
            tag = self._load_tag(c, str(ref.tag_id))
        except Vault__Tag_Error:
            out['status'] = BAD
            return out
        except Exception:
            return out
        out.update(commit_id=str(tag.commit_id or ''), message=str(tag.message or ''), timestamp_ms=int(tag.timestamp_ms or 0),
                   tagger_key_id=str(tag.tagger_key_id or ''), status=self._status(c, ref, tag))
        return out

    def _commit_of(self, c, ref) -> str:
        try:
            return str(self._load_tag(c, str(ref.tag_id)).commit_id)
        except Exception:
            return str(ref.tag_id)

    def _resolve_commit(self, c, directory: str, commit_id: str) -> str:
        if not commit_id:
            raise Vault__Tag_Error('nothing to tag: this clone has no commits yet')
        from sgit_ai.core.actions.history.Vault__Revision import Vault__Revision
        from sgit_ai.core.Vault__Errors                   import Vault__Revision_Error
        try:
            target = Vault__Revision(crypto=self.crypto, api=self.api).resolve(directory, commit_id)   # HEAD~1, a tag, a short id …
            Vault__Commit(crypto=self.crypto, pki=c.pki, object_store=c.obj_store, ref_manager=c.ref_manager).load_commit(target, c.read_key)
        except Vault__Revision_Error as error:
            raise Vault__Tag_Error(str(error))
        except Exception:
            raise Vault__Tag_Error(f'{commit_id} is not a commit this clone has')
        return target

    def _on_server(self, c, commit_id: str) -> bool:
        try:
            return bool((self.api.batch_read(str(c.vault_id), [f'bare/data/{commit_id}']) or {}).get(f'bare/data/{commit_id}'))
        except Exception:
            return False
