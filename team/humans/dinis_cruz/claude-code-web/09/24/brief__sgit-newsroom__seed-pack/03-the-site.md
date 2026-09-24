# 03. The site

## Non-negotiable: it works offline

The first reader will open it on a plane. So:

- **Static HTML, built by a script, opened from `file://`.** Double-clicking `site/index.html` must work with no server and no network.
- **No external anything.** No CDN scripts, no web fonts, no remote images, no analytics. System fonts.
- **No `fetch()` of local files.** Browsers block it on `file://`. Data a page needs is inlined into that page at build time (a `<script type="application/json">` block is fine).
- **Relative links only.** Every link between pages is relative, so the folder can be moved, zipped or served from any path.
- **Search works offline.** A small client-side search over an index inlined into the search page.
- **External links are marked** (↗) and open the live site; the local copy is always one click away beside them.

## Build

- `python3 tools/build.py` turns `sources/`, `data/`, `editions/`, `stories/`, `history/`, `signals/` and `loose-ends` into `site/`.
- **Standard library only.** No pip installs. Write a small markdown renderer (headings, paragraphs, lists, tables, code, links, emphasis); the sources use nothing more exotic.
- **Deterministic.** The same inputs build the same bytes.
- **A validator** (`tools/validate.py`) that fails the build on: a broken relative link, an external script or stylesheet, a `fetch(` in any page, a credential-shaped string (see `05-house-rules.md`), or a page without a provenance block.
- Also emit `site/llms.txt` and a `.md` twin of every page, the way every site in the network does.

## Pages

| Page | What it shows | Written by |
|---|---|---|
| **Front page** | Today's edition (the latest one), with the lead story, the counts of what changed per site, and links to the loose ends and signals. | Journalist |
| **Editions** | One page per day that had changes, newest first. | Journalist |
| **Stories** | Longer pieces from the editions. | Journalist |
| **The index** | Every page on every site: filter by site, type, date and concept. Each row links to the local copy and the live page. | Librarian |
| **Reading room** | Every source file rendered as a readable page, with its provenance block. The "new since 18 September" list first. | Librarian |
| **Concepts** | The recurring ideas, and every page that uses each. | Librarian |
| **Vaults** | Every published vault across the network, what it holds, its read key if the site publishes one. | Librarian |
| **History** | The week's moment, lessons learned, decisions and contradictions. | Historian |
| **Signals** | Cross-pollination: site A has X, site B should know. | Guest desks |
| **Loose ends** | What was said and not done. | All desks |
| **The newsroom** | A picture of the desks and the flow between them, with what each desk read and wrote on the latest day. | Build, from the data |
| **About and method** | What runs, what is design, who reviews, how sources are frozen. An "honest sentence" like newsroom.sgit.ai's. | Editor |

## The provenance block

Every page that states anything about a source carries, visibly: the site, the live URL, the date and time the source was fetched, its sha256 (first 12 characters are enough on screen), and which desk wrote the page. A reader must be able to walk from any claim to the frozen copy it came from.

## Look

Borrow the look of sgit.ai: warm off-white background, near-black ink, one blue accent, a serif for headings, system sans for text, monospace eyebrows. Readable on a phone with a 16px gutter and no horizontal scroll. A dark mode is welcome and not required for the first version.

## Data files

| File | What it is |
|---|---|
| `sources/sites/manifest.json` | Every fetched file: URL, local path, bytes, sha256, fetched time. Written by `tools/fetch_sources.py`. |
| `data/changes/YYYY-MM-DD.json` | The Librarian's changes for the day: per file, site, type, title, one-line summary, concepts. |
| `data/index.json` | Every page in the network, with type, title, date if known, concepts. |
| `data/concepts.json` | Concept name, one-line definition, the pages that use it. |
| `editions/YYYY-MM-DD.md` | Front matter: `date`, `desk`, `sources` (list of URLs), `reviewed_by`, `reviewed_on`. Then the edition. |
| `stories/*.md`, `history/*.md`, `signals/*.md` | Same front matter shape. |
| `data/loose-ends.json` | Where said, when, what, waiting on, status. |
