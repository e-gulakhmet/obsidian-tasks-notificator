# Repository Guidelines

## Project Structure & Module Organization

This repository contains a small Python 3.12 service that scans Obsidian task notes and sends Telegram reminders.

- `notificator/`: application package. Key modules include `config.py` for environment loading, `scanner.py` for task parsing, `reminder.py` and `state.py` for reminder state, `telegram.py` for Telegram API calls, and `jobs.py`/`main.py` for scheduled execution.
- `tests/`: pytest suite mirroring the package modules, with Markdown fixtures in `tests/fixtures/`.
- `docs/superpowers/`: design notes and implementation plans. Treat these as historical context, not runtime documentation.
- `Dockerfile` and `docker-compose.yml`: container packaging and local deployment.
- `.env.example`: required and optional runtime configuration.

## Build, Test, and Development Commands

- `uv sync --extra dev`: install runtime and development dependencies into the local environment.
- `uv run pytest`: run the full test suite.
- `uv run pytest tests/test_scanner.py`: run one focused test module.
- `uv run python -m notificator.main`: start the scheduler locally; requires the environment variables shown in `.env.example`.
- `docker compose up -d`: run the published container with values from `.env`.

## Coding Style & Naming Conventions

Use idiomatic Python with 4-space indentation, type hints where they clarify interfaces, and dataclasses for simple structured values. Keep functions small and module boundaries clear: parsing belongs in `scanner.py`, persistence in `state.py`, Telegram transport in `telegram.py`, and scheduling glue in `jobs.py` or `main.py`.

Use snake_case for modules, functions, variables, and test names. Environment variables are uppercase, for example `TELEGRAM_CHAT_ID` and `SCANNER_CRON`.

## Testing Guidelines

Tests use `pytest`, with `pytest-mock` and `respx` available for mocks and HTTP assertions. Add or update tests alongside behavior changes. Prefer focused unit tests named `test_<behavior>` and keep Markdown parsing samples under `tests/fixtures/`.

Run `uv run pytest` before submitting changes. For scanner or reminder logic, include fixture coverage for both matching and non-matching task cases.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commit style, such as `feat: add optional telegram_topic_id to Config`, `refactor(tests): use helpers`, and `ci: redeploy ...`. Follow `type(scope): summary` when useful; keep summaries imperative and specific.

Pull requests should include a short behavior summary, test results, linked issue or context when available, and configuration changes if `.env.example`, Docker, or deployment behavior changes. Include screenshots only for user-visible notification formatting changes.

## Security & Configuration Tips

Never commit real Telegram tokens, chat IDs, or local `.env` files. Keep task vault mounts read-only in Docker, as shown in `docker-compose.yml`, and store mutable reminder state under `/data`.
