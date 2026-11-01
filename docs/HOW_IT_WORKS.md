# How it works, on one page per question

The brief names three areas: how information flows, how buyers and sellers get matched, and how
this gets in front of real customers. This page answers those, then the questions that follow
from them: does it scale, what are the trade-offs, what do account managers do, how is success
measured, how are the AI models evaluated, and what can you see while it runs. Each answer says
what's **built and tested** here and what's **a plan**.

## What's built, and how to see it

| | Command | What you see |
|---|---|---|
| **The live demo** | `uv run fleek live` | Onboarding (a ready-made market of 4 sellers, 18 lots, 3 buyers), then the buyer's and the seller's screens side by side, and Fleek's column: the matching funnel, the referee, approvals, the watch list, metrics |
| The Deal Room | `uv run fleek room` | One negotiation, step by step, in a 3D scene |
| The deep dive | `uv run fleek leak`, `fleek bench`, `fleek monitors` | Every leak measured, with error bars ([SAFETY_CASE.md](SAFETY_CASE.md)) |
| The market at scale | `uv run fleek simulate` | 500 buyers through matching and negotiation; Claude replayed |
| A person's tools | `fleek approvals`, `fleek digest`, `fleek summary` | What waits for whom, near misses worth a call, a summary per deal |

**A five-minute demo:** `fleek live` → Next, Next → Claude Haiku → Start → Run. Show (1) the
matching funnel in Fleek's column, (2) each side's own secret and private price checks, (3) the
approval: the buyer and an account manager say yes, (4) the metrics. Then pick the Depop buyer:
a different seller wins on rating and dispatch.

## 1. Information flow: who knows what

| Who | Knows | Never knows |
|---|---|---|
| Buyer | their top price, what they want, every card | the seller's floor |
| Seller | their floor, their stock, every card | the buyer's top price |
| Ralph and Tommy (AI) | public facts, the cards, and one word about their **own** limit per turn: strong, acceptable, stretch or outside | any secret number. In blind mode, Ralph doesn't see seller text either |
| The vault (code) | both secrets | nothing it would tell: it answers yes or no, or a band word |
| Matching (code) | the vault's yes or no per lot | the numbers |
| Account manager | the deal, the cards, why it's waiting, the watch list | the secrets (an import rule stops their tools loading the vault) |

- **The agents talk only in cards:** a price and fixed reason codes, no free text. Every card and
  accept is checked against both limits in code before it counts.
- **What can still leak, and what stops it** ([SAFETY_CASE.md](SAFETY_CASE.md)):

| Way out | Measured | Fix | After |
|---|---|---|---|
| Said in words | 0 of over 4,100 calls | the secret never goes in | 0 |
| From Tommy's moves | 62% of floors found within 2% | secret margin | 37%; 99% of deals that work still close |
| | | **firm mode** (seller's choice) | **0**, tested card for card, for about 44 points of deals |
| By probing matching | exact floor in about 12 accounts | match gate, crowd count | 48% within 2%; crowds flagged |
| Pressure in listing text | +2.0% of list | reader / **blind mode** | +0.7% / **0** by construction |

## 2. Matching: the funnel

All plain code, cheapest step first. No AI is called until a lot is picked.

1. **Filters (SQL):** category, brand (if named), accepted grade, in stock, bundle at most twice
   the pieces wanted. Each dropped lot gets its reason (`matching/explain.py`).
2. **"Could any price work?" (the vault):** the lowest price the seller accepts, against what the
   buyer can pay, shipping and fee included. Yes or no only, through the match gate: the buyer's
   top rounded down to a 5% step, 20 answers per lot per day, repeats answered free.
3. **Ranking (public facts only):** fit 50, price 25, seller rating 15, dispatch 10
   (`market.toml [matching]`). Fit is how close the lot's words are to the buyer's, by a local
   embedding model (bge-small; nothing leaves the laptop), compared across the candidates.
4. **Quantity:** the bundles closest to the pieces wanted.

Ralph negotiates the top lot. If it fails (walked away, expired, or a person said no), he moves
to the next. In the live demo the funnel is shown lot by lot, with the score broken down.

**Why ranking can't read a secret:** the order would then tell a buyer something about floors.
The vault has already said which lots could work; ranking only sorts them.

## 3. Getting it to real customers

Five steps, each starting only when the last ran cleanly ([SCALE_AND_ROLLOUT.md](SCALE_AND_ROLLOUT.md)):

| Step | Who | The agent | Compared on |
|---|---|---|---|
| 1. Replay | nobody live | Tommy on past Make an Offer bids, real decisions hidden | would he have done what the seller did? any leak? |
| 2. Shadow Tommy | ~10 big sellers | suggests; the seller sends their own | how often and how they edit |
| 3. Ralph with approval | ~200 repeat resellers + a control group | negotiates; the buyer approves each deal | deals, price vs list, time to close, disputes |
| 4. Automatic small deals | the same buyers | deals under £1,500 close on their own | the same, plus overrides |
| 5. Wider | vintage shops, then enterprise | the same | the same |

**Stop rules:** disputes rise; seller prices fall; people override the agent over 30% of the
time; or any secret leaks (one is enough). Who it's for first: repeat resellers on Make an Offer,
because Fleek already has their bids to replay and they buy often.

## 4. Does it scale?

The rules don't change at 50,000 buyers and 1,000 sellers; where things run does.

| | Here (tested) | At full scale (plan) |
|---|---|---|
| Data | SQLite, one writer | Postgres, same tables; append-only as a database permission |
| Turns | one process | a job queue; any worker can take any turn (each turn is rebuilt from the event log) |
| Races | one writer | a per-buyer lock around opening and buyer moves |
| Vault | a package agents can't import | its own service; agent workers have no route to it |
| Matching | 500 buyers ranked in 46 ms (measured) | ~30,000 lots: ~2 ms a buyer; rank when stock or a want changes, not every turn |
| Model calls | ~18 per negotiation, 0.5¢ with Haiku (measured) | 100,000 negotiations a week ≈ 1.8M calls ≈ 3 a second on average, ≈ $520 a week |

Turns have a 48-hour clock, so a queue that waits seconds costs nothing. Rate limits, retries
with backoff and batching are the engineering; none of the scale-out is built here.

## 5. Trade-offs: the ones made now, and the ones scaling brings

**Made now, on purpose**

| Chose | Over | Because | Cost |
|---|---|---|---|
| Secrets in code, AI sees band words | the AI holding the limits | an AI can be talked into anything; code can't | agents negotiate with less information |
| Secret margin (8%) as default | firm price | Fleek earns 15% of delivered orders; haggling closes 100% of deals that work, firm 56% | 37% of floors still guessable within 2%; 1 deal in 168 lost to the hidden floor |
| Match gate | open matching | open matching gave floors away exactly | 5% of real matches lost |
| Blind mode in the demo | Ralph reading listings | zero text manipulation | Ralph can't use sizes or defects from text |
| People for decisions that matter | people on every deal | deals expire waiting, and earn nothing | a judgement call on thresholds |
| Haiku | Sonnet | same results on 10 buyers, 1/13 the cost | small sample |
| One lot at a time, next if it fails | many lots in parallel | simple to follow and to approve | slower for the buyer |
| Hand-set ranking weights | learned weights | no outcome data yet | the weights are a guess |
| SQLite, one process | a distributed system | the point is the rules, not the plumbing | not tested under real load |

**What scaling changes**

- **More buyers asking about the same lots** makes the match gate's budget bite: it must be sized
  per lot popularity, or real buyers get refused. Measured already: 5 a day refused half the
  matches on the seeded market.
- **Fake accounts** get cheaper to make than to detect. The crowd count is easy to dodge; real
  defence is sign-up checks (Fleek's buyers are businesses) and pricing questions per account.
- **Approvals pile up:** "first 3 deals by a person" is up to 150,000 approvals if everyone joins
  at once. Roll out in steps; let trust rules relax with each buyer's history.
- **Cost against speed:** batch the turns that can wait; keep the best model for big deals only
  once a bigger comparison justifies it.
- **Ranking weights** should be learned from which matches close and repeat, then checked so
  they never take a secret as input.
- **Model drift:** recordings show what a model did once. At scale, re-run the bench on every
  model change before switching.

## 6. What the account managers do

They're the people in the loop, and the agents give them a short list instead of an inbox:

- **Approve decisions that matter:** big deals, a buyer's first deals, flagged buyers, unusual
  prices. Each comes with a summary: what happened, where it stands, what to do.
- **Call near misses** (`fleek digest`): failed negotiations that ended within 10%, biggest
  first. A small nudge often closes them.
- **Watch list:** buyers who probe, come back, or crowd a lot with new accounts.
- **Take over** when a buyer or seller hands a deal over, or an agent is stopped by the vault.
- **Set the numbers:** approval thresholds, margins, budgets, with the sales team, in
  `market.toml`.

For Fleek's GTM team this turns account management from answering every offer into handling
exceptions, and gives the account manager a measured book: deals closed, by whom, and why.

## 7. How success and efficiency are measured

| Kind | Metric | Where it's measured today |
|---|---|---|
| Business | deal rate (of deals that were possible), Fleek's commission per negotiation, price vs list, time to close, repeat buying, disputes | `fleek bench`, `fleek simulate`, `fleek leak --firm`; disputes and repeats need real data |
| Fairness | each side's share of the gains between the two limits | `fleek bench` (buyer share), `fleek simulate` |
| People | approvals per deal, overrides, account-manager touches per deal | the approvals table; overrides need real use |
| Safety | secrets in model text, deals outside a limit, vault stops, leak rate from moves and matching | every bench suite, with error bars and pass marks set before measuring |
| Cost and speed | model calls, tokens, cents per deal, agent time, simulated hours | the live demo's metrics panel, `fleek simulate` |

The north-star number for Fleek is **commission per negotiation**: deals closed times price, net of
what it costs to run. The stop rules guard trust: disputes, seller prices, overrides, leaks.

## 8. How the AI models are evaluated

- **A bench of generated deals** where the evaluator knows both limits and the agents don't
  (`bench/`). Scored: deal rate, buyer share, secrets in text (canaries), deals outside a limit,
  each with 95% intervals.
- **Attack suites:** attackers that know the code read Tommy's moves; fake accounts probe
  matching; six pressure tactics with paired controls; an adaptive red team.
- **Model comparisons:** scripted, Haiku 5.5 and Sonnet 5.5 on the same buyers
  ([EVALS.md](EVALS.md)).
- **The checker checked:** the listing reader's warnings scored on Haiku and Sonnet, with false
  alarms on clean listings.
- **Replays in CI:** every recorded Claude run replays with no key; a change that alters what the
  model would be sent fails the tests.

**Not yet:** large Claude samples (100 lots for moves, 5 red-team deals), several model families, human ratings of
negotiation quality, and live monitoring of model drift.

## 9. Observability: what you can see while it runs

| Built | What it gives |
|---|---|
| Append-only event log | every move, by whom, when, and why a person was asked; replaying it gives the saved state |
| Approvals table | who was asked to approve, why, and when each said yes |
| Spend ledger and caps | every model call charged; a call that could break a cap is never made |
| Metrics panel (live demo) | per agent turn: model, time, calls, tokens, cost; totals per session |
| Trace download | `/api/trace` (live) and `fleek export`: everything public about a run, as JSON, no secret |
| Leak scanner | every line `fleek negotiate` prints is checked for numbers near a secret |
| Account managers' lists | approvals, near misses, the watch list, a summary per deal |

**At scale (plan):** ship the same events to a log store, turn the metrics into dashboards and
alerts on the stop rules (a leak, a rise in disputes, override rate, cost per deal), and trace
each model call with OpenTelemetry. None of that is built here.
