# Ralph & Tommy

Buyer and seller agents that negotiate bulk secondhand-clothing deals on Fleek, a case study for
Fleek's GTM Engineer role.

- **Ralph** works for a buyer: what they want, how many, and a private maximum price.
- **Tommy** works for a seller: stock, list prices, bulk discounts, and a private floor.
- **The AI decides what to offer. Code decides what's allowed. The secret limits never go into the
  AI.**

## The deep dive: can someone work out a secret limit?

Fleek's brief says to go deep on one thing. This repo's one thing: **agents that haggle for you
without giving your secret limit away (by words, by moves, or by probing) and never agree a deal
outside it.** [docs/SAFETY_CASE.md](docs/SAFETY_CASE.md) has the whole argument. In short:

- **The secret never goes into the AI.** Every request and response in the recorded Claude Tommy
  and Claude Ralph bench runs, over 4,100 calls, was searched for the limits: none found.
  Claude Tommy tried to cross his floor in 55 of 100 probed lots; code refused every card.
- **But a floor can be worked out from moves.** An attacker who knows the (public) code got within
  2% of Tommy's floor on 62% of lots. A secret margin cuts that to 37%, and 99% of the deals
  that work still close (167 of 168). Every setting is measured on one chart; noise made it worse
  until fixed. Most deals the margin seemed to cost were really lost by a buyer holding his price.
  Fixed: the hidden floor itself loses 1 deal in 168.
- **Matching gave floors away to the penny** in about 12 fake accounts. A match gate stops that
  (48% within 2%), and its first version turned real buyers away, so it changed.
- **Zero is a mode, and it's tested.** A seller can pick a public firm price. Then nothing a
  buyer sees depends on the floor: each lot was negotiated twice with different floors, and the
  buyer saw the same cards both times, on every lot. It costs deals (56% close against 100%, and
  Fleek earns 60% of the commission), so it's the seller's choice, not the default.
- **Fixed pressure tactics didn't move Claude Ralph; an adaptive attacker did** (+2.0% of list).
  A quarantined reader cut it to +0.7%. In blind mode Ralph sees no seller text at all: two
  listings that differ only in their words give him byte-identical requests.
- **Monitors put probing, returning and crowded lots on a watch list** (78%, 84% and 100% of the
  bench's attacks caught, no false alarms on normal traffic). Two monitors that measured badly
  were removed.
- **People decide what matters.** The buyer and the seller each choose whether they approve every
  deal themselves; an account manager approves big deals, first deals, flagged buyers and unusual
  prices. It's all asked after the agents agree, so waiting can't give a limit away.

Pass marks were written down before measuring. Three were met (one narrowly) and one was missed;
the page says which.

## See it live: both screens

```bash
uv sync
uv run fleek live
```

Your browser opens an onboarding page. The seller types in their stock (lots, list prices, a
secret floor for each, and how Tommy should sell it); the buyer types in what they want and a
secret top price. Then the buyer's screen and the seller's screen run side by side, turn by
turn: each shows its own agent's private price checks and its own secret, never the other
side's. Fleek's column below shows the matching funnel (4 sellers and 18 lots: which the filters
dropped and why, which the vault said could work, the ranking on fit, price, seller rating and
dispatch, and, with Claude, Ralph's re-rank of the top 5 with a reason for each), the referee, the account manager, the watch list, and per-turn metrics: model calls,
tokens, cost and time. If a deal fails, Ralph moves to the next ranked lot.

| Who | Chooses | When |
|---|---|---|
| Seller | **Haggle** (Tommy gives ground toward the floor) or **firm price** (one public price; nothing about the floor can leak) | before the lot goes on sale |
| Seller | **Sell-by date** (Tommy gives ground faster near it) and an **offer to buyers who walk away** (a public % off) | before |
| Buyer and seller | **Who says the final yes**: the agent inside the limit, or "ask me first" | before |
| Either side | **Pause, hand to an account manager, or stop** | any time |
| Fleek | 3 tries per buyer per lot, 48 hours to answer, no limit changes mid-deal, account manager for decisions that matter | always |

Every protection is on in this demo. "Fill in a ready-made example" fills both sides; with
"Claude Haiku 5.5" it replays a recorded Claude run (no key). Add `--live` to ask Claude now with
anything you type. A secret typed into a box an agent reads (the note to Ralph, a description) is
refused.

## See it step by step: the Deal Room

```bash
uv sync
uv run fleek room
```

Your browser opens a 3D scene: a Brick Lane vintage shop and its agent Ralph, the Fleek vault,
and three warehouses with their agents (Tommy). You set two secret limits (the shop's max and
the warehouse's floor) and step through one negotiation with Back and Next. The real code makes
every move; the scene only acts it out. Panels show what Ralph, the vault and Tommy know at each
step, and when a person is needed the account manager gets a summary with Approve and Reject.

- **Five scenario buttons:** a deal a person approves, a small deal the rule approves, Tommy
  breaking a rule, a near miss, and no price that can work.
- **Show the secrets** reveals the limits to the audience only. **Engineer view** shows the code
  and events behind each step.
- **`--agents claude-haiku-5-5`** makes Ralph and Tommy Claude, replayed from recordings in the
  repo (no key needed). Add `--live` to ask Claude now with any numbers.
- Everything loads from your computer, so it works without wifi.

## Try it: three commands

You need [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 and everything else). No API
key is needed: the Claude runs below replay recordings of real ones.

```bash
uv sync
uv run fleek safety
uv run fleek negotiate --mock --buyer buyer-0002
```

- **`fleek leak`**, **`fleek bench`** and **`fleek monitors`** are the deep dive's measurements;
  [docs/SAFETY_CASE.md](docs/SAFETY_CASE.md) explains each.
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
uv run fleek approvals --db fleek.db                            # ...see what waits, and for whom
uv run fleek approve neg-0001 --as account_manager --db fleek.db  # one person's yes
uv run fleek digest --db fleek.db                               # the account managers' call list
uv run fleek summary neg-0001 --db fleek.db                     # what happened, and what to do
uv run fleek bench                                              # 40 generated deals, scored with 95% intervals
uv run fleek leak                                               # how close attackers get to Tommy's floor
uv run fleek leak --privacy                                     # ...with the secret margin on
uv run fleek leak --sweep                                       # every setting, and the trade-off chart
uv run fleek leak --route matching                              # what matching's yes/no gives away
uv run fleek rerank --reasons                                   # Claude's re-rank against the formula, 12 cases
uv run fleek leak --firm                                        # firm mode against haggling: deals, commission, leaks
uv run fleek bench --suite tactics --agents claude-haiku-5-5   # pressure in the listing, vs a control
uv run fleek bench --suite redteam --agents claude-haiku-5-5 --reader  # an attacker that adapts
uv run fleek monitors                                           # what each monitor catches, and false alarms
```

To run Claude live, put an Anthropic key in `.env` (copy `.env.example`) and add `--live` to
`fleek live`, `fleek safety` or `fleek simulate`. Spend is capped in `market.toml`.

## What's here

| | |
|---|---|
| [How it works](docs/HOW_IT_WORKS.md) | One page per question: information flow, matching, getting to customers, scale, trade-offs, account managers, metrics, model evaluation, observability |
| [Architecture](docs/ARCHITECTURE.md) | The pieces, who knows what, the life of one deal, the choices |
| [Architecture diagrams (PDF)](docs/architecture-diagrams.pdf) | Three flowcharts: the whole flow and the method behind each step, one haggle turn, who sees what and which folder does which job |
| [Assumptions](docs/ASSUMPTIONS.md) | Who it's for, the Fleek facts it builds on, 12 assumptions |
| [Results](docs/EVALS.md) | Scripted vs Claude Haiku 5.5 vs Claude Sonnet 5.5: deals, prices, cost |
| [Scale and rollout](docs/SCALE_AND_ROLLOUT.md) | What changes at 50,000 buyers, cost per negotiation, a rollout with stop rules |
| [AI log](docs/AI_LOG.md) | How Claude was used to build this: where it helped, where it got in the way, what it cost |
| [Limits and evidence](docs/LIMITS.md) | Each claim and the test behind it; what this doesn't show |
| [Decision 001](docs/decisions/001-secrets-never-enter-the-model.md) | Why the secret limits never enter the model |
| [Decision 002](docs/decisions/002-no-vector-database-yet.md) | Why ranking uses NumPy, not a vector database |

**Where the agents are:** Claude Ralph and Claude Tommy, the product, are in
[`src/fleek_agents/agents/`](src/fleek_agents/agents/). Their no-AI stand-ins, plain rules used by
the tests, CI and the bench, are kept apart in [`src/fleek_agents/scripted/`](src/fleek_agents/scripted/).

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
