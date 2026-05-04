"""
Layer import enforcement — B12.

Parses source files with ast (no import execution) and asserts that
each layer respects the D6 dependency rules. Fails CI if a violation
is introduced.

Current enforcement scope (B12):
  - crypto: may not import from storage or any higher layer
  - storage: may import crypto, safe_types, schemas, and sibling storage files

B13 will extend this to core/network/plugins when those layers land.

Known pre-existing violations (tracked, not yet fixed):
  - sgit_ai/crypto/Vault__Crypto.py imports sgit_ai.network.transfer.Simple_Token
    (inline import inside two methods; fix requires refactor in B13)
"""
import ast
import os


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
SRC_ROOT  = os.path.join(REPO_ROOT, 'sgit_ai')

LAYERS = {
    'crypto'  : os.path.join(SRC_ROOT, 'crypto'),
    'storage' : os.path.join(SRC_ROOT, 'storage'),
}

# Pre-existing violations approved for B12 — to be fixed in B13.
KNOWN_VIOLATIONS = {
    'sgit_ai/crypto/Vault__Crypto.py: imports sgit_ai.network.transfer.Simple_Token',
}


def _collect_py_files(directory):
    for root, _, files in os.walk(directory):
        for name in files:
            if name.endswith('.py'):
                yield os.path.join(root, name)


def _sgit_ai_imports(filepath):
    with open(filepath, encoding='utf-8') as fh:
        tree = ast.parse(fh.read(), filename=filepath)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith('sgit_ai.'):
                    imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith('sgit_ai.'):
                imports.append(node.module)
    return imports


def _violation_key(path, imp):
    return f'{os.path.relpath(path, REPO_ROOT)}: imports {imp}'


class Test_Layer_Imports:

    def test_crypto_does_not_import_storage(self):
        violations = []
        for path in _collect_py_files(LAYERS['crypto']):
            for imp in _sgit_ai_imports(path):
                if imp.startswith('sgit_ai.storage.'):
                    key = _violation_key(path, imp)
                    if key not in KNOWN_VIOLATIONS:
                        violations.append(key)
        assert violations == [], (
            'crypto layer must not import storage:\n' + '\n'.join(violations)
        )

    def test_crypto_does_not_import_higher_layers(self):
        forbidden = ('sgit_ai.sync.', 'sgit_ai.objects.', 'sgit_ai.cli.',
                     'sgit_ai.api.', 'sgit_ai.transfer.', 'sgit_ai.workflow.',
                     'sgit_ai.pki.')
        violations = []
        for path in _collect_py_files(LAYERS['crypto']):
            for imp in _sgit_ai_imports(path):
                if any(imp.startswith(p) for p in forbidden):
                    key = _violation_key(path, imp)
                    if key not in KNOWN_VIOLATIONS:
                        violations.append(key)
        assert violations == [], (
            'crypto layer must not import from higher layers:\n' + '\n'.join(violations)
        )

    def test_known_violations_are_still_present(self):
        """Guard: if a known violation is fixed, remove it from KNOWN_VIOLATIONS."""
        found = set()
        all_layer_files = list(_collect_py_files(LAYERS['crypto'])) + list(_collect_py_files(LAYERS['storage']))
        for path in all_layer_files:
            for imp in _sgit_ai_imports(path):
                key = _violation_key(path, imp)
                if key in KNOWN_VIOLATIONS:
                    found.add(key)
        gone = KNOWN_VIOLATIONS - found
        assert gone == set(), (
            'Known violation(s) no longer present — remove from KNOWN_VIOLATIONS:\n'
            + '\n'.join(gone)
        )

    def test_storage_does_not_import_sync(self):
        violations = []
        for path in _collect_py_files(LAYERS['storage']):
            for imp in _sgit_ai_imports(path):
                if imp.startswith('sgit_ai.sync.'):
                    violations.append(_violation_key(path, imp))
        assert violations == [], (
            'storage layer must not import from sgit_ai.sync:\n' + '\n'.join(violations)
        )

    def test_storage_does_not_import_objects(self):
        violations = []
        for path in _collect_py_files(LAYERS['storage']):
            for imp in _sgit_ai_imports(path):
                if imp.startswith('sgit_ai.objects.'):
                    violations.append(_violation_key(path, imp))
        assert violations == [], (
            'storage layer must not import from sgit_ai.objects:\n' + '\n'.join(violations)
        )

    def test_storage_does_not_import_cli_or_api(self):
        forbidden = ('sgit_ai.cli.', 'sgit_ai.api.', 'sgit_ai.transfer.',
                     'sgit_ai.workflow.')
        violations = []
        for path in _collect_py_files(LAYERS['storage']):
            for imp in _sgit_ai_imports(path):
                if any(imp.startswith(p) for p in forbidden):
                    violations.append(_violation_key(path, imp))
        assert violations == [], (
            'storage layer must not import from cli/api/transfer/workflow:\n' + '\n'.join(violations)
        )

    def test_storage_allowed_imports(self):
        allowed_prefixes = ('sgit_ai.crypto.', 'sgit_ai.safe_types.',
                            'sgit_ai.schemas.', 'sgit_ai.storage.')
        violations = []
        for path in _collect_py_files(LAYERS['storage']):
            for imp in _sgit_ai_imports(path):
                if not any(imp.startswith(p) for p in allowed_prefixes):
                    violations.append(_violation_key(path, imp))
        assert violations == [], (
            'storage may only import from crypto / safe_types / schemas / storage:\n'
            + '\n'.join(violations)
        )

    def test_no_cross_layer_circular_imports(self):
        crypto_imports_storage = any(
            imp.startswith('sgit_ai.storage.')
            for path in _collect_py_files(LAYERS['crypto'])
            for imp in _sgit_ai_imports(path)
        )
        storage_imports_crypto = any(
            imp.startswith('sgit_ai.crypto.')
            for path in _collect_py_files(LAYERS['storage'])
            for imp in _sgit_ai_imports(path)
        )
        assert not (crypto_imports_storage and storage_imports_crypto), (
            'circular dependency detected between crypto and storage layers'
        )
