# `Vault__Backend` abstract stubs — sgit_ai/network/api/Vault__Backend.py

`Vault__Backend` is an interface with a default `batch` and `exists`. **No production code constructs or references any `Vault__Backend*` class**: `grep -rln Vault__Backend sgit_ai/ tests/` finds only the three files under `network/api/` and their unit tests. The real host boundary is `Vault__API` directly (`Vault__Sync__Base.api : Vault__API`, sgit_ai/core/Vault__Sync__Base.py:L32).

## `read` (L13-L14), `write` (L16-L17), `delete` (L19-L20), `list_files` (L22-L23)
Each raises `NotImplementedError` naming the class. Tests: `tests/unit/api/test_Vault__Backend.py` L17-L35.

See `network__api__Vault__Backend__batch.md` and `network__api__Vault__Backend__exists.md` for the two methods with bodies.
