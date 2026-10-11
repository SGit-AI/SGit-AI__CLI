# review/intent — the design as data (top-down)

Written by the sgit-ai CLI agent on 2026-10-11 from the threat model
(`team/explorer/appsec/threat-model/v0.21.0__threat-model.md`), which is the project's statement
of what the code is meant to guarantee. Every node names the section it came from. Accepted by
the project lead when the plan was accepted (11 Oct); corrections go in `BRIEF-CORRECTIONS.md`.

| File | Nodes | Source |
|---|---|---|
| `assets.json` | what must be protected, where it lives, who must not get it | threat model §2 |
| `actors.json` | A1–A8, what each holds and can do | threat model §3 |
| `boundaries.json` | the trust boundaries and what crosses them | threat model §4 |
| `mechanisms.json` | each security mechanism, what it guarantees, what it does not, and the slice files that implement it | threat model §5, joined to `review/slice.json` by hand |

The join to the code layer (`review/graph/`) is through `mechanisms[].files`: each mechanism names
the files in the slice that implement it, and `review/graph/files.json` names the tests that
import each of those modules. The `register` fields name risk-register rows (TM-Rnn, TM-Fnn).

These files are written by an agent and accepted by a person. They are not derived, and nothing
regenerates them.
