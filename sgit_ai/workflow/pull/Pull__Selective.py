"""Pull__Selective — what a pull writes on a selective working copy.

A full clone writes every changed path. A selective one (a clone made with
--no-checkout or --sparse) writes only the changed paths it has checked out, or
nothing with `pull --no-checkout`; what it did not write is reported and recorded
(`.sg_vault/local/last-pull.json`) so `sgit checkout --since-pull` can write it.
"""
from osbot_utils.type_safe.Type_Safe                  import Type_Safe
from sgit_ai.safe_types.Safe_Str__File_Path          import Safe_Str__File_Path
from sgit_ai.storage.Vault__Checkout_Set             import Vault__Checkout_Set


class Pull__Selective(Type_Safe):
    directory   : Safe_Str__File_Path = None
    sparse      : bool                = False
    no_checkout : bool                = False
    paths       : object              = None       # the checkout set (a set of paths) or None (no record)
    obj_store   : object              = None
    written     : list                             # what this pull wrote

    def setup(self, directory: str, obj_store, local_config, no_checkout: bool):
        self.directory   = Safe_Str__File_Path(directory)
        self.obj_store   = obj_store
        self.sparse      = bool(getattr(local_config, 'sparse', False)) if local_config is not None else False
        self.no_checkout = bool(no_checkout) and self.sparse
        self.paths       = Vault__Checkout_Set().load(str(directory)) if self.sparse else None
        return self

    def split(self, apply_map: dict) -> tuple:
        """(what to write, what not to) of the changed entries."""
        if not self.sparse:
            return dict(apply_map), {}
        if self.no_checkout:
            return {}, dict(apply_map)
        cset = Vault__Checkout_Set()
        to_write, skipped = {}, {}
        for path, entry in apply_map.items():
            (to_write if cset.materialised(path, entry, self.obj_store, True, self.paths) else skipped)[path] = entry
        return to_write, skipped

    def after_write(self, written: list, deleted: list) -> None:
        self.written = list(written)
        if self.sparse and self.paths is not None:
            cset = Vault__Checkout_Set()
            cset.add(str(self.directory), written)
            cset.discard(str(self.directory), deleted)
            self.paths = cset.load(str(self.directory))

    def record_pull(self, head: str, added, modified, deleted) -> None:
        if self.sparse:                                                      # a full clone wrote everything: no note
            Vault__Checkout_Set().record_pull(str(self.directory), head, added or [], modified or [], deleted or [], self.written)
