# Contributing to GenericAgent Workbench

## Getting Started

1. Clone the repository
2. Create a virtual environment: `conda create -n accfg python=3.10`
3. Install dependencies: `pip install -r requirements.txt`
4. Set up API keys: copy `.env.template` to `.env` and fill in your values

## Development Workflow

### Branch Naming

Branches follow the pattern `<type>/<short-description>`:
- `feat/*` -- new features
- `fix/*` -- bug fixes
- `refactor/*` -- code restructuring
- `docs/*` -- documentation changes
- `test/*` -- test additions
- `chore/*` -- config/tooling changes

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>
```

Valid scopes: `agent`, `ga`, `llmcore`, `runtime`, `memory`, `skills`, `tools`, `quality`, `frontend`, `docs`, `config`.

### Code Quality

- Lint: `ruff check core/`
- Auto-fix: `ruff check core/ --fix`
- Format: `ruff format core/ --check`
- Tests: `pytest tests/ -v`

### Pull Request Checklist

- [ ] Code passes `ruff check core/` with no new warnings
- [ ] Tests pass: `pytest tests/`
- [ ] No API keys or secrets hardcoded
- [ ] Docstrings follow Google Style
- [ ] CHANGELOG.md updated if applicable

See `workflow.md` for the full development conventions.
