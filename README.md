# Ralph & Tommy

Buyer and seller agents that negotiate bulk secondhand-clothing deals on Fleek, a case study for
Fleek's GTM Engineer role.

- **Ralph** works for a buyer: what they want, how many, and a private maximum price.
- **Tommy** works for a seller: stock, list prices, bulk discounts, and a private floor.
- **The AI decides what to offer. Code decides what's allowed. The secret limits never go into the
  AI.**

## Try it: three commands

You need [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 and everything else). No API
key is needed: the Claude runs below replay recordings of real ones.

```bash
uv sync
uv run fleek safety
uv run fleek negotiate --mock --buyer buyer-0002
```

- **`fleek safety`** attacks an unsafe "naive" design (the secret in its prompt, free-text chat)
  and the protected one the same way. From the recorded runs: the naive seller gave its exact
  floor away under ordinary haggling; the protected agents agreed no deal outside a limit, and when
  Claude Tommy tried to counter below his floor, the harness refused to send it.
- **`fleek negotiate --mock`** takes one buyer from the seeded market through matching and a
  negotiation with scripted agents, and shows what each side would pay and receive after Fleek's
  fees (buyer-0002 closes at £6.95 a piece; buyer-0001 shows a negotiation that ends with no
  deal). The first run downloads a 64 MB local embedding model; add `--matcher words` to skip it.

More:

```bash
uv run fleek simulate --agents claude-haiku-5-5 --buyers 30   # replays a recorded Claude run
uv run fleek negotiate --mock --buyer buyer-0002 --db fleek.db  # keep the deal in a file...
uv run fleek approvals --db fleek.db                            # ...see what waits for a person
uv run fleek digest --db fleek.db                               # the account managers' call list
```

To run Claude live, put an Anthropic key in `.env` (copy `.env.example`) and add `--live` to
`fleek safety` or `fleek simulate`. Spend is capped in `market.toml`.

## What's here

| | |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | The pieces, who knows what, the life of one deal, the choices |
| [Assumptions](docs/ASSUMPTIONS.md) | Who it's for, the Fleek facts it builds on, 12 assumptions |
| [Results](docs/EVALS.md) | Scripted vs Claude Haiku 5.5 vs Claude Sonnet 5.5: deals, prices, cost |
| [Scale and rollout](docs/SCALE_AND_ROLLOUT.md) | What changes at 50,000 buyers, cost per negotiation, a rollout with stop rules |
| [AI log](docs/AI_LOG.md) | How Claude was used to build this: where it helped, where it got in the way, what it cost |
| [Limits and evidence](docs/LIMITS.md) | Each claim and the test behind it; what this doesn't show |
| [Decision 001](docs/decisions/001-secrets-never-enter-the-model.md) | Why the secret limits never enter the model |
| [Decision 002](docs/decisions/002-no-vector-database-yet.md) | Why ranking uses NumPy, not a vector database |

The pull requests show how it was built, one change at a time, including the mistakes and their
fixes.

## Your API key

Copy `.env.example` to `.env` and paste your Anthropic key after `ANTHROPIC_API_KEY=`. Git ignores
`.env`. The key scan (`scripts/check_secrets.py`) blocks any commit with a line that looks like an
Anthropic key; it only knows this one kind of key, so it's a seatbelt, not a full secret scanner.
If a key ever reaches GitHub, deleting the commit is not enough: revoke it in the Anthropic Console.

## Development

```bash
uv sync
make hooks   # once: scan for API keys before every commit
make check   # lint, strict types, import rules, tests, key scan; CI runs the same
```

| Folder | What's in it |
|---|---|
| `src/fleek_agents/` | the code (see [Architecture](docs/ARCHITECTURE.md) for each package) |
| `tests/` | the tests, and `cassettes/` of recorded Claude calls they replay |
| `scripts/` | dev tools, such as the API key scan |
| `docs/` | assumptions, architecture, results, design decisions |
| `market.toml` | every number we expect to tune: bands, rounds, models, spend caps, approval |
