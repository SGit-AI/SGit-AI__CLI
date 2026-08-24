# Testing the static-publishing feature set

**Scope:** everything landed on `claude/sgit-cli-review-rxll54` — tracked-wins ignore
(P0), the static transport + verify-before-write (P1), `sgit publish` (P2/P4/P4b/P6),
`sgit vault serve` (P3), `sgit vault mirror` (P5), `sgit vault attach` (P9), and the
publishing-matrix QA suite (P7).

Two halves: §1–2 run the automated suites and map what covers what; §3 is a manual
smoke-test walkthrough you can run end-to-end in a scratch directory with nothing but
the CLI and Python's stdlib. §4 lists what still needs a real-world (GitHub Pages) run.

> **Updated 2026-08-24** for the behaviour that changed after the two architecture
> review passes: verification is now **strict** everywhere (the "but it decrypts under
> my key" fallback is gone), `sgit vault move` **rewrites object ids**, a refused
> object that is *required* raises a typed integrity error, and `sgit publish` refuses
> an unverifiable store. New drills for all four are in **§3.10–3.12**; the older
> drills below are unchanged and still correct.

**Current suite baseline:** 3815 unit passed · 122 passed / 20 skipped qa.

---

## 1. Automated suites

```bash
pip install -e ".[dev]"

# everything unit-level (~2 min with xdist)
pytest tests/unit/ -n auto              # expected: 3796 passed

# the QA scenarios, including the publishing matrix
pytest tests/qa -q                      # expected: 121 passed, 20 skipped
# (note: `-m qa` selects only a subset — use the path form for the full run)

# just the publishing matrix (invariants I1–I7 + matrix cells)
pytest tests/qa/test_QA__Scenario_4__Publishing_Matrix.py -s -v
```

Integration tests (real in-memory SG/Send server) need the Python 3.12 venv — see
`CLAUDE.md` → *Integration Testing*.

## 2. What covers what

| Feature | Test file(s) | The assertions that matter |
|---|---|---|
| Tracked-wins + `.github` ignored | `tests/unit/sync/test_Vault__Ignore.py`, `test_Vault__Ignore__Tracked_Wins.py` | a vault whose head tracks `.github/workflows/x.yml` is still clean after upgrade; push says nothing to push; fresh vaults never add `.github/**`; the one-time migration notice; `--apply` removes in one commit, work tree untouched |
| Static transport | `tests/unit/network/api/test_Vault__API__Static.py` | real clones from a folder + stdlib HTTP server in both layouts; >4 MB presigned path; writes raise; **dead host raises naming the host, never "no named ref"** (F5); recorded requests carry no key material (I2) |
| SP-1 verify-before-write | same file + `test_Clone__Workspace.py` | a served `obj-cas-imm-*` with wrong bytes is refused **before** the write and the clone still completes |
| `sgit publish` | `tests/unit/core/actions/publish/test_Vault__Publish.py` | surface-only output, O(KB) whatever the vault weighs, loader == bundled template even when the vault has its own `index.html` (I4), manifest enumerates the store byte-for-byte, deterministic double-publish, publish from a read-only clone |
| Visibility (P4) | same file + `tests/unit/cli/test_CLI__Publish_And_Serve.py` | public confirmation + irreversibility text, downgrade warning blocks without `--yes`, per-clone recording, `sgit_private_*` never a filename |
| `sgit vault serve` | `tests/unit/core/serve/test_Vault__Static_Server.py` | virtual `bare/` route byte-identical (I1), traversal + encoded variants refused (SP-8), Host-header check (SP-9), 405 on writes, no directory listing, `--port 0` |
| API docs (P4b) | `test_Vault__Publish__Api_Docs.py`, `tests/unit/network/assets/test_Swagger_UI__Assets.py` | `servers: ["."]`, GET-only paths, real file-id examples, the five CDN attributes each asserted, no floating tag, SRI fail-closed + corrupted-cache refetch |
| Bundles (P6) | `test_Vault__Publish__Bundles.py` | `ZIP_STORED` only, delta union == `bare/data`, corrupt bundle degrades per object, deterministic |
| `sgit vault mirror` (P5) | `tests/unit/core/actions/mirror/test_Vault__Mirror.py` | byte-identical keyless copy, **rewritten object + rewritten manifest hash still never "verified"** (SP-3), traversal file_id refused, over-count and conflicting-duplicate manifests rejected (SP-8), honest no-listing failure |
| `sgit vault attach` (P9) | `tests/unit/core/actions/lifecycle/test_Vault__Attach.py` | wrong key → `Nothing written.`, mode-exclusive both directions, `Schema__Clone_Mode`-exact, status/publish/serve work afterwards |
| The whole matrix | `tests/qa/test_QA__Scenario_4__Publishing_Matrix.py` | I1–I7 end-to-end + cells 1–4, 7, 9, 11, 13 and the **cell-14 fork round-trip** (the acceptance test) |
| Repo-side key guard | same QA file | canonical gitignore asserted literally; keyed backup + `git add -A` stages nothing under `.sg_vault/backups/` |

## 3. Manual smoke-test walkthrough

Everything below runs in a scratch dir against the default remote or `--base-url` of
your choice; steps marked *(local-only)* never touch a server. `sgit` here means
`python -m sgit_ai` or the installed console script from this branch.

### 3.1 Publish, inspect, serve

```bash
mkdir /tmp/demo && cd /tmp/demo
sgit init .                             # or clone an existing vault
echo "# handbook" > handbook.md
sgit commit -m "initial" && sgit push

sgit publish                            # bare (the safe default)
find .sg_vault/publish -type f          # expect ONLY: index.html cover.json manifest.json
python -m json.tool .sg_vault/publish/manifest.json | head -40
```

Check: `objects[]` lists every file under `.sg_vault/bare/**` with `size` and `sha256`;
`commits` is head-first; `plaintext_surface` hashes each emitted file; there is **no
ciphertext** in the folder and no key file at `bare`.

```bash
sgit publish                            # again — determinism
# (hash the folder before/after: identical)

sgit vault serve --port 8420 &          # auto-republishes if the store moved on
curl -s http://127.0.0.1:8420/ | head -3                       # the loader
curl -s http://127.0.0.1:8420/manifest.json | head -5
# the virtual composed route — served straight from .sg_vault/bare/, no copies:
VID=$(python -c "import json;print(json.load(open('.sg_vault/publish/manifest.json'))['vault_id'])")
FID=$(python -c "import json;print(json.load(open('.sg_vault/publish/manifest.json'))['objects'][0]['file_id'])")
curl -s "http://127.0.0.1:8420/api/vault/read/$VID/$FID" | cmp - ".sg_vault/$FID" && echo "I1 OK"
```

Negative checks against the same server:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8420/cover.json   # 405
curl -s -o /dev/null -w "%{http_code}\n" --path-as-is \
     "http://127.0.0.1:8420/../../etc/passwd"                                        # 403/404
curl -s -o /dev/null -w "%{http_code}\n" -H "Host: evil.example.com" \
     http://127.0.0.1:8420/                                                          # 403 (SP-9)
kill %1
```

### 3.2 Public visibility and the downgrade warning

```bash
sgit publish --visibility public        # read the prompt — answer y
ls .sg_vault/publish/sgit_public_read_* # the key file, name IS the key
# now simulate the CI fresh-clone case: clear the stored per-clone choice
python - <<'EOF'
import json; p='.sg_vault/local/config.json'; c=json.load(open(p))
c['publish_visibility']=None; json.dump(c, open(p,'w'))
EOF
sgit publish                            # expect: refuses with the PUBLIC-downgrade warning
sgit publish --visibility public --yes  # explicit keeps it public
```

### 3.3 Static clone — folder, dumb HTTP host, both layouts *(local-only)*

```bash
# compose a served root the deployment way: surface + store, keyless copy
mkdir /tmp/site && cp -r .sg_vault/publish/* /tmp/site/ && cp -r .sg_vault/bare /tmp/site/bare

# from a plain folder:
sgit clone <vault-key> /tmp/clone-folder --base-url /tmp/site --transport auto
# output shows: Transport: local (folder, read-only)

# from a dumb HTTP server (auto flips to static on the missing batch endpoint, and says so):
python -m http.server 9000 -d /tmp/site &
sgit clone <vault-key> /tmp/clone-http --base-url http://127.0.0.1:9000
cat /tmp/clone-http/handbook.md
sgit vault info /tmp/clone-http         # Transport line under Remote:
kill %1
```

Also worth seeing once: point `--base-url` at a **closed port** and confirm the error
names the host and says *transport failure* — never "no branch index and no named ref"
(F5). And clone with a `sgit_private_read_*` key over plain `http://` to see the SP-6
warning; `sgit_public_read_` stays silent.

### 3.4 Verify-before-write, by sabotage *(local-only)*

```bash
cp -r /tmp/site /tmp/site-hostile
B=$(ls /tmp/site-hostile/bare/data | head -1)
echo "tampered" > "/tmp/site-hostile/bare/data/$B"
sgit clone <vault-key> /tmp/clone-hostile --base-url /tmp/site-hostile
# expect: a per-object warning, the clone COMPLETES, and the tampered object
# is absent from /tmp/clone-hostile/.sg_vault/bare/data/ (refused before the write)
```

### 3.5 Mirror — custody without access *(local-only)*

```bash
sgit vault mirror /tmp/site /tmp/mirror            # no key anywhere in scope
diff -r /tmp/site/bare /tmp/mirror/bare && echo "byte-identical"
ls /tmp/mirror | grep sgit_ || echo "no key file written"
sgit vault mirror --verify /tmp/mirror             # offline re-check
# sabotage drill: rewrite an object AND its manifest sha256 in a copy of the site;
# mirror again — the object must be reported host-attested/refused, never verified (SP-3)
```

### 3.6 Attach — the fresh-git-clone shape

```bash
# simulate what a git clone of a one-repo vault gives you: work tree + bare/, no local/
mkdir /tmp/checkout && cp handbook.md /tmp/checkout/
mkdir -p /tmp/checkout/.sg_vault && cp -r .sg_vault/bare /tmp/checkout/.sg_vault/bare

sgit vault attach /tmp/checkout --vault-key <wrong-key>:<vault-id>
# expect: "derived ref … not found in bare/refs — wrong key for this store. Nothing written."
sgit vault attach /tmp/checkout --read-key <read-key> --vault-id <vault-id>
# expect: "attached (read-only): …  ref … verified in bare/refs"
cd /tmp/checkout && sgit status && sgit publish && cd -
```

### 3.7 Ignore engine — tracked-wins and the escape hatch

```bash
sgit vault ignore                       # the documented always-ignored list (.github in it)
mkdir -p .github/workflows && echo "on: push" > .github/workflows/ci.yml
sgit status                             # clean — never added
# for a pre-existing vault that tracks .github/** (write one in with `sgit write`):
#   first command prints the one-time migration notice; files stay in the head
sgit vault ignore --apply .github       # one visible commit; work tree untouched
```

### 3.8 Bundles and API docs

```bash
sgit publish --bundles --api-docs
ls .sg_vault/publish/bundles/           # head-<commit>.zip + one zip per commit
python -c "import zipfile;
b=zipfile.ZipFile(next(iter(__import__('glob').glob('.sg_vault/publish/bundles/head-*.zip'))));
assert all(i.compress_type==zipfile.ZIP_STORED for i in b.infolist()); print('ZIP_STORED OK')"
grep -o 'integrity="sha384-[^"]*"' .sg_vault/publish/api/docs/index.html   # two pins
grep 'Content-Security-Policy' .sg_vault/publish/api/docs/index.html       # mandatory CSP
sgit vault serve --open                 # docs at /api/docs/, spec at /api/openapi.json
```

`--api-docs=bundled` needs network once (fetch-verify-cache into
`~/.sgit/assets/swagger-ui/<version>/`); corrupt a cached file and re-run to watch it
refetch rather than serve bad bytes.

### 3.9 The one-repo pattern end-to-end (the real thing)

1. `git init` next to the vault; make sure `.gitignore` has the canonical three lines
   (`.sg_vault/local/`, `.sg_vault/backups/`, `.sg_vault_new/`) — `sgit vault backup`
   warns if `backups/` is missing.
2. `sgit publish --visibility public --yes`, commit **work tree + `.sg_vault/bare` +
   `.sg_vault/publish`**, push to GitHub.
3. Deploy with `team/explorer/dev/impl-plans/08/17/static-publishing/templates/github-pages.yml`
   (or serve the repo root with `.nojekyll`).
4. From another machine: `sgit clone <key> ./copy --base-url https://<user>.github.io/<repo>/.sg_vault`
   (co-located/flat) — or compose `publish/* + bare→api/vault/read/<vid>/bare` for the
   api-path layout.

### 3.10 Strict verification — the object-swap drill *(local-only)*

The check has no key-based exemption any more, so *authentic* objects served under the
wrong ids must be refused, not accepted.

```bash
# publish a vault, copy the site, then SWAP two objects between their filenames
cd /tmp/site-copy/bare/data
A=$(ls | head -1); B=$(ls | sed -n 2p)
cp $A /tmp/a.bak; cp $B $A; cp /tmp/a.bak $B      # both are genuine ciphertext

sgit clone <vault-key> /tmp/clone-swap --base-url /tmp/site-copy
```

Expect: a warning naming the count that **failed their content-address check**, both
swapped ids **absent** from `/tmp/clone-swap/.sg_vault/bare/data/`, and the substituted
content never reaching the working copy. Before the fix, both were accepted silently
because they decrypted.

### 3.11 A refused object that is *required* — the typed error

Tampering with a **blob** fails soft (§3.4). Tampering with a **tree or commit** hits an
object the walk cannot continue without:

```bash
# overwrite the head commit's ROOT TREE object in the copied site, then clone
sgit clone <vault-key> /tmp/clone-tree-tamper --base-url /tmp/site-copy
```

Expect an error that **names the object and the remedy** — not a raw
`FileNotFoundError` showing an internal store path, and not the generic "vault may be
corrupted, try fsck" hint. Also expect the refusal summary to appear even though the run
failed. Run it once more with a library call (no `on_progress`) to confirm the summary
still reaches **stderr** rather than vanishing.

### 3.12 `vault move` rewrites ids; `publish` refuses a store readers would refuse

```bash
sgit vault move -d /tmp/vault-a                      # note the ids before and after
```

Expect: **no object id survives** the move (the vault and its pre-move copy can no
longer be correlated), **every** object in the moved store hashes to its own id, the
moved vault clones cleanly, and the output warns that any previously published surface
is now stale and to re-run `sgit publish`.

Then the publish-side guard — append a byte to any `obj-cas-imm-*` in a vault's store
and run `sgit publish`. Expect a refusal naming the offending object and the remedy,
with **nothing written** to `.sg_vault/publish/`. This is what stops you shipping a
store that every current reader would reject.

### 3.13 The generated command reference

```bash
sgit help --format markdown | head -40
sgit help --format json -o /tmp/ref.json     # diffable between releases
```

Expect every command you exercised above to appear, with its real flags — it is walked
from the parser, so anything missing here is missing from the CLI.

## 4. Not covered by automation — needs a real-world run

- **Real GitHub Pages round trip** (matrix cell 5) and the **run-time ACAO assertion**
  (cell 10) — plus tabletop 11's still-owed items: Pages propagation under
  `max-age=600`, secret masking in Actions logs, measured provider headers.
- **The loader in a browser** — the emitted template is a documented placeholder; the
  Web team's loader (key discovery, fragment hygiene, in-page decrypt) replaces one
  constant (`Loader__Template.LOADER_TEMPLATE`).
- **`--api-docs=bundled` against the real CDN/`static.sgit.ai`** — unit tests exercise
  the machinery against a local origin with true SRI hashes.
- **Integration suite** (`tests/integration/`, Python 3.12 venv) — unchanged by this
  work but worth a run before release since clone/pull internals gained the
  verify-before-write step.
