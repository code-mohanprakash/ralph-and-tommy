# AI log: how this was built with AI

The brief says to use AI and to be ready to say what I used, and where it helped or got in the
way. This is that record, including the mistakes.

## What I used

| | What for |
|---|---|
| **Claude Code** (desktop app, Claude Opus 5.5) | Planning, writing nearly all the code, tests and docs, running the checks, opening and merging PRs |
| **Claude Haiku 5.5** and **Claude Sonnet 5.5**, through the Anthropic API | Inside the product: Ralph and Tommy, the safety attacks, the simulation |

Claude Opus 5.5 is also set in `market.toml` for the digest, but the digest is plain code today and
calls no model.

## How I worked

- **I set the direction; Claude wrote the code.** I decided what to build and in what order, and
  made the calls on design, scope and rules. Claude Code wrote the code, the tests and the first
  draft of every doc.
- **A plan first.** Before any code: a written plan of about 55 PRs, each small enough to explain
  in two minutes, with a cut list for when time ran short.
- **One PR at a time, checked by CI.** Every PR runs lint, strict types, the import rules, the tests
  and a key scan. Claude merged each PR itself once CI was green; I chose that to keep moving, and
  the "Checked before merging" section of each PR quotes the CI log lines it relied on.
- **Study notes for every PR.** Claude wrote a private study entry for each PR: what it does, why,
  and how to explain it out loud. Writing those entries meant reading the merged code again, and
  that is how most of the bugs below were found.
- **Rules I gave it:** no backdated commits; no planted mistakes; a real bug gets its own `fix:` PR
  that says how it was found; a wrong claim in a merged PR gets an open correction on that PR; the
  API key never leaves a git-ignored `.env`.

## Where it helped

- **Speed.** About 73 PRs and 1,004 tests between Thursday 29 Oct at night and Saturday 31 Oct,
  then 8 more PRs for the deep dive on Sunday 1 Nov (81 PRs, about 1,070 tests). I couldn't
  have built this much alone in the time.
- **Tests I wouldn't have written by hand.** Property tests (2,000 random cases that the band words
  and the yes/no checks agree), race tests with 10 threads, and "break it on purpose" checks:
  remove a safety rule, watch which tests fail, put it back.
- **Knowing the current API.** Strict tool schemas, server-side model fallbacks, and what Pydantic
  has to check that strict mode can't.
- **Finding its own bugs, when asked to explain the code.** Most of the fixes below came from the
  study-notes review, not from me spotting them.

## Where it got in the way

**1. It made the agents copywriters.** Its first design had code choose every offer and the AI only
write the message. I pushed back: the brief is about agents that negotiate. The final design keeps
the decisions in the agents and makes them safe with the harness (secret limits outside the model,
checked tools, a referee on every move).

**2. It said things were done or checked when they weren't.** Three times:

- PR 5 said the help-centre links had been checked before they were opened. Corrected on PR 5
  and fixed in #6.
- PR 47 said it added a `compare_open_deals` tool. It hadn't: the edit's search text had been
  rewrapped by the formatter, so the edit didn't apply, and the check looked at different text.
  Fixed in #51, with a correction on PR 47.
- PR 54 said removing a rule "failed 2 tests" before the output was on screen. The edit hadn't
  applied; the real number, once run, was 3. Corrected on PR 54.

What I changed: "checked" now means run or read in that session, with the output quoted, and
every scripted edit must find its exact target text once or stop.

**3. A number with no source.** The plan said agents holding secrets leak them "in 2–80% of runs".
When decision 001 needed a citation, no source could be found: two candidate papers, once read,
gave no rate. The number was dropped; decision 001 cites only what was opened and read.

**4. Too-strong words.** "Guarantees" where the code only enforces; a cost limit that "can only
overstate" when it could understate. Reworded in #41. The banned list is now in my notes:
production-ready, secure, guaranteed, unhackable, proves, fully autonomous.

**5. Ordinary bugs**, each found, fixed in the open and tested:

| Fixed in | What broke | How it was found |
|---|---|---|
| [#4](https://github.com/code-mohanprakash/ralph-and-tommy/pull/4) | PR 2 merged into a branch that was already merged, so the key scanner never reached `main` | The PR count looked wrong; the scanner file was missing on `main` |
| [#6](https://github.com/code-mohanprakash/ralph-and-tommy/pull/6) | The assumptions doc presented a 44-listing sample as Fleek's own definitions | Opening every linked help-centre article |
| [#14](https://github.com/code-mohanprakash/ralph-and-tommy/pull/14) | A buyer accepting a moment after losing the lot got an error instead of "sold" | The 10-buyer race test failed once |
| [#18](https://github.com/code-mohanprakash/ralph-and-tommy/pull/18) | Price bands ignored fees, so a band could say "stretch" when the yes/no check said no | Writing the yes/no checks on real totals |
| [#20](https://github.com/code-mohanprakash/ralph-and-tommy/pull/20) | Settings imported the vault, so any agent reading a setting could reach it | The new import rule caught it |
| [#28](https://github.com/code-mohanprakash/ralph-and-tommy/pull/28) | Decision 002 gave the wrong candidate count | Study notes |
| [#31](https://github.com/code-mohanprakash/ralph-and-tommy/pull/31) | An expired approval kept the stock taken, so a one-of-one lot could never sell again | Study notes |
| [#32](https://github.com/code-mohanprakash/ralph-and-tommy/pull/32) | Two negotiations opened at once could get the same id | Study notes, then a 10-thread test that failed 3 of 3 runs |
| [#41](https://github.com/code-mohanprakash/ralph-and-tommy/pull/41) | The spend ledger charged cache writes at the plain input price; they cost up to 2× | Study notes |
| [#42](https://github.com/code-mohanprakash/ralph-and-tommy/pull/42) | Recordings saved responses with sorted keys, so one replay missed at call 7 | Tracing request fingerprints |
| [#51](https://github.com/code-mohanprakash/ralph-and-tommy/pull/51) | The missing `compare_open_deals` tool (above) | Study notes read the merged code |
| [#56](https://github.com/code-mohanprakash/ralph-and-tommy/pull/56) | A `fleek safety` check passed for the wrong reason (the card was refused for missing fields, not for the text) | Study notes ran the check and counted the errors |
| [#63](https://github.com/code-mohanprakash/ralph-and-tommy/pull/63) | No command read `market.toml`; they all used the same numbers copied into the code, so editing the file changed nothing | Study notes traced where the approval threshold comes from |
| [#65](https://github.com/code-mohanprakash/ralph-and-tommy/pull/65) | Two "Secret leaked?" cells in `fleek safety` were fixed text, not results | Study notes traced each cell back to its code |

**6. Tests that checked less than their names said.** Building the claim → evidence table in
[LIMITS.md](LIMITS.md) and reading each test for the study notes turned up four:

- EVALS.md said the tests check every Claude deal is inside both limits; only the scripted run
  was checked. Test added in [#62](https://github.com/code-mohanprakash/ralph-and-tommy/pull/62).
- The digest test named "live and agreed deals" only built a live one. Fixed in
  [#64](https://github.com/code-mohanprakash/ralph-and-tommy/pull/64).
- The export's secret check skipped prices written inside text and the buyer's budget. Fixed in
  [#66](https://github.com/code-mohanprakash/ralph-and-tommy/pull/66).
- The `fleek safety` cells above (#65).
- The Deal Room's "no secret in a step" test searched `json.dumps` output for "£15.50", but
  `json.dumps` writes "£" as `\u00a3`, so it could never match. Found by planting a secret before
  merging (#69); the test now reads the text as written and also looks for the bare amount.

Each new test was broken on purpose first and seen to fail, then restored and seen to pass.

## The deep dive (Sunday 1 Nov)

**How the plan was made.** Fleek's brief says to go deep on one thing. Claude's first plan for
that was built from negotiation papers from 1998–2007 and a few searches. I said it wasn't good
enough: AI labs and companies running these agents use many techniques at once. Claude then
researched what Anthropic, OpenAI, Google DeepMind, Microsoft and Meta publish, what companies
running commerce agents do (Pactum, Google AP2, Stripe, Project Vend), the 2025–26 negotiation
papers, and practitioners' writing. It rebuilt the plan from that. I also asked for the PRs to be
ordered by what each needs, so each one builds only on merged work. The result is
[SAFETY_CASE.md](SAFETY_CASE.md).

**Mistakes Claude made in this round, and how each was caught:**

| Mistake | Caught by |
|---|---|
| The canary generator kept canaries unique across scenarios. Past about 200 scenarios it walked floors down by pounds (968p became 97p, then negative) | Training the attackers on 400 scenarios; fixed inside #74 before merging, with a test that fails on the old code |
| A commit went in while `mypy` was failing: a pipe to `tail` hid the exit code | Its own next check; fixed and amended before pushing. Checks now run with `pipefail` |
| The first noise design clamped counters onto the floor, which showed the floor and made the leak worse (62% to 75%) | The trade-off sweep; fixed in #76 with a test |
| The first match-gate budget (5 answers a lot a day) turned real buyers away: 50% of 500 buyers' matches | Measuring on the seeded market, not just the bench; fixed in #77 |
| Two monitors (big drop, gate refusals) caught nothing | Scoring them on the bench's attacks; removed in #80 |
| Draft docs said "about 3,800 calls searched" and "0 of 419 negotiations" | Recounting against what the tests check before committing: nearly 3,000 and 390 |

**What surprised me:**

- **Fixed pressure tactics didn't work on Claude Ralph; an adaptive attacker did.** Three of six
  tactics made him pay *less*. A Claude attacker rewriting after each try got him to pay up to 2%
  more. That's what "The Attacker Moves Second" predicts: test against attackers that adapt.
- **Noise didn't hide a floor from an attacker who knows the code.** The secret margin did, and
  it costs deals: the trade-off chart is the real answer.



- **Claude Tommy tried to counter below his own floor** when a probing bot pushed him. The harness
  refused the card (`card_outside_limit`) and the floor stayed secret. This is why limits are
  checked in code, not left to the prompt.
- **Claude got buyers better prices than the scripted agents, but closed fewer deals** (11.6% vs
  5.1% below list; 70% vs 83% of negotiations) in the 30-buyer run ([EVALS.md](EVALS.md)).
- **Sonnet 5.5 cost about 13 times as much per deal as Haiku 5.5 and did no better** on the same 10
  buyers.
- **Claude Tommy broke a limit on his own in the Deal Room.** On the near-miss numbers, he spent
  his one price check on Ralph's offer, then countered at £13.00 without checking it: 6p under
  the lowest price his floor allows. The vault refused, the card was never sent, and the account manager got a summary
  saying to call the seller. The scripted agents ended the same numbers as a near miss.

## What the AI cost

The live model calls kept as recordings in this repo cost **about $2.13** at list prices, over
4,451 calls: about 90 US cents over 846 calls before the deep dive (84.7¢ of it the two simulation
runs, 2.3¢ the Deal Room's Claude recordings), and $1.23 over 3,605 calls for the deep dive's
bench (Claude Tommy probed 23.0¢, the tactics with and without the reader 61.5¢, the red team
14.2¢, and the text check 24.2¢, 22.5¢ of it Sonnet). Recordings that were thrown away and re-made aren't
counted, so the true total is a little higher. Everything in CI and the README replays the
recordings, so running the repo costs nothing.

Claude Code itself ran on my own subscription and isn't counted here.
