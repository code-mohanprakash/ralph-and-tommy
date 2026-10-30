# Scale and rollout

The brief asks two things this repo can't show by running it: **what changes at about 50,000
buyers and 1,000 sellers**, and **how you'd get this in front of real customers**. This is the
plan for both. Numbers marked *measured* come from this repo; everything else is an estimate or an
assumption, and says so.

## What changes at full scale

The rules don't change. Every check that runs today (the vault's yes/no answers, one-way
concessions, binding offers, the budget across deals, the atomic accept, the append-only log)
stays exactly as it is. What changes is where things run and what holds the data.

| | Built and tested here | At 50,000 buyers and 1,000 sellers |
|---|---|---|
| **Market** | 500 buyers, 50 sellers, 1,494 lots | About 30,000 lots if sellers list as many each as here (an assumption) |
| **Database** | SQLite, one file, one writer | Postgres with the same tables, the same conditional update for accepts, and the same CHECK on stock. The app's database user can only read and insert events, so "append-only" is a permission, not only a trigger |
| **Running turns** | One process, negotiations take turns in rotation | A job queue. Each turn is already a fresh conversation built from the event log, so any worker can take any turn. One worker per negotiation at a time |
| **Opening and budgets** | The "one live negotiation per buyer and lot" check and the budget across deals read, then write. Safe with one writer | With many workers, two could pass the same check at once. Take a per-buyer lock (a Postgres advisory lock on the buyer id) around opening and around every buyer move |
| **The vault** | A package that the agents can't import (checked in CI) | Its own service, its own database and credentials. Agent workers have no network route to it; only the harness calls it, and it still answers only band words and yes/no |
| **Matching** | Rank every lot for all 500 buyers in 46 ms (*measured*, decision 002) | About 20 times more lots per buyer: roughly 2 ms per buyer, under 2 minutes to re-rank all 50,000 (*scaled from the measurement*, not run). 30,000 lot vectors take about 45 MB. Rank when a buyer's request changes or new stock arrives, not on every turn. pgvector when lots reach the millions |
| **Spend caps** | 25¢ per negotiation, 500¢ per run | Keep the per-negotiation cap. Replace "per run" with a daily budget and an alert, since there's no single run any more |
| **Approvals** | A command-line queue | The account managers' own tool. Note: "a buyer's first 3 deals go to a person" means up to 150,000 approvals if every buyer started at once. That's one more reason to roll out in steps |
| **Model calls** | About 18 per negotiation with Haiku 5.5 (*measured*) | Plan for API rate limits, and retry with backoff. Turns have a 48-hour clock, so a few seconds in a queue doesn't matter |

## What it costs

*Measured* from the recorded runs in [EVALS.md](EVALS.md), at Anthropic list prices (US cents):

| Model (both sides) | Negotiations | Model calls per negotiation | Cost per negotiation | Most expensive negotiation | Cost per deal |
|---|---|---|---|---|---|
| Claude Haiku 5.5 | 30 | 18.1 | 0.52¢ | 0.75¢ | 0.74¢ |
| Claude Sonnet 5.5 | 10 | 13.3 | 6.93¢ | 11.9¢ | 7.70¢ |

**Per 100,000 negotiations: about $520 with Haiku 5.5, about $6,930 with Sonnet 5.5.**

How many negotiations Fleek would run is not something I know. If every buyer negotiated two lots a
week (an assumption for scale only), that's 100,000 a week, so the figures above are per week.

Three ways to spend less, none built yet:

- **Batch the turns that can wait.** Most turns have hours before the 48-hour clock runs out, so
  they don't need an instant answer.
- **Use the scripted agents where they're good enough.** In the 30-buyer run they closed more
  deals than Claude (83% vs 70%) but at worse prices for buyers (5.1% vs 11.6% below list), at no
  model cost. A mix (scripted for small, simple deals) is worth testing.
- **Don't route big deals to Sonnet yet.** `market.toml` sends deals of £1,000 or more to Sonnet
  5.5. On the same 10 buyers it cost about 13 times as much per deal as Haiku and did no better.
  Ten buyers is too few to decide on, so before rollout: a larger, paired comparison on big deals.

Prompt caching isn't used. The playbooks are short, so the saving is uncertain; measure before
counting on it.

## Rollout

Each step only starts when the one before has run cleanly. Nothing is automatic until step 4.

| Step | Who | What the agent does | What we compare |
|---|---|---|---|
| **1. Replay** | Nobody live | Run Tommy on past Make an Offer bids, with the sellers' real decisions hidden | Would Tommy have accepted what the seller accepted? Countered where they countered? Any secret in any card? |
| **2. Shadow Tommy** | About 10 big sellers | Tommy suggests a reply; the seller sends their own | How often the seller edits Tommy's suggestion, and how |
| **3. Ralph with approval** | About 200 repeat resellers, plus a control group of similar buyers who negotiate by hand | Ralph negotiates; the buyer approves every deal before it's binding | Deals closed, price against list, time to close, disputes: agent group against control |
| **4. Automatic small deals** | The step-3 buyers, then more | Deals under about £1,500 close without a person (the approval threshold already in `market.toml`) | The same, plus how often people override the agent |
| **5. Wider** | Vintage shops, then enterprise buyers | The same agents | The same. Enterprise last: bigger orders and an account manager already in the loop |

**Stop rules.** Any one of these pauses the current step until it's understood:

- **Disputes rise** against the control group.
- **Seller prices fall:** deals close further below list than in the control group. Sellers stop
  listing if the agents give their margin away, and the simulation shows Tommy gives away more
  than Ralph does.
- **People override the agent more than 30% of the time** and it doesn't come down.
- **Any secret leaks.** One is enough. Today the leak scanner checks every line `fleek negotiate`
  prints; in production it would also check every model conversation and every message a person
  reads.

The thresholds for "rise" and "fall" should be set with the sales team before step 3, not by me.

## What it changes for Fleek's team

- **Account managers** get two lists instead of an inbox: deals waiting for approval (with the
  reason), and near misses worth a call (`fleek digest`: negotiations that ended within 10% of a
  deal).
- **Sellers** set a floor once instead of answering every offer. Many won't want to state a floor;
  then estimate it from the offers they've accepted and declined, with a person checking
  (`ASSUMPTIONS.md`).
- **Buyers** set a maximum and a budget once, and see every deal before it's final until step 4.

## How it gets better

1. **Traces.** Every move is already an event, and a run exports as JSON (`fleek export`).
2. **Signals.** Deal or no deal, price against list, disputes, and in shadow mode every edit a
   seller makes to Tommy's suggestion.
3. **Eval cases.** Each bad outcome becomes a case in the simulation, so a fix can be shown to
   help and not break anything else. The safety attacks work the same way.
4. **Fixes, cheapest first:** a note per seller (what they won't go below on what), then tuning
   the playbooks' concession rules, then fine-tuning if it's ever worth it.

Tommy's playbook is the first thing to tune: in every simulated row the buyer side kept most of the
gains (70% to 83%).

## Not built

Postgres, the job queue and workers, the vault as a separate service, batching, the account
managers' tool, sign-in for buyers and sellers, and estimating floors from history. The design
above is how each would fit; none of it is tested here.
