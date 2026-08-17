"""Self-identifying key prefixes (design contract 08/14).

The invariants under test are the compatibility rules the design commits to:
the value after the prefix is byte-identical to the legacy key (so old
versions work by stripping it), every input point accepts both forms, and the
derived key material is IDENTICAL for both forms.
"""
import os
import shutil
import tempfile

import pytest

from sgit_ai.crypto.Vault__Crypto import (Vault__Crypto, VAULT_KEY_PREFIX,
                                          READ_KEY_PREFIX, READ_KEY_PUBLIC_PREFIX)
from sgit_ai.safe_types.Enum__Key_Kind import Enum__Key_Kind


class Test_Prefix_Helpers:

    def setup_method(self):
        self.crypto = Vault__Crypto()

    def test_prefix_constants(self):
        assert VAULT_KEY_PREFIX       == 'sgit_private_vault_'
        assert READ_KEY_PREFIX        == 'sgit_private_read_'
        assert READ_KEY_PUBLIC_PREFIX == 'sgit_public_read_'

    def test_one_scanner_rule_covers_every_private_credential(self):
        # the property the semantic naming exists for: a single anchored rule
        # alerts on all private key types (and any future one) and never on public
        import re
        rule = re.compile(r'\bsgit_private_\S+')
        assert rule.search(VAULT_KEY_PREFIX + 'p:abcd1234')
        assert rule.search(READ_KEY_PREFIX  + 'ab' * 32)
        assert not rule.search(READ_KEY_PUBLIC_PREFIX + 'ab' * 32)

    def test_strip_vault_key_prefix(self):
        assert self.crypto.strip_key_prefix('sgit_private_vault_pass:abcd1234') == 'pass:abcd1234'

    def test_strip_read_key_prefix(self):
        assert self.crypto.strip_key_prefix('sgit_private_read_' + 'ab' * 32) == 'ab' * 32

    def test_strip_is_noop_on_bare_keys(self):
        assert self.crypto.strip_key_prefix('pass:abcd1234') == 'pass:abcd1234'

    def test_format_vault_key_is_idempotent(self):
        once  = self.crypto.format_vault_key('pass:abcd1234')
        twice = self.crypto.format_vault_key(once)
        assert once == twice == 'sgit_private_vault_pass:abcd1234'

    def test_format_read_key_is_idempotent(self):
        hex64 = 'ab' * 32
        once  = self.crypto.format_read_key(hex64)
        assert once == f'sgit_private_read_{hex64}'
        assert self.crypto.format_read_key(once) == once

    def test_round_trip_strip_format(self):
        for key in ('pass:abcd1234', 'p:with:colons:abcd1234'):
            assert self.crypto.strip_key_prefix(self.crypto.format_vault_key(key)) == key


class Test_Prefixed_Keys_Derive_Identically:
    """The property everything rests on: prefix changes NOTHING cryptographic."""

    def setup_method(self):
        self.crypto = Vault__Crypto()

    def test_parse_vault_key_accepts_both(self):
        bare     = self.crypto.parse_vault_key('mypassphrase:abcd1234')
        prefixed = self.crypto.parse_vault_key('sgit_private_vault_mypassphrase:abcd1234')
        assert bare == prefixed == ('mypassphrase', 'abcd1234')

    def test_derived_keys_identical_for_both_forms(self):
        bare     = self.crypto.derive_keys_from_vault_key('mypassphrase:abcd1234')
        prefixed = self.crypto.derive_keys_from_vault_key('sgit_private_vault_mypassphrase:abcd1234')
        assert bare == prefixed

    def test_import_read_key_accepts_both(self):
        hex64    = 'ab' * 32
        bare     = self.crypto.import_read_key(hex64, 'abcd1234')
        prefixed = self.crypto.import_read_key(f'sgit_private_read_{hex64}', 'abcd1234')
        assert bare == prefixed
        assert bare['read_key'] == hex64                 # internal canonical form is BARE

    def test_passphrase_containing_colons_still_works_prefixed(self):
        p, vid = self.crypto.parse_vault_key('sgit_private_vault_a:b:c:abcd1234')
        assert (p, vid) == ('a:b:c', 'abcd1234')

    def test_invalid_key_still_rejected(self):
        with pytest.raises(ValueError):
            self.crypto.parse_vault_key('sgit_private_vault_no-vault-id-here')


class Test_New_Vaults_Are_Prefixed:
    """init/clone store and report the prefixed form; everything consumes it."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_init_returns_and_stores_prefixed_key(self):
        from sgit_ai.core.Vault__Sync       import Vault__Sync
        from sgit_ai.storage.Vault__Storage import Vault__Storage
        vault  = os.path.join(self.tmp, 'vault')
        result = Vault__Sync(crypto=Vault__Crypto()).init(vault)

        assert result['vault_key'].startswith(VAULT_KEY_PREFIX)
        with open(Vault__Storage().vault_key_path(vault)) as f:
            assert f.read().startswith(VAULT_KEY_PREFIX)
        # and the returned key round-trips through derivation
        keys = Vault__Crypto().derive_keys_from_vault_key(result['vault_key'])
        assert keys['vault_id'] == result['vault_id']

    def test_init_with_explicit_bare_key_stores_prefixed_same_material(self):
        from sgit_ai.core.Vault__Sync import Vault__Sync
        vault  = os.path.join(self.tmp, 'vault')
        result = Vault__Sync(crypto=Vault__Crypto()).init(vault, vault_key='mypassphrase:abcd1234')
        assert result['vault_key'] == 'sgit_private_vault_mypassphrase:abcd1234'
        assert result['vault_id']  == 'abcd1234'

    def test_init_accepts_an_already_prefixed_key(self):
        from sgit_ai.core.Vault__Sync import Vault__Sync
        vault  = os.path.join(self.tmp, 'vault')
        result = Vault__Sync(crypto=Vault__Crypto()).init(
            vault, vault_key='sgit_private_vault_mypassphrase:abcd1234')
        assert result['vault_key'] == 'sgit_private_vault_mypassphrase:abcd1234'   # no double prefix


class Test_Prefixed_Keys_End_To_End:
    """Full workflows driven with the prefixed forms only."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_clone_with_prefixed_vault_key(self):
        from sgit_ai.core.Vault__Sync                  import Vault__Sync
        from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory
        api    = Vault__API__In_Memory().setup()
        sync   = Vault__Sync(crypto=Vault__Crypto(), api=api)
        origin = os.path.join(self.tmp, 'origin')
        result = sync.init(origin)

        with open(os.path.join(origin, 'a.txt'), 'w') as f:
            f.write('hello')
        sync.commit(origin, 'initial')
        sync.push(origin)

        clone_dir = os.path.join(self.tmp, 'clone')
        sync.clone(result['vault_key'], clone_dir)       # the PREFIXED key from init
        with open(os.path.join(clone_dir, 'a.txt')) as f:
            assert f.read() == 'hello'
        # the clone's stored VAULT-KEY is prefixed too
        from sgit_ai.storage.Vault__Storage import Vault__Storage
        with open(Vault__Storage().vault_key_path(clone_dir)) as f:
            assert f.read().startswith(VAULT_KEY_PREFIX)

    def test_read_only_clone_with_prefixed_read_key(self):
        from sgit_ai.core.Vault__Sync                  import Vault__Sync
        from sgit_ai.network.api.Vault__API__In_Memory import Vault__API__In_Memory
        api    = Vault__API__In_Memory().setup()
        crypto = Vault__Crypto()
        sync   = Vault__Sync(crypto=crypto, api=api)
        origin = os.path.join(self.tmp, 'origin')
        result = sync.init(origin)
        with open(os.path.join(origin, 'a.txt'), 'w') as f:
            f.write('hello')
        sync.commit(origin, 'initial')
        sync.push(origin)

        keys      = crypto.derive_keys_from_vault_key(result['vault_key'])
        prefixed  = crypto.format_read_key(keys['read_key'])
        clone_dir = os.path.join(self.tmp, 'ro_clone')
        sync.clone_read_only(keys['vault_id'], crypto.strip_key_prefix(prefixed), clone_dir)
        with open(os.path.join(clone_dir, 'a.txt')) as f:
            assert f.read() == 'hello'


class Test_Derive_Keys_Command_Is_Wired:
    """`sgit vault derive-keys` existed as a method but was never registered on
    the parser (found while verifying read-key clone support, 08/14). It is a
    pure function of its argument, so it must also work OUTSIDE a vault."""

    def test_derive_keys_runs_outside_a_vault(self, capsys, monkeypatch):
        import sys
        from sgit_ai.cli.CLI__Main import CLI__Main
        tmp = tempfile.mkdtemp()
        try:
            monkeypatch.chdir(tmp)                       # definitely not a vault
            monkeypatch.setattr(sys, 'argv',
                                ['sgit', 'vault', 'derive-keys',
                                 'sgit_private_vault_mypassphrase:abcd1234'])
            CLI__Main().run()
            out = capsys.readouterr().out
            assert 'vault_id:              abcd1234' in out
            assert 'read_key:' in out and 'write_key:' in out
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_derive_keys_accepts_prefixed_read_key_form(self, capsys, monkeypatch):
        import sys
        from sgit_ai.cli.CLI__Main import CLI__Main
        tmp = tempfile.mkdtemp()
        try:
            monkeypatch.chdir(tmp)
            monkeypatch.setattr(sys, 'argv',
                                ['sgit', 'vault', 'derive-keys',
                                 'sgit_private_read_' + 'ab' * 32 + ':abcd1234'])
            CLI__Main().run()
            out = capsys.readouterr().out
            assert 'read_key:              ' + 'ab' * 32 in out
            assert 'not derivable' in out               # read-key-only note
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Test_Clone_Credential_Routing:
    """Explicit prefixes beat the 64-hex heuristic (08/15 vault-team review).
    This ordering is the contract the web mirrors — pinned here."""

    def _resolve(self, raw, read_key=None):
        from sgit_ai.cli.CLI__Vault import CLI__Vault
        from sgit_ai.cli.CLI__Token_Store import CLI__Token_Store
        return CLI__Vault(token_store=CLI__Token_Store())._resolve_clone_credential(raw, read_key)

    def test_bare_64hex_head_detected_as_read_key(self):
        hex64 = 'ab' * 32
        vk, rk, detected = self._resolve(f'{hex64}:abcd1234')
        assert (vk, rk, detected) == ('abcd1234', hex64, True)

    def test_private_read_prefixed_shorthand_detected(self):
        hex64 = 'ab' * 32
        vk, rk, detected = self._resolve(f'sgit_private_read_{hex64}:abcd1234')
        assert (vk, rk, detected) == ('abcd1234', hex64, True)

    def test_vault_prefix_suppresses_the_heuristic(self):
        # a genuine vault key whose passphrase HAPPENS to be 64-hex: the explicit
        # sgit_private_vault_ prefix declares the type, so it must NOT route read-only
        hex64 = 'ab' * 32
        vk, rk, detected = self._resolve(f'sgit_private_vault_{hex64}:abcd1234')
        assert (vk, rk, detected) == (f'{hex64}:abcd1234', None, False)

    def test_read_prefix_without_vault_id_is_a_clear_error(self):
        # never silently retried as a passphrase
        with pytest.raises(ValueError, match='vault id'):
            self._resolve('sgit_private_read_' + 'ab' * 32)

    def test_read_key_flag_is_prefix_stripped(self):
        hex64 = 'ab' * 32
        vk, rk, detected = self._resolve('abcd1234', read_key=f'sgit_private_read_{hex64}')
        assert (vk, rk, detected) == ('abcd1234', hex64, False)

    def test_ordinary_vault_key_untouched(self):
        vk, rk, detected = self._resolve('mypassphrase:abcd1234')
        assert (vk, rk, detected) == ('mypassphrase:abcd1234', None, False)


class Test_Key_Classification:
    """Classification is by DECLARATION, never by shape — the primitive a
    loader page mirrors to refuse write capability it never needed."""

    def setup_method(self):
        self.crypto = Vault__Crypto()
        self.hex64  = 'ab' * 32

    def test_vault_key(self):
        assert self.crypto.classify_key(f'sgit_private_vault_p:abcd1234') == Enum__Key_Kind.VAULT

    def test_private_read_key(self):
        assert self.crypto.classify_key(f'sgit_private_read_{self.hex64}') == Enum__Key_Kind.READ_PRIVATE

    def test_public_read_key(self):
        assert self.crypto.classify_key(f'sgit_public_read_{self.hex64}') == Enum__Key_Kind.READ_PUBLIC

    def test_bare_key_is_unknown(self):
        assert self.crypto.classify_key(self.hex64)        == Enum__Key_Kind.UNKNOWN
        assert self.crypto.classify_key('pass:abcd1234')   == Enum__Key_Kind.UNKNOWN

    def test_public_and_private_read_keys_are_the_same_material(self):
        priv = self.crypto.import_read_key(f'sgit_private_read_{self.hex64}', 'abcd1234')
        pub  = self.crypto.import_read_key(f'sgit_public_read_{self.hex64}',  'abcd1234')
        assert priv == pub                                  # identical capability
        assert priv['read_key'] == self.hex64               # only the DECLARATION differs


class Test_Public_Read_Key_Formatting:

    def setup_method(self):
        self.crypto = Vault__Crypto()
        self.hex64  = 'cd' * 32

    def test_public_flag_selects_the_public_prefix(self):
        assert self.crypto.format_read_key(self.hex64, public=True)  == f'sgit_public_read_{self.hex64}'
        assert self.crypto.format_read_key(self.hex64, public=False) == f'sgit_private_read_{self.hex64}'

    def test_default_is_private(self):
        assert self.crypto.format_read_key(self.hex64).startswith('sgit_private_read_')

    def test_reformatting_can_flip_the_declaration(self):
        # publishing takes a private key and re-declares it; bytes unchanged
        private = self.crypto.format_read_key(self.hex64)
        public  = self.crypto.format_read_key(private, public=True)
        assert public == f'sgit_public_read_{self.hex64}'
        assert self.crypto.strip_key_prefix(public) == self.crypto.strip_key_prefix(private)


class Test_Legacy_Prefixes_Still_Accepted:
    """v0.15.5 briefly shipped sgit_private_vault_/sgit_rk1_. Accepted forever, never emitted."""

    def setup_method(self):
        self.crypto = Vault__Crypto()

    def test_legacy_vault_key_parses(self):
        assert self.crypto.parse_vault_key('sgit_private_vault_mypassphrase:abcd1234') == ('mypassphrase', 'abcd1234')

    def test_legacy_read_key_imports(self):
        hex64 = 'ab' * 32
        assert self.crypto.import_read_key(f'sgit_rk1_{hex64}', 'abcd1234')['read_key'] == hex64

    def test_legacy_classifies_correctly(self):
        assert self.crypto.classify_key('sgit_private_vault_p:abcd1234')     == Enum__Key_Kind.VAULT
        assert self.crypto.classify_key('sgit_rk1_' + 'ab'*32)     == Enum__Key_Kind.READ_PRIVATE

    def test_legacy_is_upgraded_on_reformat(self):
        assert self.crypto.format_vault_key('sgit_private_vault_p:abcd1234') == 'sgit_private_vault_p:abcd1234'
        assert self.crypto.format_read_key('sgit_rk1_' + 'ab'*32)  == 'sgit_private_read_' + 'ab'*32
