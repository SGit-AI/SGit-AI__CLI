# 04 — Invariants & Tests

Five dimensions (target × payload × key location × reader × app) produce **240
combinations**, which is not a test plan. Separating what must *always* hold from what
genuinely *varies* collapses it to **5 assertions + 14 cells**.

---

## 1. The five invariants — asserted in every cell, not tested as cases

Home: `tests/qa/test_QA__Scenario_4__Publishing_Matrix.py`, via a shared harness so every
cell gets them for free.

| # | Invariant | How it is asserted |
|---|---|---|
| **I1** | Published ciphertext is byte-identical regardless of destination | publish to folder / zip / "bucket" / repo dir; `sha256` each ciphertext subtree; assert all equal |
| **I2** | The server never receives the key | the static transport records every request URL; assert no path or query contains the read key, any 64-hex string, or `sgit_private_` |
| **I3** | A keyless client can take custody | `mirror` with **no key material in scope**; assert byte-equality with the source and that no key file is written |
| **I4** | The loader is byte-identical everywhere | publish N different vaults; assert `sha256(index.html)` identical across all, and equal to the bundled template |
| **I5** | Plaintext only where the key is published | for every visibility × plaintext combination, assert `--with-plaintext` without `--visibility public` **exits non-zero and writes nothing** |

**I2's implementation note:** assert on the *recorded requests*, not on the source code.
Asserting "the code doesn't do X" restates intent; asserting "no request contained X" is a
check. Same rule as the cache layer's positive-outcome lesson — prove the behaviour, don't
prove the absence of a line.

**I3 is why `manifest.json` is mandatory.** Every filename is `HMAC(read_key, …)` or a
content hash learned by decrypting a tree, so without a manifest (or a host listing) a
keyless client cannot name one file. See `06__decisions-and-evidence.md`.

---

## 2. The fourteen cells

Baseline: pages host · ciphertext only · key in the published folder · browser reader ·
vault app present.

| # | What varies | Where | Note |
|---|---|---|---|
| 1 | baseline | `…Publishing_Matrix.py::Test_Baseline` | the common case, end to end |
| 2 | target: local folder | `::Test_Local_Folder_Requires_Serve` | assert the `file://` guidance is printed **and** that `serve` makes it work |
| 3 | target: zip archive | `::Test_Zip_Target` | unpack → serve; depends on the same fix as cell 2 |
| 4 | target: object storage | `::Test_Object_Storage` | dumb HTTP host stands in; asserts I1 |
| 5 | target: repo → pages | `tests/integration/…::Test_Pages_Round_Trip` | real HTTP; the round trip |
| 6 | payload + plaintext | `::Test_Plaintext_Payload` | renders, and the I5 refusal holds |
| 7 | key absent, fragment | Web + `::Test_Key_Classification_Parity` | CLI-side parity on `classify_key` |
| 8 | key absent, stored | Web | returning visitor |
| 9 | key absent, nothing | `::Test_Cover_Only` | cover renders; the ask is clear |
| 10 | key on another origin | `tests/integration/…::Test_Cross_Origin_Key` | **supported** — assert the ACAO header at run time so a platform change fails loudly |
| 11 | reader: bare clone, no key | `::Test_Custody_Without_Access` | = I3, plus the no-manifest failure message |
| 12 | reader: clone then expand | `::Test_Clone_Then_Expand` | the normal developer path |
| 13 | no vault app | `::Test_Generic_Browsing` | generic browsing |
| 14 | **fork** | `::Test_Fork_Round_Trip` | **the acceptance test** |

### Cells that were re-scoped by measurement

- **Cell 10** was expected to be unavailable; GitHub Pages sends
  `access-control-allow-origin: *` by default, so it is **supported**. The test asserts the
  header at run time rather than assuming it, so if the platform ever changes, the suite
  says so instead of the feature quietly breaking.
- **Cell 11** cannot be `sgit clone` with no key — that is structurally impossible. It is
  `sgit vault mirror` against a manifest. The *failure* path (no manifest, no listing) is
  part of the test.

### Cell 14 is the acceptance test

Clone from a published target → expand with the published key → rekey → publish to a
different target → read it back. It touches every dimension, so **if it passes, the matrix
has been exercised in combination**. It will also fail for reasons in any of the parts,
which is exactly why cells 1–13 must exist first: they are the diagnosis.

---

## 3. Build order for the suite

1. **The five invariants** as automated assertions — most risk covered per line.
2. **The baseline** (cell 1), end to end.
3. **`serve`** — unblocks cells 2 and 3.
4. **The key-location cells** (7–10), where the variation is genuinely interesting.
5. **Custody** (11) — a capability deserves a named test.
6. **Fork** (14) — the acceptance test.
7. **The remainder** — mostly confirmations that a different destination changes nothing.

## 4. Fixtures and infrastructure

- **No live server.** Use `Vault__API__In_Memory`, a stdlib `ThreadingHTTPServer` over a
  published folder, or the local SG/Send test server (`tests/integration/conftest.py`,
  `SEND__STORAGE_MODE=memory`).
- **Integration cells (5, 10)** need the Python 3.12 venv — see `CLAUDE.md`.
- **Request recording** for I2 belongs in the static transport behind a flag, so QA can
  assert on it without monkey-patching.
- Follow the repo rule: **no `__init__.py` anywhere under `tests/`**.
