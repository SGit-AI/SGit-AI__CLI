# DevOps — Explorer Team

## Scope

- CI/CD pipeline: GitHub Actions (test → tag → PyPI)
- Repository infrastructure (pyproject.toml, .github/workflows)
- PyPI publishing automation
- Python version matrix (3.11, 3.12)

## Pipeline

1. `tests.yml` — runs on push/PR to main, matrix of Python 3.11/3.12
2. `publish.yml` — runs on version tags (v*), builds and publishes to PyPI
