# Git_Repo__Reader__Service

A pure-Python Git repository reader that reads directly from the `.git` folder without shelling out to `git` or using external dependencies like `gitpython` or `dulwich`.

Built with the OSBot-Utils **Type_Safe** architecture — all data structures are strongly-typed schemas with validated primitives.

---

## Why This Exists

| Traditional Approach | This Approach |
|---------------------|---------------|
| Shell out to `git log`, parse text | Read `.git/objects` directly |
| Depend on `gitpython` (heavy) | Zero external dependencies |
| Raw strings everywhere | Type_Safe schemas throughout |
| Hope the git binary exists | Works anywhere Python runs |

---

## Package Structure

```
git_reader/
├── __init__.py                          # Main exports
│
├── Git_Repo__Reader__Service.py         # High-level API (start here)
├── Git_Object__Reader.py                # Low-level object reading
├── Git_Object__Parser.py                # Parse commits, trees, authors
├── Git_Ref__Reader.py                   # Read refs, HEAD, branches
│
├── primitives/                          # New Type_Safe primitives
│   ├── Safe_Str__Git__Commit_Message.py # Up to 64KB, preserves formatting
│   ├── Safe_Str__Git__Tree_Path.py      # File paths in tree entries
│   └── Safe_Str__Git__Author_Line.py    # "Name <email> timestamp tz"
│
├── enums/
│   ├── Enum__Git__File_Change_Status.py # A (Added), M (Modified), D (Deleted)
│   └── Enum__Git__Object_Type.py        # commit, tree, blob, tag
│
├── schemas/                             # Type_Safe data structures
│   ├── Schema__Git__Author_Info.py      # Parsed author: name, email, timestamp, tz
│   ├── Schema__Git__Branch.py           # Branch name + tip commit SHA
│   ├── Schema__Git__Commit.py           # Full commit with sha + sha_short
│   ├── Schema__Git__Commit_Summary.py   # Commit + files changed
│   ├── Schema__Git__File_Change.py      # Path + status (A/M/D)
│   └── Schema__Git__Tree_Entry.py       # Tree entry: mode, name, sha
│
├── collections/                         # Type_Safe collections
│   ├── List__Git__SHAs.py
│   ├── List__Git__Branches.py
│   ├── List__Git__Commits.py
│   ├── List__Git__File_Changes.py
│   └── Dict__Git__Files__By_Path.py
│
└── tests/                               # Real-repo tests (no mocks)
    ├── test__Git_Object__Reader.py
    ├── test__Git_Object__Parser.py
    ├── test__Git_Ref__Reader.py
    └── test__Git_Repo__Reader__Service.py
```

---

## Quick Start

```python
from git_reader import Git_Repo__Reader__Service
from osbot_utils.type_safe.primitives.domains.files.safe_str.Safe_Str__File__Path import Safe_Str__File__Path

# Initialize with repo path
service = Git_Repo__Reader__Service(
    repo_path = Safe_Str__File__Path("/path/to/your/repo")
)

# List branches
for branch in service.branches():
    print(f"{branch.name} → {branch.commit_sha}")

# Get HEAD commit
summary = service.head_commit()
print(f"HEAD: {summary.commit.sha_short} - {summary.commit.message}")
print(f"Files changed: {len(summary.files_changed)}")

# Walk commit history
for commit in service.commits(depth=5):
    print(f"{commit.sha_short} | {commit.author.name} | {commit.message.split(chr(10))[0]}")
```

---

## Core Components

### Git_Repo__Reader__Service
The high-level API. Initialize with a repo path and it auto-detects the `.git` folder.

| Method | Returns | Description |
|--------|---------|-------------|
| `branches()` | `List[Schema__Git__Branch]` | All branches with tip SHAs |
| `branch_names()` | `List[Safe_Str__Git__Branch]` | Just branch names |
| `head_sha()` | `Safe_Str__SHA1` | Current HEAD commit SHA |
| `head_commit()` | `Schema__Git__Commit_Summary` | HEAD commit + files changed |
| `commit(sha)` | `Schema__Git__Commit` | Full commit data |
| `commits(branch?, sha?, depth=10)` | `List[Schema__Git__Commit]` | Walk commit history |
| `files_changed(sha)` | `List[Schema__Git__File_Change]` | Diff against parent |

### Git_Object__Reader
Low-level reader for `.git/objects`. Handles:
- **Loose objects**: `.git/objects/ab/cdef123...` (zlib compressed)
- **Packfiles**: `.git/objects/pack/*.pack` with index lookup
- **Deltas**: OFS_DELTA and REF_DELTA reconstruction

### Git_Object__Parser
Parses raw bytes into Type_Safe schemas:
- `parse_commit(sha, bytes)` → `Schema__Git__Commit`
- `parse_tree(bytes)` → `List[Schema__Git__Tree_Entry]`
- `flatten_tree(sha)` → `Dict[path, blob_sha]` (recursive)

### Git_Ref__Reader
Reads Git references:
- `head_sha()` — resolves HEAD (symbolic or detached)
- `branches()` — enumerates `refs/heads/*`
- `resolve_ref(path)` — handles loose refs and `packed-refs`

---

## Key Schemas

### Schema__Git__Commit
```python
class Schema__Git__Commit(Type_Safe):
    sha         : Safe_Str__SHA1           # Full 40-char SHA
    sha_short   : Safe_Str__SHA1__Short    # 7-char display SHA
    tree_sha    : Safe_Str__SHA1           # Tree object SHA
    parent_shas : List[Safe_Str__SHA1]     # 0+ parents
    author      : Schema__Git__Author_Info
    committer   : Schema__Git__Author_Info
    message     : Safe_Str__Git__Commit_Message
```

The `sha_short` field is auto-populated so you never need to slice `sha[:7]` yourself.

### Schema__Git__File_Change
```python
class Schema__Git__File_Change(Type_Safe):
    path   : Safe_Str__Git__Tree_Path
    status : Enum__Git__File_Change_Status  # ADDED, MODIFIED, DELETED
```

---

## Primitives Reused from OSBot-Utils

These existing primitives are imported, not recreated:

| Primitive | Validation | Used For |
|-----------|------------|----------|
| `Safe_Str__SHA1` | `^[a-fA-F0-9]{40}$` | Full commit/tree/blob SHAs |
| `Safe_Str__SHA1__Short` | `^[a-fA-F0-9]{7}$` | Display SHAs |
| `Safe_Str__Git__Branch` | git-check-ref-format rules | Branch names |

---

## New Primitives Created

| Primitive | Constraints | Purpose |
|-----------|-------------|---------|
| `Safe_Str__Git__Commit_Message` | max 64KB, `trim_whitespace=False` | Preserve message formatting |
| `Safe_Str__Git__Tree_Path` | max 4096 chars | File paths in trees |
| `Safe_Str__Git__Author_Line` | max 1024 chars | Raw author/committer line |

---

## Tests

Tests use **real git repositories** — they auto-detect the repo they're running inside.

```bash
# Run all tests
python -m pytest git_reader/tests/

# Run specific test file
python -m pytest git_reader/tests/test__Git_Repo__Reader__Service.py -v
```

Test coverage:
- Object reading (loose + packfile)
- Commit/tree parsing
- Author line parsing
- Branch enumeration
- HEAD resolution
- Commit history walking
- File change detection (A/M/D)
- sha_short derivation

---

## Limitations

1. **Read-only** — this is a reader, not a writer
2. **No working tree ops** — no `status`, `diff` against working tree
3. **First-parent only** — `commits()` follows first parent (no merge traversal)
4. **No submodules** — doesn't recurse into submodule `.git` folders
5. **No shallow clones** — assumes full history available

---

## Requirements

- Python 3.10+
- `osbot_utils` (for Type_Safe infrastructure)

No other dependencies.
