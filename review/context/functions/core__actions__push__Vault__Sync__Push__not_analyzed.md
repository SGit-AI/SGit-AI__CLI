# `Vault__Sync__Push` — functions not analyzed in this slice

- `_pull_file_changes` (L961-L966): presentation — reshapes the pull result's added/modified/deleted lists for the CLI. **not analyzed: presentation**.
- `_check_no_conflict_files` (L968-L990): local working-tree walk for `*.conflict` files (skips `.sg_vault` and ignored dirs); raises `Vault__Push_With_Conflicts_Error`. No host interaction, no ref/index logic. **not analyzed: local guard** (listed for completeness; called at `push` L47-L48 unless `--push-conflict`).

Also noted: the prompt's "re-encrypts from clone-branch key to named-branch key" has no counterpart in this module — the vault has one read key for every object and ref (`Vault__Crypto.derive_keys`, threat model §1); `grep -rn "re-encrypt\|reencrypt" sgit_ai/` finds only `vault move` (`Step__Move__Build_Temp_Vault`), the tree-IV migration and `rekey`, none of which push calls. Push uploads the clone's existing ciphertexts unchanged (`obj_store.load` → `write` ops) and encrypts only the new ref value (`Vault__Ref_Manager.encrypt_ref_value`) and rebuilt cache objects (`Vault__Cache_Manager.encrypt_object`).
