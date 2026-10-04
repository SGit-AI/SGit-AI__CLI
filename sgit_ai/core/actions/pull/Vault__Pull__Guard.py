"""Vault__Pull__Guard — protect uncommitted work from `sgit pull`.

Bug (reported three times by the RiskMandate agent team, 3 Oct 2026): pull
checked the whole incoming tree out over the working copy, so an UNCOMMITTED
edit to a tracked file was silently replaced by the committed version — even
when the incoming commits never touched that file — and `sgit status` then
said "fully in sync". With ten agents sharing one vault that is lost work on
every pull.

This does what git does. Before the merge writes anything, the working tree
is compared with the clone HEAD tree:

  * a dirty file the merge does NOT change is carried over — not written, so
    the edit survives (git: an untouched modified file is left alone);
  * a dirty file the merge DOES change blocks the pull before any write, with
    the paths named (git: "Your local changes to the following files would be
    overwritten by merge");
  * an untracked file the merge would create with different content blocks
    too (git: "untracked working tree files would be overwritten").

"Dirty" is measured exactly as `sgit status` measures it (content hash against
the tree entry), so the two never disagree about what is uncommitted.
"""
import os
from   osbot_utils.type_safe.Type_Safe           import Type_Safe


class Vault__Pull__Guard(Type_Safe):

    def dirty_paths(self, directory: str, ours_map: dict, local_scan: dict,
                    obj_store=None, sparse: bool = False) -> dict:
        """{path: 'modified' | 'deleted' | 'untracked'} for the working tree vs HEAD.

        local_scan is Vault__Sync__Base._scan_local_directory(directory): the
        ignore-aware {path: {size, content_hash}} of what is on disk. On a
        sparse clone a tracked file whose blob was never fetched is not
        'deleted' — it was never there."""
        dirty = {}
        for path, entry in ours_map.items():
            local = local_scan.get(path)
            if local is None:
                if sparse and obj_store is not None and not obj_store.exists(entry.get('blob_id', '')):
                    continue
                dirty[path] = 'deleted'
                continue
            tracked_hash = entry.get('content_hash', '')
            if tracked_hash:
                if tracked_hash != local.get('content_hash', ''):
                    dirty[path] = 'modified'
            elif local.get('size', -1) != entry.get('size', -2):
                dirty[path] = 'modified'
        for path in local_scan:
            if path not in ours_map:
                dirty[path] = 'untracked'
        return dirty

    def plan(self, dirty: dict, ours_map: dict, merged_map: dict, local_scan: dict) -> dict:
        """Decide, per dirty path, whether the merge may proceed around it.

        Returns {'carry_over': [paths the merge must NOT write],
                 'blocked':    [(path, reason) that make the pull refuse]}.
        A path is "changed by the merge" when the merged tree's blob for it
        differs from the clone HEAD's blob for it."""
        carry_over = []
        blocked    = []
        for path, kind in sorted(dirty.items()):
            ours_blob   = (ours_map.get(path)   or {}).get('blob_id')
            merged_blob = (merged_map.get(path) or {}).get('blob_id')
            if kind == 'modified':
                if merged_blob == ours_blob:
                    carry_over.append(path)
                else:
                    blocked.append((path, 'your uncommitted edit would be overwritten'))
            elif kind == 'deleted':
                if path not in merged_map or merged_blob == ours_blob:
                    carry_over.append(path)            # stays deleted locally, as in git
                else:
                    blocked.append((path, 'deleted locally but changed by the incoming commits'))
            elif kind == 'untracked':
                if path not in merged_map:
                    continue                           # the merge does not touch it
                incoming_hash = merged_map[path].get('content_hash', '')
                if incoming_hash and incoming_hash == (local_scan.get(path) or {}).get('content_hash'):
                    continue                           # identical content — writing it is a no-op
                blocked.append((path, 'untracked file would be overwritten by an incoming file'))
        return dict(carry_over=carry_over, blocked=blocked)

    def message(self, blocked: list) -> str:
        lines = ['your local changes would be overwritten by pull:']
        for path, reason in blocked:
            lines.append(f'  {path}  ({reason})')
        lines.append('commit them (sgit commit) or stash them (sgit vault stash) and pull again; '
                     'nothing was changed')
        return '\n'.join(lines)
