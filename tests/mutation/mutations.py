"""Mutation catalogue for SGit-AI v0.12.x.

Each entry is a dict with:
  id          — mutation identifier (M1..M10, B1..B5, W1..W2, R1)
  description — what the mutation does and why it matters
  file        — repo-relative path to the file under mutation
  old         — exact string to replace (str.replace semantics)
  new         — replacement string

The 'old' string is extracted verbatim from the source so that
str.replace(old, new) produces the mutant.

Source of truth: team/villager/appsec/v0.10.30/M00__mutation-test-matrix.md
"""

MUTATIONS = [
    # -------------------------------------------------------------------------
    # M1 — HMAC key dropped: encrypt_deterministic uses SHA-256 without key
    # Detector: test_Vault__Crypto__Deterministic cross-vault divergence tests
    # -------------------------------------------------------------------------
    {
        'id'          : 'M1',
        'description' : 'Replace hmac.new(key, plaintext, sha256) with hashlib.sha256(plaintext) '
                         'in encrypt_deterministic — drops the HMAC key so any two vaults with '
                         'the same plaintext produce the same IV (cross-vault leakage).',
        'file'        : 'sgit_ai/crypto/Vault__Crypto.py',
        'old'         : 'iv = hmac.new(key, plaintext, hashlib.sha256).digest()[:GCM_IV_BYTES]',
        'new'         : 'iv = hashlib.sha256(plaintext).digest()[:GCM_IV_BYTES]',
    },

    # -------------------------------------------------------------------------
    # M2 — HMAC key hard-coded to constant bytes
    # Detector: same cross-vault divergence tests as M1
    # -------------------------------------------------------------------------
    {
        'id'          : 'M2',
        'description' : 'Hard-code the HMAC key to a constant in encrypt_deterministic — '
                         'different vaults with the same passphrase now share IVs, '
                         'enabling cross-vault ciphertext correlation.',
        'file'        : 'sgit_ai/crypto/Vault__Crypto.py',
        'old'         : 'iv = hmac.new(key, plaintext, hashlib.sha256).digest()[:GCM_IV_BYTES]',
        'new'         : 'iv = hmac.new(b"constant-key", plaintext, hashlib.sha256).digest()[:GCM_IV_BYTES]',
    },

    # -------------------------------------------------------------------------
    # M3 — Deterministic IV replaced with random IV (breaks CAS deduplication
    #       and is caught by the determinism test suite)
    # Detector: test_iv_derivation__equals_hmac_sha256_prefix,
    #           test_determinism__same_key_same_plaintext_same_ciphertext
    # -------------------------------------------------------------------------
    {
        'id'          : 'M3',
        'description' : 'Replace iv = hmac(...) with iv = os.urandom(12) in '
                         'encrypt_deterministic — breaks CAS deduplication '
                         'and is caught by the determinism tests.',
        'file'        : 'sgit_ai/crypto/Vault__Crypto.py',
        'old'         : 'iv = hmac.new(key, plaintext, hashlib.sha256).digest()[:GCM_IV_BYTES]',
        'new'         : 'iv = os.urandom(GCM_IV_BYTES)',
    },

    # -------------------------------------------------------------------------
    # M4 — rekey_wipe skips deletion: shutil.rmtree replaced with pass
    # Detector: test_rekey_wipe_removes_objects
    # (B13: moved from sgit_ai/sync/ to sgit_ai/core/actions/lifecycle/)
    # -------------------------------------------------------------------------
    {
        'id'          : 'M4',
        'description' : 'Replace storage.secure_rmtree(sg_dir) with pass in rekey_wipe — '
                         'the vault store is not wiped, leaking key material after rekey.',
        'file'        : 'sgit_ai/core/actions/lifecycle/Vault__Sync__Lifecycle.py',
        'old'         : '            storage.secure_rmtree(sg_dir)',
        'new'         : '            pass  # M4 mutation: skip wipe',
    },

    # -------------------------------------------------------------------------
    # M5 — PBKDF2 cache disabled (maxsize=0)
    # Detector: test_pbkdf2_cache_size_bounded
    # -------------------------------------------------------------------------
    {
        'id'          : 'M5',
        'description' : 'Set @functools.lru_cache(maxsize=0) on _pbkdf2_cached — '
                         'disables the cache, causing unbounded PBKDF2 re-derivation '
                         'and DoS on repeated operations.',
        'file'        : 'sgit_ai/crypto/Vault__Crypto.py',
        'old'         : '@functools.lru_cache(maxsize=256)',
        'new'         : '@functools.lru_cache(maxsize=0)',
    },

    # -------------------------------------------------------------------------
    # M6 — read_key omitted from clone_mode.json write (headless clone path)
    # Detector: test_Vault__Sync__Multi_Clone round-trip (decrypt fails)
    # (B13: moved from sgit_ai/sync/ to sgit_ai/core/actions/clone/)
    # -------------------------------------------------------------------------
    {
        'id'          : 'M6',
        'description' : 'Omit read_key from Schema__Clone_Mode constructor in clone path — '
                         'clone_mode.json is written without the read_key, so subsequent '
                         'operations on the read-only clone cannot decrypt any blob.',
        'file'        : 'sgit_ai/core/actions/clone/Vault__Sync__Clone.py',
        'old'         : '            clone_mode      = Schema__Clone_Mode(mode=Enum__Clone_Mode.READ_ONLY,\n'
                         '                                                 vault_id=vault_id, read_key=read_key_hex)',
        'new'         : '            clone_mode      = Schema__Clone_Mode(mode=Enum__Clone_Mode.READ_ONLY,\n'
                         '                                                 vault_id=vault_id)',
    },

    # -------------------------------------------------------------------------
    # M7 — write_file skips encryption (identity function instead of encrypt)
    # Detector: test_write_file_blob_is_not_plaintext (brief 21)
    # (B13: moved from sgit_ai/sync/ to sgit_ai/storage/)
    # -------------------------------------------------------------------------
    {
        'id'          : 'M7',
        'description' : 'Replace crypto.encrypt(read_key, file_content) with file_content '
                         'in write_file — blobs stored unencrypted on disk.',
        'file'        : 'sgit_ai/storage/Vault__Sub_Tree.py',
        'old'         : '        encrypted = self.crypto.encrypt(read_key, content)',
        'new'         : '        encrypted = content  # M7 mutation: skip encryption',
    },

    # -------------------------------------------------------------------------
    # M8 — extra field injected into _save_push_state
    # Detector: test_push_state_only_safe_fields__extra_field_dropped_on_load
    # (B13: moved from sgit_ai/sync/ to sgit_ai/core/actions/push/)
    # -------------------------------------------------------------------------
    {
        'id'          : 'M8',
        'description' : 'Add a paths: flat_map field to _save_push_state output — '
                         'Schema__Push_State allowlist drops injected fields on load, '
                         'so the extra field can never be read back.',
        'file'        : 'sgit_ai/core/actions/push/Vault__Sync__Push.py',
        'old'         : '        with open(path, \'w\') as f:\n'
                         '            json.dump(state.json(), f)',
        'new'         : '        with open(path, \'w\') as f:\n'
                         '            data = state.json()\n'
                         '            data[\'paths\'] = [\'injected\']\n'
                         '            json.dump(data, f)',
    },

    # -------------------------------------------------------------------------
    # M9 — probe_token writes clone_mode.json to disk
    # Detector: test_probe_writes_no_files_to_empty_temp_dir (brief 21)
    # (B13: moved from sgit_ai/sync/ to sgit_ai/core/actions/lifecycle/)
    # -------------------------------------------------------------------------
    {
        'id'          : 'M9',
        'description' : 'In probe_token success path, write clone_mode.json to CWD — '
                         'probe must be a read-only operation; disk artefacts leak vault_id.',
        'file'        : 'sgit_ai/core/actions/lifecycle/Vault__Sync__Lifecycle.py',
        'old'         : '                self.crypto.clear_kdf_cache()\n'
                         '                return dict(type=\'vault\', vault_id=vault_id, token=token_str)',
        'new'         : '                import json as _json_probe\n'
                         '                with open(\'clone_mode.json\', \'w\') as _f:\n'
                         '                    _json_probe.dump({\'vault_id\': vault_id}, _f)\n'
                         '                self.crypto.clear_kdf_cache()\n'
                         '                return dict(type=\'vault\', vault_id=vault_id, token=token_str)',
    },

    # -------------------------------------------------------------------------
    # M10 — delete_vault drops the x-sgraph-vault-write-key header
    # Detector: integration test against real server (Phase 3/sgraph-ai-app-send)
    # In-memory API ignores headers so unit tests cannot catch this.
    # (B13: moved from sgit_ai/api/ to sgit_ai/network/api/)
    # -------------------------------------------------------------------------
    {
        'id'          : 'M10',
        'description' : 'In Vault__API.delete_vault, drop the x-sgraph-vault-write-key '
                         'header — the server rejects the DELETE without the auth header, '
                         'but the in-memory API ignores headers so unit tests cannot catch this.',
        'file'        : 'sgit_ai/network/api/Vault__API.py',
        'old'         : "        body    = json.dumps({'vault_id': vault_id}).encode('utf-8')\n"
                         "        headers = {'Content-Type'             : 'application/json',\n"
                         "                   'x-sgraph-access-token'    : self.access_token,\n"
                         "                   'x-sgraph-vault-write-key' : write_key}",
        'new'         : "        body    = json.dumps({'vault_id': vault_id}).encode('utf-8')\n"
                         "        headers = {'Content-Type'             : 'application/json',\n"
                         "                   'x-sgraph-access-token'    : self.access_token}",
    },

    # =========================================================================
    # BASELINE MUTATIONS B1–B5
    # =========================================================================

    # -------------------------------------------------------------------------
    # B1 — PBKDF2 iterations reduced from 600_000 to 1_000
    # Detector: test_pbkdf2_iterations_constant
    # -------------------------------------------------------------------------
    {
        'id'          : 'B1',
        'description' : 'Set PBKDF2_ITERATIONS = 1000 — drastically weakens KDF, '
                         'enabling brute-force attacks on vault keys.',
        'file'        : 'sgit_ai/crypto/Vault__Crypto.py',
        'old'         : 'PBKDF2_ITERATIONS = 600_000',
        'new'         : 'PBKDF2_ITERATIONS = 1_000',
    },

    # -------------------------------------------------------------------------
    # B2 — AES key length reduced from 32 to 16 bytes (AES-128 instead of AES-256)
    # Detector: test_aes_key_bytes_constant
    # -------------------------------------------------------------------------
    {
        'id'          : 'B2',
        'description' : 'Set AES_KEY_BYTES = 16 — downgrades encryption from AES-256 '
                         'to AES-128, halving the key space.',
        'file'        : 'sgit_ai/crypto/Vault__Crypto.py',
        'old'         : 'AES_KEY_BYTES     = 32',
        'new'         : 'AES_KEY_BYTES     = 16',
    },

    # -------------------------------------------------------------------------
    # B3 — HKDF_INFO_PREFIX byte-string changed
    # Detector: test_hkdf_info_prefix__matches_spec
    # -------------------------------------------------------------------------
    {
        'id'          : 'B3',
        'description' : "Change HKDF_INFO_PREFIX from b'sg-send-file-key' to b'mutated-prefix' — "
                         'breaks cross-client interoperability; derived file keys no longer '
                         'match keys derived by the browser Web Crypto API.',
        'file'        : 'sgit_ai/crypto/Vault__Crypto.py',
        'old'         : "HKDF_INFO_PREFIX  = b'sg-send-file-key'",
        'new'         : "HKDF_INFO_PREFIX  = b'mutated-prefix'",
    },

    # -------------------------------------------------------------------------
    # B4 — VAULT_ID_PATTERN validation removed (accepts any string as vault_id)
    # Detector: test_parse_vault_key__invalid_empty_vault_id and related init tests
    # -------------------------------------------------------------------------
    {
        'id'          : 'B4',
        'description' : "Remove VAULT_ID_PATTERN from vault_id validation in parse_vault_key — "
                         'allows arbitrary strings (with hyphens, uppercase, spaces) as vault '
                         'IDs, leaking vault names to server logs and S3 paths.',
        'file'        : 'sgit_ai/crypto/Vault__Crypto.py',
        'old'         : '        if not VAULT_ID_PATTERN.match(vault_id):',
        'new'         : '        if False:  # B4 mutation: skip vault_id validation',
    },

    # -------------------------------------------------------------------------
    # B5 — blob encryption skipped in commit/write_file path
    # Detector: test_object_store__no_plaintext_file_contents (AppSec test)
    #           + test_write_file_blob_is_not_plaintext (M7 closer, brief 21)
    # (B13: moved from sgit_ai/sync/ to sgit_ai/storage/)
    # -------------------------------------------------------------------------
    {
        'id'          : 'B5',
        'description' : "In write_file, skip encryption so the blob is stored as raw "
                         "plaintext in the object store. This is the same mutation as M7 "
                         "approached from the baseline angle — the AppSec no-plaintext "
                         "test and the M7 closer test both catch this.",
        'file'        : 'sgit_ai/storage/Vault__Sub_Tree.py',
        'old'         : '        encrypted = self.crypto.encrypt(read_key, content)',
        'new'         : '        encrypted = content  # B5 mutation: skip encryption',
    },

    # =========================================================================
    # WORKFLOW MUTATIONS W1–W2 (added v0.12.x)
    # =========================================================================

    # -------------------------------------------------------------------------
    # W1 — Workflow runner skips is_done check (resume logic broken)
    # Detector: test_Workflow__Runner resume tests; test_Synthetic__Workflow
    # -------------------------------------------------------------------------
    {
        'id'          : 'W1',
        'description' : 'In Workflow__Runner.run(), replace `if step.is_done(ws):` with '
                         '`if False:` — the runner never resumes a partially-completed '
                         'workflow; already-finished steps re-execute, breaking idempotency '
                         'and potentially corrupting workspace state.',
        'file'        : 'sgit_ai/workflow/Workflow__Runner.py',
        'old'         : '                if step.is_done(ws):',
        'new'         : '                if False:  # W1 mutation: skip is_done check',
    },

    # -------------------------------------------------------------------------
    # W2 — Workflow workspace not cleaned up on success
    # Detector: test_Workflow__Runner__cleanup / test_Synthetic__Workflow cleanup
    # -------------------------------------------------------------------------
    {
        'id'          : 'W2',
        'description' : 'In Workflow__Runner.run(), replace `ws.cleanup()` with `pass` — '
                         'workspace temp directories are never removed on success, '
                         'leaking plaintext step outputs to disk indefinitely.',
        'file'        : 'sgit_ai/workflow/Workflow__Runner.py',
        'old'         : '            ws.cleanup()',
        'new'         : '            pass  # W2 mutation: skip workspace cleanup',
    },

    # =========================================================================
    # READ-ONLY GUARD MUTATIONS R1 (added v0.12.x)
    # =========================================================================

    # -------------------------------------------------------------------------
    # R1 — read-only clone write guard bypassed in commit path
    # Detector: test_write_file_raises_on_read_only_clone,
    #           test_Vault__Sync__Write_File__Guard (brief 21)
    # -------------------------------------------------------------------------
    {
        'id'          : 'R1',
        'description' : 'In Vault__Sync__Commit.commit(), replace `if not c.write_key:` with '
                         '`if False:` — a read-only clone can now commit, writing objects '
                         'that bypass the read-key-only enforcement.',
        'file'        : 'sgit_ai/core/actions/commit/Vault__Sync__Commit.py',
        'old'         : '        if not c.write_key:\n'
                         '            raise Vault__Read_Only_Error()',
        'new'         : '        if False:  # R1 mutation: skip read-only guard\n'
                         '            raise Vault__Read_Only_Error()',
    },
]
