# Repository Guidelines

## Project Structure & Module Organization

- This is a Python 3.13 CLI project managed with `uv`
- Source code lives under `src/`
- `src/app/cli.py` defines the CLI entry point
- `src/notion/` contains Notion client

## Build, Test, and Development Commands

- `uv sync --dev`: install runtime and development dependencies from `uv.lock`.
- `make fmt`: run formatting
- `make lint`: verify formatting
- `make check`: run all checks

## Coding Style

- Add docstrings to created classes, methods and functions. Docstrings only in English. Always single-line docstrings, without args/return. Only one-line summary. For `__init__` methods write """Initialize class instance.""".
- Avoid generic docstrings that start with words like "Represent"; describe the model directly.
- Use `rich` for console output by default.
- Use Pydantic `BaseModel` for structured data models instead of dataclasses.
- Store Pydantic models in `resources.py` files within their modules.
- Do not use `model_config = ConfigDict(frozen=True)` in Pydantic models.
- Use python 3.13 syntax
- Run `make fmt` to format code
- Never add `from __future__ import annotations` to code

## Client Architecture

Always keep SOLID in mind.

- For every client, implement an abstract interface in `client.py`.
- For every client, implement the real client in `client.py`.
- For every client, implement the mock client in `mock.py`.
- Always follow the Dependency Inversion Principle: high-level classes must depend on abstract interfaces, not concrete clients.
- Client constructors should prefer required arguments without `None` defaults; if a client has its own config, provide a `from_config` class method that returns an instance.

## Testing Guidelines

- Use `pytest` for unit tests
- Add tests to `tests/` and use only plain files without sub-dir. For example: `tests/test_jira.py`.
- Add fixtures to `tests/conftest.py`. Prefer using fixtures.

## Security & Configuration Tips

- Never commit secrets, `.env` files, or local virtual environments
