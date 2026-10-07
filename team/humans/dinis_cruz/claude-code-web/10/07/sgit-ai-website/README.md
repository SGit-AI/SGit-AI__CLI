# Brief for the sgit.ai website team — sgit-ai 0.18.0 (7 Oct 2026)

Four page drafts, written to be dropped into the site as they are (second person, `$`
code blocks, tables where the site uses them). Each one says where it should live.

| File | Proposed location on sgit.ai | Purpose |
|---|---|---|
| `01__release-notes__sgit-ai-0.18.0.md` | Updates → *sgit-ai release notes* (a CLI change log, which the site does not have yet: the version log at `admin/versions.html` covers the website's own versions) | Change control: what changed since 0.16, with the measured numbers |
| `02__guide__partial-clones.md` | Docs → next to *Working with AI agents* (`docs/partial-clones.html`) | How-to for `sgit clone --path` / `--depth`, `sgit fetch <folder>` / `--unshallow` |
| `03__guide__agents-sharing-one-vault.md` | Docs → `docs/agents-sharing-one-vault.html`, linked from *Working with AI agents* → *Multi-agent collaboration* | The recommended loop for a team of agents on one vault, with the new pull / status behaviour |
| `04__notice__update-to-0.18.0.md` | Updates → a short page the vault owner can point an agent team at (`updates/update-to-0-18-0.html`) | "Read this, update, change these five things" |

## Things to check before publishing

- **PyPI.** The notice tells agents to run `sgit update`. That only helps once `sgit-ai 0.18.0`
  is on PyPI It is: PyPI published 0.18.0 at 01:02 UTC on 7 Oct from the `dev → main` merge of PR #7
  (the release pipeline bumped the minor version). The pages name that version.
- **The example vault is anonymised on purpose.** Every page uses "a shared CRM vault"
  with folders like `mail/<account>/`, `runs/` and `docs/`, and the sizes "about 600 commits
  and 9,400 files". Those sizes are real (they are what the numbers were measured on) but no
  vault id, key, owner, or folder name from the real vault appears, and none should be added.
- **The numbers are measured, not estimated**, and the pages say under what conditions
  (one client in a cloud sandbox whose network path adds latency; agents on a plain
  connection will see at least these gains). Keep the conditions when editing. Source:
  `team/humans/dinis_cruz/claude-code-web/10/02/`, `10/03/` and `10/06/` in the CLI repo,
  and the CLI `CHANGELOG.md` *Unreleased* section (released as 0.18.0).
- *Working with AI agents* currently lists three clone modes for fast cold starts (sparse,
  branch, headless). Add the scoped clone as the first choice for an agent that works in one
  folder, and the shallow clone for one that needs no history; both are in page 02.
- *Installation* already documents `sgit update`; page 04 links to it rather than repeating.

## Not for the website

The session notes under `team/humans/dinis_cruz/claude-code-web/` discuss the real vault
by id and the inner workings of the fixes. They are the source of the numbers, not pages.
