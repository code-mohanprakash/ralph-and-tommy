# Ralph & Tommy

Buyer and seller agents that negotiate bulk secondhand-clothing deals for Fleek.

- **Ralph** works for a buyer: what they want, how many, and a private maximum price.
- **Tommy** works for a seller: stock, list prices, bulk discounts, and a private floor.
- The AI decides what to offer. Code decides what is allowed. The secret prices never go into the AI.

> Work in progress, built in small steps. The pull requests show the history.

## Run the checks

You need [uv](https://docs.astral.sh/uv/). It installs Python 3.12 and the tools for you.

```bash
uv sync
make check
```

`make check` runs ruff (lint and format), mypy (strict types) and pytest.

## Layout

| Folder | What's in it |
|---|---|
| `src/fleek_agents/` | the code |
| `tests/` | the tests |
