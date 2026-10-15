## `require_signatures` in sgit_ai/core/actions/pull/Vault__Incoming_Check.py (L13-L53)

**Purpose:** The signature policy gate for a head about to be accepted. Under feature `signatures-required`, every commit from `incoming_head` down to what the clone already holds (and down to the recorded policy start) must classify `verified`, or the function raises `Vault__Signature_Error` before the caller writes anything. Pull (writable and read-only), branch switch (fetch of a never-fetched branch) and push call it (module docstring L3-L5; `Vault__Sync._fetch_branch_for_switch` L204; `Vault__Sync__Push.py:L196`).

**Inputs & Assumptions:**
- `directory` (str), `c` (Vault__Components), `read_key` (bytes): trusted, local.
- `incoming_head` (str): the server's head for the branch. Trust: **semi-trusted** — decrypted under the read key (`Step__Pull__Fetch_Remote_Ref._parse_ref`), so a read-key holder's value; path-safe only because every use is through `obj_store.exists`/`load` with `Safe_Str__Object_Id`-shaped ids downstream — but `incoming_head` itself is a plain `str` taken from `json.loads(...).get('commit_id')` (`Vault__Sync__Status._parse_ref` L251). It reaches `os.path.join` in `Vault__Object_Store.object_path` (L96-L97) via `exists` (L93-L94) in `local_history` L67 and `_fetch_commit_chain` L293. **Nothing found** on the pull path that validates `incoming_head` against `OBJECT_ID__REGEX` before it is used as a filename component; `Schema__Pull__State.named_commit_id` is `Safe_Str__Commit_Id` (regex `[^a-zA-Z0-9\-]` *replaced*, `Safe_Str__Commit_Id.py:L7`), which sanitises rather than refuses, and that sanitised value is what `Step__Pull__Fetch_Missing` passes here (L50, L26-L27 of the step). So `/` and `.` cannot survive into the id; the risk is a wrong-but-safe name, not traversal.
- `held_head` (str): what this clone already holds (its clone-branch head, or for a reader the last accepted head). Trust: trusted (local ref/baseline).
- Implicit: the local index file (L27-L30), the local object store, `.sg_vault/local/config.json` for shallow boundaries (L39), the server (L42-L43 fetches missing commits; L44-L46 may fetch key files).

**Outputs & Effects:**
- Returns `None` (policy off, nothing incoming, or everything verified) or raises `Vault__Signature_Error` (L49-L53).
- **Writes:** commit objects downloaded by `_fetch_commit_chain` (verified-before-write, `Vault__Sync__Status.py:L304`) and key files by `Vault__Key_Fetch` (see record). No ref, baseline, index or working-copy write.
- Raises `FileNotFoundError`/`InvalidTag`/`ValueError` from `load_branch_index` (L30) when the index is present but unreadable — fail closed (docstring L18, TM-R25).

**Block-by-Block:**

```python
# L19-L20
if not incoming_head or incoming_head == held_head:
    return
```
- **What:** Nothing incoming.
- **Assumes:** `held_head` really is held — the callers pass the clone's own ref (`Step__Pull__Fetch_Missing` L27 `clone_commit_id`) or, for a reader, `accepted or local ref` (`Step__Pull__RO__Load_Named_Head` L81-L83, cleared when the object is absent).

```python
# L27-L32
index_id = str(c.branch_index_file_id or '')
if not index_id or not os.path.isfile(c.storage.index_path(directory, index_id)):
    return                                                         # no index (single-branch vault): no policy
index = c.branch_manager.load_branch_index(directory, index_id, read_key)
if not Vault__Format().has_feature(index, FEATURE_SIG_REQUIRED):
    return
```
- **What:** Policy lookup from the **local** index copy.
- **Why here:** before any fetch, so a vault without the feature costs nothing.
- **Assumes:** the local index reflects the owner's current policy. It does on pull because `Step__Pull__Load_Branch_Info._refresh_index` (L17-L45) merged the server copy first — with the gate taken from the *server* copy (`Vault__Index_Sync.merge` L95-L100). So: a host that replays an older index without the feature turns the policy off for this check (TM-R29, named in the threat model §5 Format-gate row). A present-but-unreadable index raises here (no `try`), which is the TM-R25 fail-closed. For `_fetch_branch_for_switch` and push there is also a refresh before this call? — not traced here; see Open Questions.
- **Establishes:** `index` parsed, feature on.
- **Depended on by:** L36 (`policy_start(c, index)`), L45-L46 (`index=index` for the branch→key fallback).

```python
# L33-L36
stop = self.local_history(c, read_key, held_head)                  # what this clone already holds is not incoming
if incoming_head in stop:
    return                                                         # behind or equal: nothing incoming
stop |= self.policy_start(c, index)                                 # commits from before the policy was switched on
```
- **What:** `stop` = every commit reachable from `held_head` through local objects, plus the recorded `signed-since` commit (if local).
- **Why here:** `local_history` walks *all* parents (docstring L56-L59): a divergent merge base is already-held, so pre-policy history is not dragged in. `policy_start` adds the anchor so commits before it are not expanded (they sit behind the anchor in the graph).
- **Assumes:** that "reachable from the held head" ⇒ "already accepted under the policy". For a writable clone `held_head` is the clone branch's head, which includes the clone's own unpushed commits — those were made locally, fine. For a reader it is the last accepted head. Both are local state, not server state.
- **Establishes:** `stop` is the frontier; everything reachable from `incoming_head` that is not in `stop` is "incoming".
- **Depended on by:** L42-L46.

```python
# L37-L43
bounds = set()
try:
    bounds = set(Vault__Scope().from_local_config(self._read_local_config(directory, c.storage)).boundary_ids())
except Exception:
    pass
Vault__Sync__Status(crypto=self.crypto, api=self.api)._fetch_commit_chain(
    c, c.obj_store, read_key, incoming_head, limit=10000, known=stop | bounds, boundaries=bounds)
```
- **What:** Fetch (verify-before-write) the incoming commit objects, up to 10,000, stopping at known commits and shallow boundaries.
- **Why here:** `verify_chain` classifies only local objects (`status_of` → `missing`); the commits must be here first. The return value `(fetched, connected)` is **discarded** — an unreachable server or a chain longer than 10,000 leaves commits `missing`, which `verify_chain` then reports as `first_failure=(cid, 'missing')` → refusal. So "could not fetch" refuses, it does not pass.
- **Assumes:** `_fetch_commit_chain` writes only through `Vault__Verified_Write.save` (`Vault__Sync__Status.py:L304`), so a host cannot plant a commit object under a wrong id.
- **Establishes:** best effort: the incoming commits are local.
- **Depended on by:** L45-L46.

```python
# L44-L53
key_fetch = Vault__Key_Fetch(crypto=self.crypto, api=self.api)
report    = Vault__Signatures(crypto=self.crypto, key_fetch=key_fetch).verify_chain(
    c, read_key, incoming_head, stop_at=stop, index=index, boundaries=bounds)
if report['first_failure']:
    cid, status = report['first_failure']
    raise Vault__Signature_Error(...)
```
- **What:** Classify the incoming set; refuse on the first non-verified.
- **Why here:** last; everything needed is local.
- **Assumes:** `verify_chain` semantics (see record): `missing`, `unsigned`, `no-key`, `bad` all refuse. `Vault__Signature_Error` is in `_print_friendly_error`'s "refused on purpose" list (`CLI__Main.py:L1027-L1035`) and propagates through `Workflow__Runner` as the same type (`Workflow__Runner.py:L126-L130`).
- **Establishes:** on return, every incoming commit is `verified` (= signed by some key file that decrypts under the read key — TM-R01).
- **Depended on by:** every accept that follows: `Step__Pull__Fetch_Missing._accept` L29-L44; `Step__Pull__RO__Checkout` L94-L100; `Vault__Sync._fetch_branch_for_switch` L206-L211; push (`Vault__Sync__Push.py:L196`, not read).

**Cross-Function Dependencies:**
- Callee `local_history`, `policy_start` (internal): see records.
- Callee `Vault__Branch_Manager.load_branch_index` (internal, L88-L96): decrypt, parse, `check_client`. A `Vault__Client_Too_Old_Error` propagates (refusal by name).
- Callee `Vault__Format.has_feature` (internal, L61-L62): `name in [str(f) for f in index.features]`.
- Callee `Vault__Sync__Status._fetch_commit_chain` (internal, L255-L326): read in full; see `_fetch_missing_objects` record for the sibling path. Note it uses `c.sg_dir` as `base_dir` for `Verified_Write.save` (L304) and `c.vault_id` for the API.
- Callee `Vault__Signatures.verify_chain` (internal): see record.
- Callers: `Step__Pull__Fetch_Missing._enforce_signature_policy` L26-L27 (writable pull **and** read-only pull — the RO workflow reuses this step, `Workflow__Pull__ReadOnly.py:L34`); `Vault__Sync._fetch_branch_for_switch` L204-L205; `Vault__Sync__Push.py:L196`. Each of those does its ref/baseline write **after** this call returns.
- Shared state: object store, key store; reads the index and config.
- Invariant coupling: this is the enforcement point of the system rule "nothing writes a local named ref or a baseline except verify-then-accept" (docstring L3-L5; tests `tests/security/test_Security__Fixed__Verify_Then_Accept.py::test_N3__a_refused_pull_leaves_no_local_ref_for_a_switch_to_check_out`, `::test_N2__switch_to_a_never_fetched_branch_refuses_an_unsigned_head`, `tests/security/test_Security__Fixed__Trust_And_Policy.py::test_K2__a_refused_read_only_pull_refuses_again`).

**Open Questions:**
- unclear; whether push (`Vault__Sync__Push.py:L196`) and `_fetch_branch_for_switch` refresh the index from the server before calling this, as pull does. If not, they apply the clone's cached policy, which may be older than the owner's (either direction).
- unclear; `limit=10000` on L43: a branch with more than 10,000 incoming commits refuses with `missing`. Intended ceiling or incidental.
