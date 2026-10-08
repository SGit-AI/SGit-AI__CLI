"""Vault__Sync__Format — show and raise a vault's format gate (sgit vault format)."""
from   sgit_ai.core.Vault__Sync__Base                 import Vault__Sync__Base
from   sgit_ai.core.actions.index.Vault__Index_Sync   import Vault__Index_Sync
from   sgit_ai.storage.Vault__Format                  import Vault__Format, FORMAT_1, FORMAT_2, FEATURE_IDS_128


class Vault__Sync__Format(Vault__Sync__Base):

    def format_info(self, directory: str) -> dict:
        c     = self._init_components(directory)
        index = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
        fmt   = Vault__Format()
        return dict(format=fmt.format_of(index), id_hex_len=fmt.id_hex_len(index),
                    min_client=fmt.min_client_of(index), features=fmt.features_of(index),
                    client=fmt.client_version(), describe=fmt.describe(index))

    def set_format(self, directory: str, format: int = None, min_client: str = None,
                   add_features: list = None, remove_features: list = None,
                   on_progress: callable = None) -> dict:
        """Raise the gate on the local index and write it to the server with
        compare-and-swap. A format can only go up (2 writes 32-hex ids for new
        objects; existing objects keep theirs, no move needed). Refuses to set a
        min_client this very client does not meet."""
        _p    = on_progress or (lambda *a, **k: None)
        c     = self._init_components(directory)
        fmt   = Vault__Format()
        index = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
        sync  = Vault__Index_Sync(crypto=self.crypto, api=self.api)
        raw, remote = sync.read_remote(c.vault_id, c.branch_index_file_id, c.read_key)
        if remote is not None:                                     # start from the gate the server holds, not this clone's copy
            index = sync.merge(index, remote)
        if index.format is None:
            index.format = fmt.format_of(index)                    # always explicit: an index without one reads as "a writer dropped the gate"
        if format is not None:
            if int(format) not in (FORMAT_1, FORMAT_2):
                raise ValueError(f'format must be 1 or 2, not {format}')
            if int(format) < fmt.format_of(index):
                raise ValueError(f'format cannot go down (vault is at {fmt.format_of(index)}); '
                                 f'objects already written at the wider id would be unreadable')
            index.format = int(format)
        if min_client is not None:
            if fmt.parse_version(min_client) is None:
                raise ValueError(f'min_client must look like MAJOR.MINOR.PATCH, not {min_client!r}')
            have = fmt.parse_version(fmt.client_version())
            if have is not None and have < fmt.parse_version(min_client):
                raise ValueError(f'min_client {min_client} is newer than this client ({fmt.client_version()}); '
                                 f'you would lock yourself out')
            index.min_client = '.'.join(map(str, fmt.parse_version(min_client)))
        feats = set(fmt.features_of(index))
        feats |= set(add_features or []); feats -= set(remove_features or [])
        if fmt.format_of(index) >= FORMAT_2:
            feats.add(FEATURE_IDS_128)
        index.features = sorted(feats)
        c.branch_manager.save_branch_index(directory, index, c.read_key, index_file_id=c.branch_index_file_id)
        _p('step', 'Writing the format gate to the server')
        merged = sync.merge(index, remote, gate='local') if remote is not None else index   # the owner's decision wins
        merged = sync.upload(c.vault_id, c.branch_index_file_id, c.read_key, c.write_key, merged,
                             expected_raw=raw, gate='local')
        c.branch_manager.save_branch_index(directory, merged, c.read_key, index_file_id=c.branch_index_file_id)
        return self.format_info(directory)
