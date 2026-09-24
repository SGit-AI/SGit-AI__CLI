# The sgit newsroom: seed pack for its first version

This zip is everything a new Claude Code session needs to build the first version of **sgit.newsroom.sgit.ai** (working name): a newsroom whose beat is the sgit network itself. Agents read every site each day, index what exists, tell the story of what changed, put it in perspective, notice where one project should know about another, and keep a list of what is falling through the cracks.

It also carries a full text snapshot of the network as of 24 September 2026, so the first version can be built, and read, with no network at all.

## How to use it

1. Create an empty repository for the newsroom (suggested name, following the Portuguese newsroom's: `SGit-AI__Website__Newsroom__Sgit`).
2. Unzip this at the root of the repository, and commit it as it is.
3. Start a Claude Code session in the repository and paste the prompt below.
4. Before you leave, pull the repository (or download it as a zip) and open `site/index.html` from your disk. It is built to work with no network.

**If the session runs short of time:** everything in `sources/` is plain markdown and text. Start with `sources/history/sgit.ai-new-pages-since-2026-09-18.md` and read in any editor.

## The prompt

```
You are building the first version of the sgit newsroom, from the seed pack in this repository.

Read, in order: START-HERE.md, CLAUDE.md, brief/01-the-newsroom.md to brief/06-house-rules.md,
sources/README.md, and the role definitions in roles/ (skim; the brief says what to take from them).

Then build v0.1 in the order of brief/04-first-version.md. The deadline is tonight and the first
reader will be offline on a plane, so:
- Step 1, the reading room, comes first and must work from file:// with the network off.
- Commit and push after every step, so the repository is usable whenever it is pulled.
- Python standard library only; no CDN, no external fonts or scripts, no fetch() of local files.

Every desk's output is a file in the repository, never only a chat message. Follow the house rules
in brief/06-house-rules.md, including the validator rule that refuses anything shaped like a vault
key. When you finish each step, say what exists, what you checked, and what is next.
```

## What is in the zip

| Path | What it is |
|---|---|
| `START-HERE.md` | This file. |
| `CLAUDE.md` | Project instructions for every session that works in the newsroom repository. |
| `brief/` | Six documents: the newsroom, the desks, the site, the first version, the daily run, the house rules. |
| `roles/` | The role definitions this builds on: from the Send project (Librarian, Journalist, Historian, Architect, Developer, Cartographer, Conductor, and the Librarian's daily run) and from sgit.ai's own team. |
| `sources/` | The snapshot: 675 text files from 29 sites with a hashed manifest, the week's change history, the briefs, and the five business-plan vaults. See `sources/README.md`. |
| `tools/fetch_sources.py` | The script that took the snapshot. The daily run uses it again. Standard library only. |

Nothing in this zip is private: it is all published on the sites it came from. No vault keys and no write credentials are included.
