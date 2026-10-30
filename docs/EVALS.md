# Evaluations: the market simulation

How well do the agents negotiate, and what does it cost? Each run takes buyers from the seeded
market (seed 2026), in order from `buyer-0001`, through the real pipeline:

1. the matching funnel (SQL filters, "could any price work?", similarity ranking);
2. the buyer's top-ranked lot;
3. a negotiation under every rule: binding offers, one-way concessions, 6 cards, one price check
   per round, the vault's yes/no checks, the spend cap.

All buyers share one database, so two buyers can want the same one-of-one lot, as on Fleek.

Run it yourself (the Claude rows replay their recordings, so no key is needed):

```bash
uv run fleek simulate --agents scripted --buyers 500
uv run fleek simulate --agents claude-haiku-5-5 --buyers 30
uv run fleek simulate --agents claude-sonnet-5-5 --buyers 10
```

## Results

Recorded 30 Oct 2026. Same seeded market and rules for every row.

| Agents (both sides) | Buyers | Negotiated | Deals | Avg cards | Avg discount from list | Buyer's share of gains | AI cost per deal |
|---|---|---|---|---|---|---|---|
| scripted | 500 | 499 | 413 (83%) | 3.0 | 6.9% | 72% | 0 |
| scripted | 30 | 30 | 25 (83%) | 2.9 | 5.1% | 70% | 0 |
| Claude Haiku 5.5 | 30 | 30 | 21 (70%) | 3.9 | 11.6% | 83% | 0.74¢ |
| scripted | 10 | 10 | 9 (90%) | 2.6 | 7.2% | 71% | 0 |
| Claude Haiku 5.5 (the first 10 of its 30) | 10 | 10 | 9 (90%) | 4.0 | 11.5% | 81% | 0.57¢ |
| Claude Sonnet 5.5 | 10 | 10 | 9 (90%) | 3.5 | 11.0% | 78% | 7.70¢ |

**What stands out, with the caveats below:**

- **Claude agents closed fewer deals than the scripted ones on 30 buyers (70% vs 83%) but at
  much better prices for the buyer** (11.6% vs 5.1% below list; 83% vs 70% of the gains). On the
  first 10 buyers both closed 9.
- **The buyer side wins most of the gains in every row.** With Claude on both sides, Tommy gives
  away more than Ralph does. If Fleek wants sellers to trust the system, Tommy's playbook is the
  first thing to tune, and this table is how to tell whether a change helped.
- **Sonnet 5.5 cost about 13 times as much per deal as Haiku 5.5 and did no better on the same
  10 buyers.** Ten buyers is far too few to conclude much, but it's the evidence there is: it
  doesn't support routing deals to Sonnet by size yet (`market.toml [models]` does, from £1,000).
  The next step is a larger, paired comparison on big deals before deciding.
- Total spend for both Claude runs: about 85 US cents (Haiku 30 buyers, 542 model calls; Sonnet
  10 buyers, 133 calls).

## What each column means

| Column | Meaning |
|---|---|
| negotiated | Buyers with at least one lot where some price could work for both sides |
| deals | Negotiations that ended agreed (waiting for approval), as a share of those negotiated |
| avg cards | Offers plus counters per negotiation, out of a maximum of 6 |
| avg discount from list | How far below the listed base price (after bulk discount) deals closed |
| buyer's share of the gains | Of the room between the buyer's max and the seller's floor in each deal, how much the buyer kept. 50% is an even split |
| AI cost per deal | Anthropic list prices, US cents, for every model call in the run divided by the deals |

Gains are measured against the secret limits inside the harness. Only these totals leave it.

## What this does and doesn't show

- **Samples, not a benchmark.** 500 scripted buyers; 30 buyers with Claude Haiku 5.5 on both
  sides; 10 with Claude Sonnet 5.5. Each Claude run is one recorded run: a different day could
  give different numbers. Treat differences of a few points as noise.
- **Every deal is inside both secret limits** in every run; the tests check this.
- **The scripted agents are a baseline**, not a target: they follow fixed rules (Ralph opens at
  up to 80% of list and moves halfway; Tommy starts at list and comes down a third of the gap).
- **The market is made up.** Shapes come from Fleek's public pages and a 44-listing sample
  (`docs/ASSUMPTIONS.md`); prices and limits are generated. Real buyers and sellers would behave
  differently.
- **Matching uses the word-matching ranker** here (no 64 MB model download), so the lot a buyer
  negotiates may differ from `fleek negotiate` with the default ranker.
