# sgit-ai Briefing Pack — Index

**Date:** 2026-03-20
**Version:** v0.8.10
**Status:** Active development (Alpha)
**Prepared by:** Explorer Team (Architect, Developer, QA, Librarian)

## Purpose

This briefing pack is a **stand-alone reference** for any LLM session (Claude Code,
Claude Web, or new contributors) that needs to understand, modify, or extend the
`sgit-ai` CLI tool. Read this pack before touching the code.

## How to Read This Pack

**If you're brand new** — start with `01__PROJECT_OVERVIEW.md`, then `02__ARCHITECTURE.md`.
**If you're implementing a feature** — read `11__DEVELOPER_GUIDE.md` and the relevant system doc.
**If you're debugging** — check `10__KNOWN_ISSUES.md` first, then the relevant layer doc.
**If you're reviewing** — `09__TEST_COVERAGE.md` and `08__TYPE_SYSTEM.md` for quality context.

## Document Map

```
briefing-pack/03/20/
 |
 |-- 00__INDEX.md .................. YOU ARE HERE — navigation and reading order
 |
 |-- 01__PROJECT_OVERVIEW.md ....... What is sgit-ai? Mission, status, identity
 |                                   Audience: Everyone
 |
 |-- 02__ARCHITECTURE.md .......... Full system architecture with ASCII diagrams
 |                                   Layer map, dependency direction, class inventory
 |                                   Audience: Architects, Senior Developers
 |
 |-- 03__DATA_MODEL.md ............ Schemas, Safe_* types, object store layout
 |                                   Every schema class documented with fields
 |                                   Audience: Architects, Developers
 |
 |-- 04__CRYPTO_DESIGN.md ......... Cryptographic design: AES-GCM, HKDF, PBKDF2
 |                                   Key derivation flows, zero-knowledge guarantees
 |                                   Audience: Security reviewers, Architects
 |
 |-- 05__SYNC_ENGINE.md ........... Sync lifecycle: init, commit, push, pull, merge
 |                                   Branch model, three-way merge, conflict handling
 |                                   Audience: Developers
 |
 |-- 06__CLI_REFERENCE.md ......... Every CLI command with usage, args, examples
 |                                   Audience: Users, Developers
 |
 |-- 07__API_LAYER.md ............. Server API protocol: endpoints, auth, batch ops
 |                                   Audience: Developers, Backend engineers
 |
 |-- 08__TYPE_SYSTEM.md ........... Type_Safe framework patterns and conventions
 |                                   Safe_* types, schema rules, naming conventions
 |                                   Audience: Developers (MUST READ before coding)
 |
 |-- 09__TEST_COVERAGE.md ......... Test inventory, coverage analysis, gaps
 |                                   Audience: QA, Developers
 |
 |-- 10__KNOWN_ISSUES.md .......... Bugs, gaps, risks, and their severity
 |                                   Audience: Everyone
 |
 |-- 11__DEVELOPER_GUIDE.md ....... How to set up, develop, test, and contribute
 |                                   Audience: New developers (MUST READ first)
```

## Quick Facts

| Property              | Value                                         |
|-----------------------|-----------------------------------------------|
| Package name (PyPI)   | `sgit-ai` (was `sg-send-cli`)                 |
| CLI command           | `sgit`                                        |
| Import name           | `sg_send_cli` (current, pending rename)       |
| Python                | >= 3.11                                       |
| Dependencies          | `osbot-utils` (Type_Safe), `cryptography`     |
| Source modules        | 93 Type_Safe classes across 9 packages        |
| Unit tests            | 971 passing (4 xfail, 87 skipped integration) |
| License               | Apache-2.0                                    |
| Repository            | `the-cyber-boardroom/SG_Send__CLI`            |

## Key Constraints (Non-Negotiable)

1. **Zero raw primitives** in Type_Safe classes — use Safe_Str, Safe_Int, Safe_UInt
2. **No Pydantic, no boto3, no mocks** — Type_Safe + `cryptography` only
3. **Crypto interop** — Python output must match Web Crypto API byte-for-byte
4. **Zero plaintext on server** — server never sees file names, content, or keys
5. **All behavior in methods** — no module-level functions, no @staticmethod
