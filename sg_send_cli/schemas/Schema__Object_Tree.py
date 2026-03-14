from osbot_utils.type_safe.Type_Safe                              import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Schema_Version              import Safe_Str__Schema_Version
from sg_send_cli.schemas.Schema__Object_Tree_Entry                import Schema__Object_Tree_Entry


class Schema__Object_Tree(Type_Safe):
    schema  : Safe_Str__Schema_Version = None                      # v2: e.g. 'tree_v1'
    entries : list[Schema__Object_Tree_Entry]

    def entry_by_path(self, path: str):
        for entry in self.entries:
            if entry.path == path:
                return entry
        return None

    def entry_by_name(self, name: str):
        for entry in self.entries:
            if entry.name == name:
                return entry
        return None

    def paths(self):
        return [str(entry.path) for entry in self.entries if entry.path is not None]

    def names(self):
        return [str(entry.name) for entry in self.entries if entry.name is not None]

    def add_entry(self, path: str, blob_id: str, size: int):
        entry = Schema__Object_Tree_Entry(path=path, blob_id=blob_id, size=size)
        self.entries.append(entry)
        return entry

    def add_sub_tree_entry(self, name: str, tree_id: str):
        entry = Schema__Object_Tree_Entry(name=name, tree_id=tree_id, size=0)
        self.entries.append(entry)
        return entry

    def add_file_entry(self, name: str, blob_id: str, size: int, content_hash: str = None):
        entry = Schema__Object_Tree_Entry(name=name, blob_id=blob_id, size=size, content_hash=content_hash)
        self.entries.append(entry)
        return entry
