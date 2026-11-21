# Contributing to Invesha

Thanks for helping improve Invesha.

## Set up

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Before opening a pull request

- `ruff check src tests` and `ruff format --check src tests` pass
- `pytest --cov` passes (coverage must stay above 85%)
- New model logic has a test that checks the numbers by hand
- Excel changes keep formulas recalculating to the engine's values (see `tests/test_excel_cli.py`)

## Where things live

- `src/invesha/` engine: models, Excel export, file extraction
- `web/` the web platform and the Academy
- `tests/` unit tests and fixture files
