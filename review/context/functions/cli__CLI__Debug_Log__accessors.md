# `CLI__Debug_Log` small methods in sgit_ai/cli/CLI__Debug_Log.py

Fields (L8-L9): `enabled : bool` (Type_Safe default `False`), `entries : list` (per-instance `[]`). Constructed only by `CLI__Main._setup_debug` with `enabled=True` (`CLI__Main.py:L1075`); `self.vault.debug_log = debug_log` then flows into `Vault__API(debug_log=...)` (`CLI__Vault.py:L55-L60`, `Vault__API.py:L29`, `Vault__API__Auto.py:L41`).

---

## `log_response` (L23-L27)
Sets `status`, `resp_size`, `duration = monotonic - start`; prints. Callers: `Vault__API.py:L257,L419`, `Vault__Sync__Clone.py:L339,L425`, `Vault__Batch.py:L147`.

## `log_error` (L29-L33)
Sets `status`, `error` (the HTTP reason string, `Vault__API.py:L423` passes `e.reason`), duration; prints. Only `HTTPError`s reach it; `URLError`s do not (`Vault__API.py:L421-L429`).

## `_format_size` (L68-L75)
`-` for 0, then B / KB / MB. Pure. Test `::test_format_size`.

## `print_header` (L77-L85)
Banner to stderr when enabled. Called once at `CLI__Main.py:L1077`.

## `print_summary` (L87-L100)
Request count, error count, wall-clock span (max end − min start over `entries`), total bytes — stderr, when enabled and non-empty. Called at `CLI__Main.py:L893` on command end. Reads every entry's `start`/`duration`; an entry whose response never arrived keeps `duration 0.0` and so counts its start as its end.
