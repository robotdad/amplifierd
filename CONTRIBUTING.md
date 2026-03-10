# Contributing to amplifierd

Thanks for your interest in contributing. amplifierd is in active early
development with a small team, so clear contribution practices help everyone
move faster. This guide covers what you need to get started.

**Note:** amplifierd is experimental. APIs, architecture, and conventions are
still evolving. If something in this guide contradicts what you see in the code,
the code wins -- and a PR to fix the docs is welcome.

## Prerequisites

- **Python 3.12+**
- **uv** -- used for dependency management and running commands
- **git**

## Getting Started

```bash
# Clone the repo
git clone <repo-url>
cd amplifierd

# Install dependencies (including dev deps)
uv sync

# Start the server
uv run amplifierd serve
```

The server runs as a FastAPI application. Once running, you can access the API
and the auto-generated docs at the endpoints it reports on startup.

## Running Tests

Tests use pytest with markers to separate test categories:

```bash
# Run unit tests only (fast, no external dependencies)
uv run pytest -m unit

# Run integration tests (may require running services)
uv run pytest -m integration

# Run the full test suite (unit + integration)
uv run pytest

# Run smoke tests (requires opt-in)
AMPLIFIERD_SMOKE_TEST=1 uv run pytest -m smoke
```

Smoke tests hit real external services and are gated behind the
`AMPLIFIERD_SMOKE_TEST=1` environment variable. Do not run them in CI without
understanding the cost and rate-limit implications.

## Code Quality

Run all three checks before submitting a PR:

```bash
# Format code (line length: 100)
uv run ruff format

# Lint (auto-fix what's possible)
uv run ruff check --fix

# Type check (basic mode)
uv run pyright
```

Configuration for ruff and pyright lives in `pyproject.toml`.

## Project Structure

```
src/amplifierd/
    app.py              # FastAPI application setup
    routes/             # API route modules
    ...
docs/
    design/
        architecture.md # Detailed architecture documentation
    plugins.md          # Plugin authoring guide
tests/
    unit/
    integration/
```

For a deeper understanding of the architecture, see `docs/design/architecture.md`.

## How to Add a Route

1. Create a new file in `src/amplifierd/routes/` (e.g., `my_feature.py`).
2. Define your endpoints using a FastAPI `APIRouter`.
3. Register the router in `app.py`.
4. Add tests in the appropriate test directory.

Look at existing route files for conventions around request/response models,
error handling, and dependency injection.

## How to Write a Plugin

amplifierd uses a plugin system based on Python entry points. See
`docs/plugins.md` for the full guide on authoring and registering plugins.

## PR Guidelines

- **Keep PRs focused.** One logical change per PR. If you find an unrelated
  issue while working, file it separately or submit it as a separate PR.
- **Include tests.** New functionality needs tests. Bug fixes should include a
  test that would have caught the bug.
- **Run quality checks before submitting.** Format, lint, and type check your
  code. PRs that fail these checks will be sent back.
- **Write a clear description.** Explain what the PR does and why. Link to
  relevant issues if they exist.
- **Expect review.** The team is small, but every PR gets reviewed. This is not
  a gate -- it is how we learn from each other and catch issues early.

## Experimental Status

amplifierd is pre-1.0. This means:

- APIs may change without deprecation cycles.
- Internal module boundaries may shift.
- What works today may be restructured tomorrow.

If you are building something substantial on top of amplifierd, talk to the team
first. We want to support external use but need to set expectations about
stability.
