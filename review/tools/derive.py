"""review/tools/derive.py — the code layer of review/, derived by a parser, never by a model.

Reads review/slice.json (the files in scope, as data), parses each Python file with the
standard library `ast`, and writes review/graph/:

    files.json     one node per file: path, sha256, lines, group, classes, functions
    classes.json   one node per class: qualified name, file, lines, bases, methods
    methods.json   one node per function or method: qualified name, file, lines, arguments,
                   the calls it makes (resolved to a slice node where the target is unambiguous,
                   otherwise kept as the dotted name seen), and the tests that reach it
    tests.json     one node per test function under tests/ that imports a slice module
    index.json     counts, the tree hash of the inputs, and the tool version

Every node carries its source (path, lines) and every file carries provenance (the tree hash it
was derived from). Output is deterministic: sorted keys, sorted lists, one trailing newline.

    python3 review/tools/derive.py            # derive
    python3 review/tools/derive.py --check    # exit 1 if review/graph/ is stale or hand-edited

Non-Python files in the slice (workflows, pyproject) are hashed and listed in files.json with
no classes or functions; they are not parsed.
"""
import ast
import hashlib
import json
import os
import sys

TOOL_VERSION = '0.1.0'


class Review__Derive:

    def __init__(self, repo_root: str):
        self.repo_root  = repo_root
        self.slice_path = os.path.join(repo_root, 'review', 'slice.json')
        self.graph_dir  = os.path.join(repo_root, 'review', 'graph')
        self.slice      = self.read_json(self.slice_path)
        self.files      = []
        self.classes    = []
        self.methods    = []
        self.tests      = []
        self.by_module  = {}                      # dotted module -> file node
        self.class_names = {}                     # simple class name -> [qualified names]

    # --- helpers -------------------------------------------------------------

    def read_json(self, path: str) -> dict:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def read_bytes(self, rel: str) -> bytes:
        with open(os.path.join(self.repo_root, rel), 'rb') as f:
            return f.read()

    def sha256(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def module_of(self, rel: str) -> str:
        return rel[:-3].replace('/', '.') if rel.endswith('.py') else ''

    def dotted(self, node) -> str:
        """The dotted name of a call target as written: `a.b.c(...)` -> 'a.b.c'."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = self.dotted(node.value)
            return f'{base}.{node.attr}' if base else node.attr
        if isinstance(node, ast.Call):
            return self.dotted(node.func)
        return ''

    # --- parsing -------------------------------------------------------------

    def slice_files(self) -> list:
        out = []
        for group, spec in sorted(self.slice['groups'].items()):
            for rel in spec['files']:
                out.append((group, rel))
        return out

    def parse_file(self, group: str, rel: str) -> None:
        data = self.read_bytes(rel)
        node = dict(path=rel, group=group, sha256=self.sha256(data),
                    lines=data.count(b'\n') + (0 if data.endswith(b'\n') or not data else 1),
                    module=self.module_of(rel), classes=[], functions=[])
        self.files.append(node)
        if not rel.endswith('.py'):
            return
        tree = ast.parse(data, filename=rel)
        self.by_module[node['module']] = node
        for item in tree.body:
            if isinstance(item, ast.ClassDef):
                self.parse_class(node, item)
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.parse_function(node, item, owner=None)

    def parse_class(self, file_node: dict, cls: ast.ClassDef) -> None:
        qualified = f"{file_node['module']}.{cls.name}"
        bases     = sorted(self.dotted(b) for b in cls.bases if self.dotted(b))
        class_node = dict(name=cls.name, qualified=qualified, path=file_node['path'],
                          lines=[cls.lineno, cls.end_lineno], bases=bases, methods=[])
        self.classes.append(class_node)
        self.class_names.setdefault(cls.name, []).append(qualified)
        file_node['classes'].append(qualified)
        for item in cls.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.parse_function(file_node, item, owner=class_node)

    def parse_function(self, file_node: dict, fn, owner: dict) -> None:
        qualified = f"{owner['qualified']}.{fn.name}" if owner else f"{file_node['module']}.{fn.name}"
        args      = [a.arg for a in fn.args.args if a.arg != 'self']
        calls     = sorted({self.dotted(c) for c in ast.walk(fn) if isinstance(c, ast.Call) and self.dotted(c)})
        node = dict(name=fn.name, qualified=qualified, path=file_node['path'],
                    lines=[fn.lineno, fn.end_lineno], owner=owner['qualified'] if owner else None,
                    args=args, calls=calls, resolved_calls=[])
        self.methods.append(node)
        if owner:
            owner['methods'].append(qualified)
        else:
            file_node['functions'].append(qualified)

    # --- resolution ----------------------------------------------------------

    def resolve_calls(self) -> None:
        """A call `Name(...)` where Name is a class defined once in the slice resolves to that
        class; `self.<method>(...)` resolves to the method on the same class when it exists;
        anything else stays as the dotted name seen."""
        methods_by_qualified = {m['qualified']: m for m in self.methods}
        for m in self.methods:
            resolved = set()
            for call in m['calls']:
                if call.startswith('self.') and m['owner'] and call.count('.') == 1:
                    target = f"{m['owner']}.{call[5:]}"
                    if target in methods_by_qualified:
                        resolved.add(target)
                        continue
                head = call.split('.')[0]
                if head in self.class_names and len(self.class_names[head]) == 1:
                    resolved.add(self.class_names[head][0])
            m['resolved_calls'] = sorted(resolved)

    # --- tests ---------------------------------------------------------------

    def collect_tests(self) -> None:
        """A test reaches a slice module when its file imports that module (ast-level import
        statements only; no execution). Each test function becomes a node naming the slice
        modules its file imports."""
        modules = set(self.by_module)
        tests_root = os.path.join(self.repo_root, 'tests')
        for root, dirs, files in os.walk(tests_root):
            dirs.sort()
            for name in sorted(files):
                if not (name.startswith('test_') and name.endswith('.py')):
                    continue
                rel  = os.path.relpath(os.path.join(root, name), self.repo_root)
                data = self.read_bytes(rel)
                try:
                    tree = ast.parse(data, filename=rel)
                except SyntaxError:
                    continue
                imported = set()
                for item in ast.walk(tree):
                    if isinstance(item, ast.ImportFrom) and item.module in modules:
                        imported.add(item.module)
                    elif isinstance(item, ast.Import):
                        for alias in item.names:
                            if alias.name in modules:
                                imported.add(alias.name)
                if not imported:
                    continue
                for item in ast.walk(tree):
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith('test_'):
                        owner = None
                        for cls in ast.walk(tree):
                            if isinstance(cls, ast.ClassDef) and item in cls.body:
                                owner = cls.name
                        self.tests.append(dict(name=item.name, owner=owner, path=rel,
                                               lines=[item.lineno, item.end_lineno],
                                               reaches=sorted(imported)))
        by_module_tests = {}
        for t in self.tests:
            for mod in t['reaches']:
                by_module_tests.setdefault(mod, []).append(f"{t['path']}::{t['owner'] + '::' if t['owner'] else ''}{t['name']}")
        for f in self.files:
            if f['module']:
                f['tests_importing'] = sorted(by_module_tests.get(f['module'], []))

    # --- output --------------------------------------------------------------

    def tree_hash(self) -> str:
        parts = [f"{f['path']} {f['sha256']}" for f in sorted(self.files, key=lambda f: f['path'])]
        return self.sha256('\n'.join(parts).encode())

    def write_json(self, name: str, payload) -> None:
        os.makedirs(self.graph_dir, exist_ok=True)
        with open(os.path.join(self.graph_dir, name), 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=1, sort_keys=True)
            f.write('\n')

    def build(self) -> dict:
        for group, rel in self.slice_files():
            self.parse_file(group, rel)
        self.resolve_calls()
        self.collect_tests()
        tree = self.tree_hash()
        provenance = dict(derived_from=tree, tool='review/tools/derive.py', tool_version=TOOL_VERSION,
                          slice=self.slice['name'], parser='python ast (stdlib)')
        files   = dict(provenance=provenance, nodes=sorted(self.files,   key=lambda n: n['path']))
        classes = dict(provenance=provenance, nodes=sorted(self.classes, key=lambda n: n['qualified']))
        methods = dict(provenance=provenance, nodes=sorted(self.methods, key=lambda n: n['qualified']))
        tests   = dict(provenance=provenance, nodes=sorted(self.tests,   key=lambda n: (n['path'], n['lines'][0])))
        reached = [f['path'] for f in self.files if f.get('tests_importing')]
        index   = dict(provenance=provenance,
                       counts=dict(files=len(self.files), python_files=len(self.by_module),
                                   lines=sum(f['lines'] for f in self.files),
                                   classes=len(self.classes), methods=len(self.methods),
                                   python_files_some_test_imports=len(reached),
                                   tests_reaching_the_slice=len(self.tests)),
                       python_files_no_test_imports=sorted(f['path'] for f in self.files
                                                           if f['module'] and not f.get('tests_importing')),
                       groups={g: sorted(spec['files']) for g, spec in self.slice['groups'].items()})
        return dict(files=files, classes=classes, methods=methods, tests=tests, index=index)

    def derive(self) -> dict:
        out = self.build()
        for name, payload in out.items():
            self.write_json(f'{name}.json', payload)
        self.write_readme(out['index'])
        return out['index']

    def check(self) -> int:
        """Recompute and compare byte-for-byte with what is on disk."""
        fresh = self.build()
        stale = []
        for name, payload in fresh.items():
            path = os.path.join(self.graph_dir, f'{name}.json')
            want = json.dumps(payload, indent=1, sort_keys=True) + '\n'
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    have = f.read()
            except FileNotFoundError:
                have = None
            if have != want:
                stale.append(name)
        if stale:
            print(f"review/graph is stale or hand-edited: {', '.join(stale)}  (run review/tools/derive.py)")
            return 1
        print(f"review/graph is fresh: derived_from {fresh['index']['provenance']['derived_from'][:16]}")
        return 0

    def write_readme(self, index: dict) -> None:
        c = index['counts']
        lines = ['# review/graph — the code layer, derived',
                 '',
                 f"Written by `review/tools/derive.py` {TOOL_VERSION} from `review/slice.json`"
                 f" (slice `{index['provenance']['slice']}`), tree hash `{index['provenance']['derived_from'][:16]}…`.",
                 'Do not edit by hand: `python3 review/tools/derive.py --check` fails when these files differ from a fresh derivation.',
                 '',
                 '| Count | |', '|---|---|',
                 f"| files in the slice | {c['files']} ({c['python_files']} Python) |",
                 f"| lines | {c['lines']} |",
                 f"| classes | {c['classes']} |",
                 f"| functions and methods | {c['methods']} |",
                 f"| Python files some test imports | {c['python_files_some_test_imports']} of {c['python_files']} |",
                 f"| test functions whose file imports a slice module | {c['tests_reaching_the_slice']} |",
                 '',
                 'Nodes: `files.json` (with the tests importing each module), `classes.json`, `methods.json` (with calls and resolved calls), `tests.json`, `index.json`.',
                 'Every node carries its path and lines; every file carries the tree hash it was derived from.',
                 '']
        with open(os.path.join(self.graph_dir, 'README.md'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))


if __name__ == '__main__':
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    tool = Review__Derive(root)
    if '--check' in sys.argv:
        sys.exit(tool.check())
    counts = tool.derive()['counts']
    print(json.dumps(counts, indent=1))
