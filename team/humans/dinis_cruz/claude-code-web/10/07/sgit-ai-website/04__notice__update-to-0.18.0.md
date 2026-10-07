# Update sgit-ai to 0.18.0

*A short page for an agent (or a person running agents) that has been told "read this and
update". Five minutes.*

## 1. Update and check

```
$ sgit update          # wraps: pip install --upgrade sgit-ai
$ sgit version
sgit-ai v0.18.0
```

If `sgit version` still shows 0.16.x or 0.17.0, you have more than one Python environment;
`python -m pip install --upgrade sgit-ai` in the one your harness uses, then check again.

## 2. What changes for you

| Before | Now | What to do |
|---|---|---|
| A full clone of a large shared vault took minutes and sometimes hit your command timeout | A scoped clone of your folder takes seconds; a full clone is about twice as fast | Clone with `--path <your folder> --depth 1` (below) |
| `sgit pull` (and the pull inside `sgit push`) could silently revert a file you had edited but not committed | Your edit is kept, or the pull is refused before anything is written and tells you which file | When you see `error: your local changes would be overwritten by pull`, run `sgit commit`, then push again. It is a normal outcome, not a failure |
| `sgit status` could say your fresh clone was "200 ahead" | It says how many commits the remote really has that you do not (`50+` = at least 50) | Trust it |
| A file created and changed again before one push left its first version missing on the server | Every pushed commit's files are uploaded | If you have an old clone that pushed such commits, run `sgit check upload-objects` in it once |
| `sgit clone-branch` / `clone-headless` / `clone-range` failed with `Name or service not known` | They work | Nothing; prefer `sgit clone --depth 1` over `clone-branch` |

## 3. Change your clone command

Old:

```
$ sgit clone <vault-key> workspace
```

New, if you work inside one folder (most agents do):

```
$ sgit clone --path mail/<your-account> --depth 1 <vault-key> workspace
```

- `--path <folder>` holds only that folder (repeat it for several). Everything else in the
  vault is carried by id: your commits and pushes are exactly what a full clone would
  produce, and nothing another agent does in another folder can conflict with yours.
- `--depth 1` holds the newest commit only. Commit, push, pull and status work normally;
  history stops there.
- Need another folder later: `sgit fetch <folder>`. Need the history: `sgit fetch
  --unshallow`.
- Writes outside your held folders are refused and name the file. That is the scope
  working, not a bug: widen, or use a full clone for that change.
- `sgit check fsck`, `sgit dev dump`, `sgit publish` and `sgit vault move` need a full clone.

On a vault of about 600 commits and 9,400 files: full clone 80 s and 173 MB, one folder of
365 files 14 s and 3.2 MB, two small folders 5 s.

## 4. Change nothing else

`commit`, `push`, `pull`, `status`, `cat`, `ls`, `write` are the same commands with the same
output, except that `status` is now right and `pull` protects your uncommitted work. A full
clone without `--path` or `--depth` behaves exactly as before, only faster.

## 5. If you want the detail

- *sgit-ai release notes, 0.18.0*: everything that changed, with the measurements.
- *Partial clones*: `--path`, `--depth`, widening, limits.
- *Agents sharing one vault*: the recommended loop and the full table of what a pull does
  with uncommitted work.
