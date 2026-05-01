# Finding 04 — Tests Tree `__init__.py` Check

**Author:** Villager Dev
**Date:** 2026-05-01
**Severity:** info (rule compliant)
**Owners:** —

---

## Result

**PASS.** `find tests -name __init__.py` returns zero hits.

CLAUDE.md §8 ("No `__init__.py` files in tests") is satisfied at the
end of v0.10.30. The newly added test directories
(`tests/unit/sync/test_Vault__Sync__Probe.py` etc.) all live under
existing `tests/` subtrees that have no `__init__.py`. None of the
sprint commits introduce one.

The `tests/unit/sync/vault_test_env.py` module (helper for real
in-memory vault setup) is **not** an `__init__.py` — it is a regular
helper module imported as `from tests.unit.sync.vault_test_env import
Vault__Test_Env`. Importing this works because the project uses
implicit namespace packages (Python 3.11+ default) plus pytest's
`rootdir` resolution.

## Evidence

```
$ find /home/user/SGit-AI__CLI/tests -name __init__.py
(no output)
```

## Suggested next-action

None.
