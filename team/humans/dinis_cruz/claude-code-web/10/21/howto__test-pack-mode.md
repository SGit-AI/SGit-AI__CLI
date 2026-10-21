# How to test pack mode (for an agent or a person, on a throwaway vault)

**Status:** built on branch `claude/charming-babbage-5hzcxq`, not yet released; ships in 0.24.0. **What it is:** `spec__pack-mode.md` and `note__pack-mode-round-trip.md` in this folder. **Rule one:** test on a new vault you create for this. Never on a vault other people use.

## 0. Install the branch

```bash
python3 -m venv ~/sgit-packs && . ~/sgit-packs/bin/activate
pip install "git+https://github.com/SGit-AI/SGit-AI__CLI.git@claude/charming-babbage-5hzcxq"
sgit pack --help          # lists import, export, compact, ls, verify, stats
sgit init --help | grep -A2 -- --packs
```

A branch install reports the branch's version (0.22.1 today). A pack vault it creates still gates at 0.24.0, the release that reads packs, and the branch build passes that gate because it carries the feature that set it (`Vault__Format.gate_this_build_carries`); a released 0.22.1 or 0.23.0 is refused by name. So trial vaults made now keep the right gate after the release.

You need a dev token: pass `--token <token>` on every network command, or save it once with `sgit auth` (no environment variable is read). Server: `--base-url https://dev.send.sgraph.ai` (or `sgit remote add origin https://dev.send.sgraph.ai` once inside the vault).

## 1. A new pack vault, two clones

```bash
mkdir pack-a && cd pack-a
sgit init --packs --base-url https://dev.send.sgraph.ai      # prints "(pack vault)"; SAVE THE VAULT KEY
mkdir docs && for i in 1 2 3; do seq 1 500 | sed "s/^/line of file $i: /" > docs/f$i.md; done
sgit commit -m "first"
sgit push                                                     # "First push — uploading vault structure (pack vault: one snapshot pack)"
sgit pack ls                                                  # snapshots/ 1 pack, commits/ 0, archive/ 0, "* = absorbed by this clone"
sgit pack stats                                               # "loose objects under bare/data/: 0"; blobs deflated
cd ..
sgit clone <vault key> pack-b --base-url https://dev.send.sgraph.ai
diff -rq pack-a pack-b -x .sg_vault                           # no output
```

What to look at in the clone's progress lines: `Fetching packs (1 pack(s) …)`, `Packs fetched (1 pack(s), N objects, R request(s) in Xs)`. R should be 3 or 4 (two listings, the pack, keys). It must never say it is fetching `bare/data/…` objects one by one.

## 2. Push and pull between the clones

```bash
cd pack-b && echo "from b" > docs/b.md && sgit commit -m "b" && sgit push      # one commit pack in commits/
cd ../pack-a && sgit status                                                      # 0 ahead, 1 behind
sgit pull                                                                        # Merged: 1 added
sgit pack ls                                                                     # commits/ 1 pack, marked *
```

Do three commits and pushes from `pack-b`, then one `sgit pull` in `pack-a`: all three packs arrive in one batch. Then push from both sides in turn (`a` edits one file, `b` another): both converge after a pull each. Delete a file (`sgit commit --allow-deletions` if asked) and pull it on the other side.

## 3. Compaction

```bash
cd pack-a && sgit pull && sgit pack compact --dry-run     # the plan: snapshot of the head, N packs -> archive/
sgit pack compact                                         # "Did snapshot head …; N pack(s) archived. Nothing was deleted without its copy in archive/."
sgit pack ls                                              # snapshots/ 1 (the new one), commits/ 0, archive/ N+1 (the old snapshot too)
sgit pack compact                                         # second run: "already on the host", 0 archived
sgit pack verify                                          # "ok"
cd .. && sgit clone <vault key> pack-c --base-url …       # takes only the new snapshot (one pack)
cd pack-b && sgit pull                                    # holds the head already: no download, ~1 s
```

Refusals that are correct: `compact` on a clone that has not pulled ("run `sgit pull` first"), on a dirty working tree, on a normal vault ("not a pack vault").

## 4. The round trip: a normal vault in, a normal vault out

```bash
sgit clone <key of any normal vault you own> normal-src --base-url …
sgit pack import normal-src packed-src                    # new vault, new key (printed); source untouched
cd packed-src && sgit status                              # up to date, never pushed (the history IS the vault's)
sgit push                                                 # first push: one snapshot
cd .. && sgit clone <new key> packed-clone --base-url …
sgit pack export packed-clone normal-out                  # new normal vault, new key
cd normal-out && sgit push && cd .. && sgit clone <that key> normal-check --base-url …
diff -rq normal-src normal-check -x .sg_vault             # no output
sgit history log normal-check | head                      # same messages and dates as normal-src
```

`sgit check fsck .` in `normal-out` must be clean unless the source vault itself has missing objects (the import carries those references unchanged and says so: "References the source could not resolve were carried unchanged").

`pack import` records the SOURCE clone's server and token for the new vault, so its first push lands on the same server as the source. Importing a clone of a production vault means the trial vault is created on production: pass `--base-url` to the import, or `sgit remote add` in the new vault before pushing, when that is not what you want.

## 5. What to report

- Timings for clone, push, pull, compact, with the object count and the pack sizes `pack ls` prints. From a cloud sandbox the comms vault's history (33k objects, 251 MB) cloned in 25 s; a small vault should be a few seconds.
- Anything that fetches `bare/data/…` from the host on a pack vault, or writes there (`pack stats` must always show 0 loose objects).
- Any `sgit` command that behaves differently on a pack vault from a normal one, other than the pack namespace itself: `status`, `history log`, `cat`, `diff`, `branch`, `stash`, `tag` should all be unchanged (they read the local store).
- The output of `sgit --version`, the exact command, and `--debug` on a failure.

## 6. Known limits in this version (not bugs)

- No web view of a pack vault: the browser does not read packs.
- `clone --path` / `--depth` on a pack vault take the packs whole (the packs are the unit).
- Compaction is manual (`sgit pack compact`); `pack stats` shows when `commits/` has grown.
- The first push's summary line counts the commit chain capped at 100 ("Pushed 100 commit(s)"); the snapshot carries the whole history regardless.
- `sgit clone-branch`, `clone-headless` and `clone-range` do not read packs yet and say so; `sgit clone` (full, `--path`, `--depth`, read-only) does.
- Tag objects are written loose to `bare/data/` on a pack vault too (they are tiny and read by id); `pack stats` counts them separately from loose objects.
- Large histories spend seconds in the merge and status tree walks on push and pull; that is the same on a normal vault and is the next target.

When you are done, delete the throwaway vaults: `sgit vault delete-on-remote --yes` inside each.
