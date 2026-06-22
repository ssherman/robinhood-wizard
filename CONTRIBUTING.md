# Contributing

Thanks for your interest! This project trades real money, so correctness and safety
come first.

- Use `uv` for everything: `uv sync`, `uv run pytest`, `uv run ruff check .`.
- TDD: write a failing test first, then the minimal implementation.
- Never commit secrets. Tokens, `.env`, and `*.db` are gitignored — keep it that way.
- New strategies, data sources, and executors should implement the documented
  interfaces (`Strategy`, `DataSource`, `OrderExecutor`, `Journal`).
- Run `uv run ruff format .` before committing.
