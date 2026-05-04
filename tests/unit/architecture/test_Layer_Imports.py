"""
Layer import enforcement — B12 (storage) + B13 (core/network/crypto/pki).

Parses source files with ast (no import execution) and asserts that
each layer respects the D6 dependency rules. Fails CI if a violation
is introduced.

Layer rules (D6):
  crypto   — imports nothing from other sgit_ai layers
  storage  — imports only crypto, safe_types, schemas, storage
  network  — imports only crypto, safe_types, schemas, network
  core     — imports crypto, storage, network, workflow, safe_types, schemas, secrets, core
  cli      — imports anything (thin wrapper; not layer-enforced here)

Known pre-existing violations:
  - sgit_ai/crypto/Vault__Crypto.py imports sgit_ai.network.transfer.Simple_Token
    (inline import inside two methods; fix requires refactor — tracked for a future brief)
"""
import ast
import os


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
SRC_ROOT  = os.path.join(REPO_ROOT, 'sgit_ai')

LAYERS = {
    'crypto'  : os.path.join(SRC_ROOT, 'crypto'),
    'storage' : os.path.join(SRC_ROOT, 'storage'),
    'network' : os.path.join(SRC_ROOT, 'network'),
    'core'    : os.path.join(SRC_ROOT, 'core'),
}

# Pre-existing violations approved — to be fixed in a future brief.
# Vault__Transfer mixes network + storage concerns; it should move to core/.
_VAULT_TRANSFER = 'sgit_ai/network/transfer/Vault__Transfer.py'
KNOWN_VIOLATIONS = {
    'sgit_ai/crypto/Vault__Crypto.py: imports sgit_ai.network.transfer.Simple_Token',
    f'{_VAULT_TRANSFER}: imports sgit_ai.storage.Vault__Object_Store',
    f'{_VAULT_TRANSFER}: imports sgit_ai.storage.Vault__Ref_Manager',
    f'{_VAULT_TRANSFER}: imports sgit_ai.storage.Vault__Commit',
    f'{_VAULT_TRANSFER}: imports sgit_ai.storage.Vault__Storage',
    f'{_VAULT_TRANSFER}: imports sgit_ai.storage.Vault__Sub_Tree',
    f'{_VAULT_TRANSFER}: imports sgit_ai.storage.Vault__Branch_Manager',
}


class Test_Layer_Imports:

    def _collect_py_files(self, directory):
        for root, _, files in os.walk(directory):
            for name in files:
                if name.endswith('.py'):
                    yield os.path.join(root, name)

    def _sgit_ai_imports(self, filepath):
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

    def _violation_key(self, path, imp):
        return f'{os.path.relpath(path, REPO_ROOT)}: imports {imp}'

    def _check_layer(self, layer_dir, forbidden_prefixes):
        violations = []
        for path in self._collect_py_files(layer_dir):
            for imp in self._sgit_ai_imports(path):
                if any(imp.startswith(p) for p in forbidden_prefixes):
                    key = self._violation_key(path, imp)
                    if key not in KNOWN_VIOLATIONS:
                        violations.append(key)
        return violations

    # --- crypto layer ---

    def test_crypto_does_not_import_storage(self):
        v = self._check_layer(LAYERS['crypto'], ('sgit_ai.storage.',))
        assert v == [], 'crypto must not import storage:\n' + '\n'.join(v)

    def test_crypto_does_not_import_network(self):
        v = self._check_layer(LAYERS['crypto'], ('sgit_ai.network.',))
        assert v == [], 'crypto must not import network:\n' + '\n'.join(v)

    def test_crypto_does_not_import_core(self):
        v = self._check_layer(LAYERS['crypto'], ('sgit_ai.core.',))
        assert v == [], 'crypto must not import core:\n' + '\n'.join(v)

    def test_crypto_does_not_import_cli(self):
        v = self._check_layer(LAYERS['crypto'], ('sgit_ai.cli.',))
        assert v == [], 'crypto must not import cli:\n' + '\n'.join(v)

    # --- storage layer ---

    def test_storage_does_not_import_sync_or_objects(self):
        v = self._check_layer(LAYERS['storage'], ('sgit_ai.sync.', 'sgit_ai.objects.'))
        assert v == [], 'storage must not import sync/objects:\n' + '\n'.join(v)

    def test_storage_does_not_import_network(self):
        v = self._check_layer(LAYERS['storage'], ('sgit_ai.network.',))
        assert v == [], 'storage must not import network:\n' + '\n'.join(v)

    def test_storage_does_not_import_core(self):
        v = self._check_layer(LAYERS['storage'], ('sgit_ai.core.',))
        assert v == [], 'storage must not import core:\n' + '\n'.join(v)

    def test_storage_does_not_import_cli(self):
        v = self._check_layer(LAYERS['storage'], ('sgit_ai.cli.',))
        assert v == [], 'storage must not import cli:\n' + '\n'.join(v)

    def test_storage_allowed_imports(self):
        allowed = ('sgit_ai.crypto.', 'sgit_ai.safe_types.',
                   'sgit_ai.schemas.', 'sgit_ai.storage.')
        violations = []
        for path in self._collect_py_files(LAYERS['storage']):
            for imp in self._sgit_ai_imports(path):
                if not any(imp.startswith(p) for p in allowed):
                    key = self._violation_key(path, imp)
                    if key not in KNOWN_VIOLATIONS:
                        violations.append(key)
        assert violations == [], (
            'storage may only import from crypto/safe_types/schemas/storage:\n'
            + '\n'.join(violations)
        )

    # --- network layer ---

    def test_network_does_not_import_storage(self):
        v = self._check_layer(LAYERS['network'], ('sgit_ai.storage.',))
        assert v == [], 'network must not import storage:\n' + '\n'.join(v)

    def test_network_does_not_import_core(self):
        v = self._check_layer(LAYERS['network'], ('sgit_ai.core.',))
        assert v == [], 'network must not import core:\n' + '\n'.join(v)

    def test_network_does_not_import_cli(self):
        v = self._check_layer(LAYERS['network'], ('sgit_ai.cli.',))
        assert v == [], 'network must not import cli:\n' + '\n'.join(v)

    def test_network_allowed_imports(self):
        allowed = ('sgit_ai.crypto.', 'sgit_ai.safe_types.',
                   'sgit_ai.schemas.', 'sgit_ai.network.')
        violations = []
        for path in self._collect_py_files(LAYERS['network']):
            for imp in self._sgit_ai_imports(path):
                if not any(imp.startswith(p) for p in allowed):
                    key = self._violation_key(path, imp)
                    if key not in KNOWN_VIOLATIONS:
                        violations.append(key)
        assert violations == [], (
            'network may only import from crypto/safe_types/schemas/network:\n'
            + '\n'.join(violations)
        )

    # --- core layer ---

    def test_core_does_not_import_cli(self):
        v = self._check_layer(LAYERS['core'], ('sgit_ai.cli.',))
        assert v == [], 'core must not import cli:\n' + '\n'.join(v)

    def test_core_allowed_imports(self):
        allowed = ('sgit_ai.crypto.', 'sgit_ai.storage.', 'sgit_ai.network.',
                   'sgit_ai.workflow.', 'sgit_ai.safe_types.', 'sgit_ai.schemas.',
                   'sgit_ai.secrets.', 'sgit_ai.core.')
        violations = []
        for path in self._collect_py_files(LAYERS['core']):
            for imp in self._sgit_ai_imports(path):
                if not any(imp.startswith(p) for p in allowed):
                    key = self._violation_key(path, imp)
                    if key not in KNOWN_VIOLATIONS:
                        violations.append(key)
        assert violations == [], (
            'core may only import crypto/storage/network/workflow/safe_types/schemas/secrets/core:\n'
            + '\n'.join(violations)
        )

    # --- known violations guard ---

    def test_known_violations_are_still_present(self):
        """Guard: if a known violation is fixed, remove it from KNOWN_VIOLATIONS."""
        found = set()
        all_files = []
        for layer_dir in LAYERS.values():
            all_files.extend(self._collect_py_files(layer_dir))
        for path in all_files:
            for imp in self._sgit_ai_imports(path):
                key = self._violation_key(path, imp)
                if key in KNOWN_VIOLATIONS:
                    found.add(key)
        gone = KNOWN_VIOLATIONS - found
        assert gone == set(), (
            'Known violation(s) no longer present — remove from KNOWN_VIOLATIONS:\n'
            + '\n'.join(gone)
        )

    # --- no circular imports between adjacent layers ---

    def test_no_storage_crypto_circular(self):
        crypto_imports_storage = any(
            imp.startswith('sgit_ai.storage.')
            for p in self._collect_py_files(LAYERS['crypto'])
            for imp in self._sgit_ai_imports(p)
        )
        storage_imports_crypto = any(
            imp.startswith('sgit_ai.crypto.')
            for p in self._collect_py_files(LAYERS['storage'])
            for imp in self._sgit_ai_imports(p)
        )
        assert not (crypto_imports_storage and storage_imports_crypto)

    def test_no_network_storage_circular(self):
        network_imports_storage = any(
            imp.startswith('sgit_ai.storage.')
            for p in self._collect_py_files(LAYERS['network'])
            for imp in self._sgit_ai_imports(p)
        )
        storage_imports_network = any(
            imp.startswith('sgit_ai.network.')
            for p in self._collect_py_files(LAYERS['storage'])
            for imp in self._sgit_ai_imports(p)
        )
        assert not (network_imports_storage and storage_imports_network)
