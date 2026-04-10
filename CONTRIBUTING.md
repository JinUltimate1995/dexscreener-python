# Contributing

Thanks for considering a contribution.

## Development setup

```bash
git clone https://github.com/JinUltimate1995/dexscreener-python.git
cd dexscreener-python
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running tests

```bash
pytest tests/ -v
```

## Linting

```bash
ruff check .
mypy dexscreener/
```

## Pull requests

1. Fork the repo and create a branch from `main`.
2. Add tests for any new functionality.
3. Ensure `pytest`, `ruff check`, and `mypy` all pass.
4. Keep PRs focused — one feature or fix per PR.
5. Update `CHANGELOG.md` if your change is user-facing.

## Reporting bugs

Open an issue with:
- Python version
- `dexscreener-python` version
- Minimal reproduction code
- Expected vs actual behavior

## Code style

- We use [ruff](https://docs.astral.sh/ruff/) for linting and formatting.
- Type annotations are required for all public APIs.
- All public functions need docstrings.
