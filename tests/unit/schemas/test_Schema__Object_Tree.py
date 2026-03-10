from sg_send_cli.schemas.Schema__Object_Tree       import Schema__Object_Tree
from sg_send_cli.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry


class Test_Schema__Object_Tree_Entry:

    def test_create_with_defaults(self):
        entry = Schema__Object_Tree_Entry()
        assert entry.path    is None
        assert entry.blob_id is None
        assert entry.size    == 0

    def test_create_with_values(self):
        entry = Schema__Object_Tree_Entry(path='docs/readme.md', blob_id='a1b2c3d4e5f6', size=1024)
        assert entry.path    == 'docs/readme.md'
        assert entry.blob_id == 'a1b2c3d4e5f6'
        assert entry.size    == 1024

    def test_round_trip(self):
        entry    = Schema__Object_Tree_Entry(path='src/main.py', blob_id='b2c3d4e5f6a1', size=2048)
        restored = Schema__Object_Tree_Entry.from_json(entry.json())
        assert restored.json() == entry.json()


class Test_Schema__Object_Tree:

    def test_create_empty(self):
        tree = Schema__Object_Tree()
        assert tree.entries == []

    def test_add_entry(self):
        tree  = Schema__Object_Tree()
        entry = tree.add_entry('docs/readme.md', 'a1b2c3d4e5f6', 1024)
        assert len(tree.entries) == 1
        assert entry.path       == 'docs/readme.md'
        assert entry.blob_id    == 'a1b2c3d4e5f6'
        assert entry.size       == 1024

    def test_add_multiple_entries(self):
        tree = Schema__Object_Tree()
        tree.add_entry('docs/readme.md', 'a1b2c3d4e5f6', 1024)
        tree.add_entry('src/main.py',    'b2c3d4e5f6a1', 2048)
        assert len(tree.entries) == 2

    def test_entry_by_path(self):
        tree = Schema__Object_Tree()
        tree.add_entry('docs/readme.md', 'a1b2c3d4e5f6', 1024)
        tree.add_entry('src/main.py',    'b2c3d4e5f6a1', 2048)
        entry = tree.entry_by_path('src/main.py')
        assert entry is not None
        assert entry.blob_id == 'b2c3d4e5f6a1'

    def test_entry_by_path_not_found(self):
        tree = Schema__Object_Tree()
        assert tree.entry_by_path('missing.txt') is None

    def test_paths(self):
        tree = Schema__Object_Tree()
        tree.add_entry('docs/readme.md', 'a1b2c3d4e5f6', 1024)
        tree.add_entry('src/main.py',    'b2c3d4e5f6a1', 2048)
        assert tree.paths() == ['docs/readme.md', 'src/main.py']

    def test_round_trip(self):
        tree = Schema__Object_Tree()
        tree.add_entry('docs/readme.md', 'a1b2c3d4e5f6', 1024)
        tree.add_entry('src/main.py',    'b2c3d4e5f6a1', 2048)
        restored = Schema__Object_Tree.from_json(tree.json())
        assert restored.json() == tree.json()

    def test_round_trip_empty(self):
        tree     = Schema__Object_Tree()
        restored = Schema__Object_Tree.from_json(tree.json())
        assert restored.json() == tree.json()

    def test_flat_paths_no_nesting(self):
        tree = Schema__Object_Tree()
        tree.add_entry('a/b/c/deep.txt', 'c3d4e5f6a1b2', 512)
        assert tree.paths() == ['a/b/c/deep.txt']
        assert len(tree.entries) == 1
