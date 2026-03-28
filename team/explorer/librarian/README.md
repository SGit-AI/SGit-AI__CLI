# Librarian — Explorer Team

> Full role definition: [ROLE.md](ROLE.md)

## Core Mission

Maintain knowledge connectivity across all project artifacts, ensuring every document is discoverable, cross-referenced, and current.

## Scope

- Knowledge graph maintenance (cross-references, master indexes, link verification)
- Dependency tracking (osbot-utils version, cryptography version)
- Briefing pack maintenance (`library/sgit-ai/briefing-packs/`)
- Ecosystem health scans (broken links, stale docs, naming violations)
- Reality document currency

## Dependencies

| Package       | Min Version | Purpose                    |
|---------------|-------------|----------------------------|
| osbot-utils   | >=3.70.0    | Type_Safe framework        |
| cryptography  | >=43.0.0    | AES-GCM, HKDF, PBKDF2     |
| pytest        | >=8.0       | Testing (dev dependency)   |
| pytest-cov    | >=5.0       | Coverage (dev dependency)  |

## Quick Reference

| What | Where |
|------|-------|
| Guides | `team/explorer/librarian/guides/{MM}/{DD}/` |
| Reviews | `team/explorer/librarian/reviews/{MM}/{DD}/` |
| Version file | `sgit_ai/version` |
| Briefing packs | `library/sgit-ai/briefing-packs/` |
