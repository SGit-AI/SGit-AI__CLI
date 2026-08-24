"""Vault__Mirror — custody without access (P5).

A keyless client copies a published vault it cannot read: every filename in a
vault derives from the read key, so the manifest is what makes this possible
at all (invariant I3). The copy is verifiable and byte-identical to the
source — and unreadable, which is the point, not a limitation.

Integrity rules:
  SP-3 (must-fix) — for obj-cas-imm-* objects the mirror RECOMPUTES the id
      from the fetched bytes and IGNORES the manifest sha256: the manifest is
      self-attested by the same host, so its hash is not an authority; the
      content-address is. A mismatch refuses that object, per object.
      (Post-move caveat, raised in the phase report: `sgit vault move`
      re-encrypts in place keeping ids, so a moved vault's CAS objects
      cannot content-verify keylessly — they are counted as id-mismatched
      and treated as host-attested, never silently accepted.)
  Refs/indexes/keys are not content-addressed: they fall back to the
      manifest sha256 and are flagged host-attested-only in the output.
  SP-8 (must-fix) — every manifest file_id is routed through
      Vault__Path_Guard before being used as a write path; object count and
      total size are bounded; duplicate/conflicting file_ids are rejected.
"""
import json
import os

from sgit_ai.core.Vault__Sync__Base               import Vault__Sync__Base
from sgit_ai.network.api.Vault__API__Static       import Vault__API__Static
from sgit_ai.storage.Vault__Path_Guard            import Vault__Path_Guard, Vault__Unsafe_Path_Error

MAX_OBJECT_COUNT = 100_000
MAX_TOTAL_BYTES  = 10 * 1024 * 1024 * 1024        # 10 GB — generous, but finite (SP-8)

MSG_NO_LISTING = (
    'cannot mirror without a listing.\n'
    '  This host offers no directory listing and the folder has no manifest.json,\n'
    '  so no filename can be derived — every name in a vault comes from the read key.\n'
    '  Ask the publisher to republish with sgit >= 0.15.6 (which always emits a manifest).'
)


class Vault__Mirror(Vault__Sync__Base):

    def mirror(self, source: str, dest_dir: str) -> dict:
        """Copy a published vault from source (URL or folder) into dest_dir.
        No key material is used or written; per-object failures never abort
        the run."""
        transport = Vault__API__Static(base_url=source)
        transport.setup()
        manifest = self._load_manifest(transport)
        if manifest is None:
            raise RuntimeError(MSG_NO_LISTING)

        vault_id = str(manifest.get('vault_id', ''))
        objects  = self._validated_objects(manifest)
        os.makedirs(dest_dir, exist_ok=True)

        copied, refused, host_attested = [], [], []
        for file_id, _size, manifest_sha in objects:
            data = transport.read(vault_id, file_id)
            if data is None:
                refused.append((file_id, 'absent on host'))
                continue
            verdict = self._verify_object(file_id, data, manifest_sha)
            if verdict == 'refused':
                refused.append((file_id, 'bytes do not match'))
                continue
            if not self._write(dest_dir, file_id, data):
                refused.append((file_id, 'unsafe path'))
                continue
            copied.append(file_id)
            if verdict == 'host-attested':
                host_attested.append(file_id)

        self._mirror_surface(transport, manifest, dest_dir, copied, refused)
        return dict(vault_id      = vault_id,
                    dest_dir      = dest_dir,
                    copied        = copied,
                    refused       = refused,
                    host_attested = sorted(host_attested))

    def verify(self, dest_dir: str) -> dict:
        """Re-check an existing mirror without fetching (--verify)."""
        manifest_path = os.path.join(dest_dir, 'manifest.json')
        if not os.path.isfile(manifest_path):
            raise RuntimeError(f'no manifest.json in {dest_dir} — not a mirror')
        with open(manifest_path) as f:
            manifest = json.load(f)
        objects = self._validated_objects(manifest)
        ok, failed, host_attested = [], [], []
        for file_id, _size, manifest_sha in objects:
            try:
                path = Vault__Path_Guard().safe_join(dest_dir, file_id)
            except Vault__Unsafe_Path_Error:
                failed.append((file_id, 'unsafe path'))
                continue
            if not os.path.isfile(path):
                failed.append((file_id, 'missing'))
                continue
            with open(path, 'rb') as f:
                data = f.read()
            verdict = self._verify_object(file_id, data, manifest_sha)
            if verdict == 'refused':
                failed.append((file_id, 'bytes do not match'))
                continue
            ok.append(file_id)
            if verdict == 'host-attested':
                host_attested.append(file_id)
        return dict(ok=ok, failed=failed, host_attested=sorted(host_attested))

    # --- internals ----------------------------------------------------------

    def _load_manifest(self, transport: Vault__API__Static) -> dict:
        manifest_bytes = transport.read_root_file('manifest.json')
        if manifest_bytes:
            try:
                return json.loads(manifest_bytes)
            except Exception:
                return None
        if transport.is_local():
            # a folder has a listing even without a manifest: mirror what is there
            file_ids = transport.list_files('', prefix='bare/')
            if file_ids:
                return {'vault_id': '', 'objects': [{'file_id': fid} for fid in file_ids]}
        return None

    def _validated_objects(self, manifest: dict) -> list:
        """(file_id, size, sha256) with SP-8's bounds and dedupe applied."""
        entries = manifest.get('objects', [])
        if len(entries) > MAX_OBJECT_COUNT:
            raise RuntimeError(f'manifest lists {len(entries)} objects — over the '
                               f'{MAX_OBJECT_COUNT} bound; refusing (hostile manifest?)')
        seen, result, total = {}, [], 0
        for entry in entries:
            file_id = str(entry.get('file_id', '') or '')
            if not file_id:
                continue
            size = int(entry.get('size', 0) or 0)
            sha  = str(entry.get('sha256', '') or '')
            if file_id in seen:
                if seen[file_id] != (size, sha):
                    raise RuntimeError(f'manifest lists conflicting entries for {file_id} — '
                                       f'refusing (hostile manifest?)')
                continue                                   # exact duplicate: ignore
            seen[file_id] = (size, sha)
            total += max(size, 0)
            if total > MAX_TOTAL_BYTES:
                raise RuntimeError(f'manifest total size exceeds {MAX_TOTAL_BYTES} bytes — '
                                   f'refusing (hostile manifest?)')
            result.append((file_id, size, sha))
        return result

    def _verify_object(self, file_id: str, data: bytes, manifest_sha: str) -> str:
        """'verified' | 'host-attested' | 'refused' — keyless, per SP-3."""
        object_name = file_id.rsplit('/', 1)[-1]
        if object_name.startswith('obj-cas-imm-'):
            if self.crypto.compute_object_id(data) == object_name:
                return 'verified'                          # the content-address decides
            return 'host-attested' if manifest_sha and \
                self.crypto.hash_data(data) == manifest_sha else 'refused'
        if not manifest_sha:
            return 'host-attested'                         # no hash to check against
        return 'host-attested' if self.crypto.hash_data(data) == manifest_sha else 'refused'

    def _write(self, dest_dir: str, file_id: str, data: bytes) -> bool:
        try:
            path = Vault__Path_Guard().safe_join(dest_dir, file_id)   # SP-8
        except Vault__Unsafe_Path_Error:
            return False
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)
        return True

    def _mirror_surface(self, transport, manifest, dest_dir, copied, refused) -> None:
        """Copy the declared plaintext surface — except key files: a mirror is
        custody, never access, so it writes no key file (the acceptance's
        'writes no key file' literally)."""
        for entry in manifest.get('plaintext_surface', []) or []:
            path = str(entry.get('path', '') or '')
            if not path or path.startswith('sgit_'):       # never a key file
                continue
            data = transport.read_root_file(path)
            if data is None:
                refused.append((path, 'absent on host'))
                continue
            expected = str(entry.get('sha256', '') or '')
            if path != 'manifest.json' and expected and self.crypto.hash_data(data) != expected:
                refused.append((path, 'bytes do not match declared hash'))
                continue
            if self._write(dest_dir, path, data):
                copied.append(path)
            else:
                refused.append((path, 'unsafe path'))
