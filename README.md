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
make hooks   # once: scan for API keys before every commit
make check
```

`make check` runs ruff (lint and format), mypy (strict types), pytest, and the API key scan.

## Your API key

Copy `.env.example` to `.env` and paste your Anthropic key after `ANTHROPIC_API_KEY=`. Git ignores
`.env`. Nothing reads the key yet; the Claude client comes in a later PR.

The key scan (`scripts/check_secrets.py`) blocks any commit with a line that looks like an Anthropic
key. It only knows this one kind of key, so it's a seatbelt, not a full secret scanner.

If a key ever reaches GitHub, deleting the commit is not enough: git history keeps it. Revoke the
key in the Anthropic Console and make a new one.

## Layout

| Folder | What's in it |
|---|---|
| `src/fleek_agents/` | the code |
| `tests/` | the tests |
| `scripts/` | dev tools, such as the API key scan |
