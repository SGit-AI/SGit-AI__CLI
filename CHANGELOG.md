# Changelog

All notable, user-visible changes to **sgit-ai** are recorded here.

The format is loosely based on Keep a Changelog; the project follows semantic
versioning per `sgit_ai/_version.py`.

## [Unreleased]

### Added — static publishing (the "no server needed" feature set)

  - **`sgit publish`** — generates a small plaintext surface (loader, `cover.json`,
    `manifest.json`, and — only at `--visibility public`, after an explicit
    irreversibility confirmation — the public read key file) into `.sg_vault/publish/`.
    No ciphertext is copied: the manifest enumerates the store, and the served root is
    composed at deployment. Deterministic; needs only the read key, so read-only clones
    and zero-secret CI can republish. `--bundles` adds `ZIP_STORED` head/delta zips;
    `--api-spec` / `--api-docs[=cdn|bundled]` add a generated `api/openapi.json` and an
    SRI-pinned, CSP-guarded Swagger UI docs page.
  - **Static read transport** — `sgit clone` (and fetch/pull) now work from any plain
    GET host or a folder: `--transport auto|api|static|local`, with both published
    layouts auto-sniffed. Writes on a static transport raise; only an HTTP 404 means
    "absent" — a dead host raises loudly naming the host instead of diagnosing as an
    empty vault.
  - **`sgit vault serve`** — a local, read-only, loopback-bound file server for the
    published folder (browsers give `file://` documents an opaque origin), routing
    `/api/vault/read/<vid>/bare/*` to the store virtually; path-guarded, Host-checked,
    auto-publishing when the folder is absent or stale.
  - **`sgit vault mirror`** — custody without access: a keyless, verifiable copy of a
    published vault. Content-addressed objects are re-hashed (the manifest's own hashes
    are never trusted for them); hostile manifests (path traversal, over-counts,
    conflicting duplicates) are refused.
  - **`sgit vault attach`** — bind a vault key (read-write) or read key + vault id
    (read-only) to an existing `.sg_vault/bare` checkout, e.g. a fresh `git clone` of a
    one-repo vault. Validates against `bare/refs` before writing anything; a wrong key
    writes nothing.
  - **`sgit vault ignore`** — shows the always-ignored folder list; `--apply <folder>`
    removes a now-ignored folder's tracked files from the vault in one visible commit,
    leaving the work tree untouched.

### Changed

  - **`sgit vault move` now rewrites object ids.** Key rotation re-encrypts every object
    *and* recomputes its content address, rewriting the whole object graph bottom-up
    (blobs → trees → commits) so every reference stays intact. Previously objects were
    re-encrypted in place under their old ids, which meant nothing in a moved vault could
    be verified against its own content address. Two consequences: a moved vault is now
    verifiable exactly like a fresh one, and it shares **no** object id with the vault it
    came from — so the two can no longer be correlated by anyone who sees both stores.
    A vault moved by an older sgit keeps its old ids; re-run `sgit vault move` on it to
    normalise the store (clone says so if it meets one).

  - **`.github/` is no longer vault content** (it joins the always-ignored folders):
    workflow files inside a vault are the payload that turns vault-write into code
    execution on a publisher's CI runner. Existing vaults are safe — ignore rules now
    govern **untracked files only** (git's rule): paths already in the vault head are
    grandfathered across every command, with a one-time migration notice naming the
    deliberate-removal escape hatch.

### Security

  - **Verify-before-write on every download path (SP-1/I7).** Clone, fetch and pull now
    id-verify every content-addressed object (`sha256(ciphertext)[:12] == id`) before it
    touches disk, with the write path contained by `Vault__Path_Guard`; a refused object
    is skipped and reported, never written, and never aborts the run. The check is
    **strict** — there is no "but it decrypts under my key" exemption, so a host that
    swaps two authentic objects between their ids is caught rather than silently obeyed.
  - **Structural paths are never written from vault data.** A crafted vault that carries
    `.git/**` or `.sg_vault/**` entries can no longer drop files into a clone's git-hook or
    key/config directories: the checkout path refuses any entry under a protected directory
    (`.git`, `.sg_vault`, `.sg_vault_new`, `.sg_vault_old_*`), and the ignore engine refuses
    these even when a vault head already tracks them.
  - **`sgit vault serve` keeps its DNS-rebinding defence when `--bind` widens.** Host headers
    that are domain names are refused on any bind address (rebinding requires a name);
    loopback names and IP-literal Hosts are allowed. Local static reads are path-contained,
    and a per-object non-404 HTTP status fails soft rather than aborting a batch read.

  - **Path-traversal containment in vault checkout.** Vault tree-entry names are
    decrypted from vault data and chosen by whoever authored the vault, so a
    hostile vault cloned with `sgit clone` could carry an entry named
    `../../etc/foo` (or an absolute path) and overwrite files outside the working
    copy. All working-directory writes derived from vault data now pass through
    `Vault__Path_Guard`, which rejects absolute paths and `..` traversal and
    verifies the target stays under the destination.

### Removed — Simple Token / SG-Send transfer feature

The Simple Token credential scheme (`word-word-NNNN`) and the SG/Send
transfer/share/publish/export feature built on it have been **removed entirely**.
The scheme carried only ~30 bits of entropy and exposed a fast public-ID oracle;
it is no longer part of sgit. Removed:

  - Commands: `sgit share` (send/receive/publish), `sgit vault export`,
    `sgit vault share`, `sgit vault probe`, and the `sgit clone <simple-token>`
    transfer variant.
  - Code: `Simple_Token`, the word list, `Vault__Transfer`, `Vault__Archive`,
    `API__Transfer`, `Transfer__Envelope`, the transfer clone workflow and its
    steps, and the associated transfer/archive schemas.
  - The `edit_token` field on the local config and the `simple_token` config
    mode are gone; existing simple-token-addressed vaults are no longer readable
    by the CLI (re-key to a `passphrase:vault_id` vault key).

`sgit clone <vault-key>` (the `passphrase:vault_id` form), commit, push, pull,
and all standard vault operations are unaffected.
