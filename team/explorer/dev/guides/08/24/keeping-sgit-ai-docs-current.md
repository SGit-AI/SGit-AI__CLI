# Keeping sgit.ai (and llms.txt) current with the CLI

**Date:** 2026-08-24 · **Audience:** the sgit.ai site agent, and whoever reviews its PRs
**Problem it solves:** the CLI ships features the website does not know about.

---

## 1. The failure this is fixing, concretely

At the time of writing, `README.md` in the CLI repo described **none** of
`sgit publish`, `sgit vault serve`, `sgit vault mirror`, `sgit vault attach`,
`sgit vault ignore`, or `--transport` — an entire shipped feature set, invisible to
anyone reading the front door. `library/skills/sg-send-cli__SKILL.md` still describes the
product under its old `sg-send` name in 47 places and knows none of the new commands.

That is not a discipline problem, it is a **source-of-truth** problem: every one of those
documents is a hand-written copy of a command surface that lives in code, and hand-written
copies of a moving thing go stale by default. Asking an agent to "remember to update the
site" reproduces the same failure with more steps.

The fix is to give the site agent something **generated**, so the question changes from
"what do you think changed?" to "what does the diff say changed?".

## 2. `sgit help --format` — the hand-off contract

```bash
sgit help --format json      -o cli-reference.json   # the contract (diffable)
sgit help --format markdown  -o commands.md          # a drop-in docs page
sgit help --format llms      -o cli-commands.txt     # an llms.txt-style index
```

`CLI__Reference` walks the parser tree that `CLI__Main.build_parser()` actually returns.
It therefore **cannot** describe a command that does not exist, and cannot miss one that
does — the anti-drift property is asserted directly in
`tests/unit/cli/test_CLI__Reference.py::test_walk_finds_every_parser_command_and_no_others`,
which recomputes the expected set from the parser and demands equality.

The JSON is the piece that matters for automation:

```json
{
  "schema": "sgit-cli-reference-v1",
  "cli_version": "v0.16.1",
  "command_count": 138,
  "commands": [
    { "path": "publish",
      "help": "Publish the vault as a static site surface",
      "options": [ { "flags": ["--visibility"], "choices": ["bare","named","public"],
                     "help": "..." } ],
      "positionals": [] }
  ]
}
```

Rendering is deterministic (commands sorted, two renders byte-identical), so a diff
between two releases is signal, not churn.

## 3. The workflow for the site agent

1. **Get the reference for the release you are documenting.**
   `pip install sgit-ai==<version> && sgit help --format json -o new.json`
2. **Diff it against the version the site currently describes.** Keep the last published
   `cli-reference.json` in the site repo; the diff is the complete list of commands and
   flags added, removed or re-helped. A new `path` is a page or section that does not
   exist yet; a vanished one is a page to retire; a changed `help` or `choices` is a
   paragraph to correct.
3. **Read the CHANGELOG for the *why*.** The reference gives you the surface; it cannot
   tell you that verification became strict or that `move` now rewrites ids. Pair it with
   the repo `CHANGELOG.md` `[Unreleased]`/release section, which is written for humans and
   states behaviour changes and their reasons.
4. **Regenerate the machine-readable index.** `--format llms` is designed to be pasted
   into (or included by) `llms.txt`, so an agent reading sgit.ai gets the real command
   list for the current release rather than a prose summary of it.
5. **Update the narrative pages by hand.** Quickstart, security model, use-cases and the
   git-to-sgit mapping are editorial and should stay hand-written — the generated
   reference is the *inventory*, not the *explanation*.

## 4. What the reference deliberately does not carry

- **Behaviour and rationale.** "Strict verification, no key-based exemption" is not a flag;
  it is in the CHANGELOG and the spec pack. Do not try to infer semantics from the surface.
- **Accepted risks and non-guarantees.** `12__accepted-risks.md` (rollback is undetectable
  on a published vault) must reach the security page by a human or agent reading it.
  Generating a command list does not discharge that.
- **Anything unreleased.** It reflects the installed version, which is the point: the site
  should describe what a reader can `pip install`, not what is on a branch.

## 5. Two version traps, one of which was live

**`sgit_ai/version` is the real version**; release automation writes it and
`sgit --version` reads it. `sgit_ai/_version.py` used to be a **hand-written literal that
had gone stale at `v0.1.0`** while the released package was `v0.16.1` — and
`Vault__Publish` stamps that constant into every published `manifest.json` as
`generated_by`. So every vault published before 2026-08-24 claims to have been produced by
`sgit v0.1.0`. `_version.py` now resolves from the `version` file, and
`test_version_is_the_real_release_version` holds it there.

The trap for the site agent: **do not read a version out of a source file**. Ask the CLI
(`sgit --version`, or `cli_version` in the reference JSON).

## 6. Suggested automation

The lowest-effort durable version of this is a release-triggered job in the CLI repo that
regenerates the three artefacts and opens a PR against the website repo:

```yaml
- run: sgit help --format json     -o cli-reference.json
- run: sgit help --format markdown -o docs/commands.md
- run: sgit help --format llms     -o llms-cli.txt
```

Then the site agent's job is reduced to reviewing a diff and writing the prose around it —
which is the part it is actually good at, and the part that cannot be generated.

**Not built yet.** This guide specifies the mechanism and ships the generator; wiring it
into the release workflow and the cross-repo PR is decision 15's territory (the workflow
generator) and should be done together with it.
