# Release Note — Dotfile tracking

**Branch:** `claude/improve-cli-hidden-files-RcT0m`
**Status:** Draft — no CHANGELOG file found in the repo; place this text in
whatever release-notes file exists, or create CHANGELOG.md at the repo root
and seed it with this entry.

---

## Dotfile tracking

`sgit` no longer blanket-ignores files and directories whose names start with `.`.
Common-but-safe dotfiles (`.claude/`, `.github/`, `.editorconfig`,
`.devcontainer/`, `.dockerignore`, …) are now tracked by default just like
any other file. The curated `ALWAYS_IGNORED_DIRS` / `ALWAYS_IGNORED_FILES`
sets still exclude IDE and build caches (`.vscode/`, `.idea/`, `.next/`, …)
and known-secret files (`.env*` except `.env.example`/`.env.sample`/`.env.template`,
`id_rsa`, `.netrc`, and similar credential files).

**New command:** `sgit inspect ignored` — audit what the vault is excluding
and why:

```
# List all excluded items in the current vault directory
sgit inspect ignored

# Print the hardcoded ignore sets without a filesystem walk
sgit inspect ignored --rules

# Explain whether a specific path is tracked or ignored
sgit inspect ignored --why .env.staging
# → .env.staging is IGNORED — matched by env_secret_glob (.env*).

sgit inspect ignored --why .editorconfig
# → .editorconfig is TRACKED.
```

**Upgrade note:** existing vaults that were committed under the old blanket
rule will now see previously-hidden dotfiles appear as untracked in
`sgit status`. Run `sgit inspect ignored` to audit the full list, and add any
files you don't want tracked to `.gitignore`.
