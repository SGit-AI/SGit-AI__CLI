from osbot_utils.type_safe.Type_Safe import Type_Safe


class Schema__Tree_Entries__Light(Type_Safe):
    """A tree for a walk that only follows ids: the tree id and its entries as the plain
    dicts of its JSON (`Vault__Sub_Tree._load_tree_entries`, ids validated), never
    parsed into Schema__Object_Tree_Entry: that parse cost ~2 ms per tree, minutes on
    a 77,227-tree vault (newsroom field report, 26 Oct)."""
    tree_id : str  = ''
    entries : list
