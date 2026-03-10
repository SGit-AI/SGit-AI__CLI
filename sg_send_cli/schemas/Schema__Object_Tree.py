from osbot_utils.type_safe.Type_Safe                              import Type_Safe
from sg_send_cli.schemas.Schema__Object_Tree_Entry                import Schema__Object_Tree_Entry


class Schema__Object_Tree(Type_Safe):
    entries : list[Schema__Object_Tree_Entry]

    def entry_by_path(self, path: str):
        for entry in self.entries:
            if entry.path == path:
                return entry
        return None

    def paths(self):
        return [str(entry.path) for entry in self.entries]

    def add_entry(self, path: str, blob_id: str, size: int):
        entry = Schema__Object_Tree_Entry(path=path, blob_id=blob_id, size=size)
        self.entries.append(entry)
        return entry
