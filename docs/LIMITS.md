# Limits and evidence

What this repo claims, where the evidence is, and what it doesn't show. If a claim isn't in the
first table, I don't make it.

## Claims and their evidence

Every test below runs in CI on every PR, with no API key (Claude runs are replayed from
recordings).

| Claim | Evidence |
|---|---|
| The agents' code can't import the secret limits | Three import-linter contracts in `pyproject.toml`, run by `make check`; [#20](https://github.com/code-mohanprakash/ralph-and-tommy/pull/20) shows the rule catching a real slip |
| A secret prints as `***` and refuses to become JSON, be pickled, be compared or sit in a Pydantic model | [`tests/test_secret.py`](../tests/test_secret.py) |
| Agents can't send each other text | A card has no free-text field and refuses extra ones: [`tests/test_offers.py`](../tests/test_offers.py) (`test_no_field_on_the_card_can_hold_free_text`, `test_a_card_with_a_message_field_is_refused`); `fleek safety` row "all four text attacks" |
| Only the moves Make an Offer allows can happen, by the right side | Every move from every state by every actor: [`tests/test_state.py`](../tests/test_state.py) |
| An accepted price is never outside either side's limit | Random cases: [`tests/test_properties.py`](../tests/test_properties.py); scripted and Claude deals: [`tests/test_scripted.py`](../tests/test_scripted.py), [`tests/test_claude_agent.py`](../tests/test_claude_agent.py); every deal in the scripted simulation and in both recorded Claude simulations: [`tests/test_sim.py`](../tests/test_sim.py) |
| No card past its sender's own limit is sent | `test_a_card_past_its_sender_s_own_limit_is_never_sent` in [`tests/test_scripted.py`](../tests/test_scripted.py); the probing-bot row of `fleek safety` (Claude Tommy tried; the harness refused) |
| Concessions only go one way; at most 6 cards; 48 hours to answer | [`tests/test_rounds.py`](../tests/test_rounds.py) |
| One price check per turn, answered with a band word only | [`tests/test_agent_tools.py`](../tests/test_agent_tools.py) |
| A buyer can't end up with two deals their budget only covers once | [`tests/test_budget_across_deals.py`](../tests/test_budget_across_deals.py) |
| A probing bot is stopped (binding offers, cooldown, one check per turn) | [`tests/test_probing.py`](../tests/test_probing.py) |
| When ten buyers accept at once, exactly one gets the lot; stock is never oversold | [`tests/test_deals.py`](../tests/test_deals.py), [`tests/test_properties.py`](../tests/test_properties.py) |
| The event log can't be edited or deleted, and replaying it gives the saved state | [`tests/test_events.py`](../tests/test_events.py), including 300 random negotiations |
| A model call that could break a spend cap is never made | [`tests/test_budget.py`](../tests/test_budget.py) |
| Refusals, repeated bad output and the spend cap go to a person, with the reason | [`tests/test_escalation.py`](../tests/test_escalation.py), [`tests/test_budget.py`](../tests/test_budget.py) |
| Every line `fleek negotiate` prints passes the leak scanner | [`tests/test_cli.py`](../tests/test_cli.py), [`tests/test_scanner.py`](../tests/test_scanner.py) |
| An exported run holds no amount at or near a secret limit (floor, max or budget), as a number or inside text | [`tests/test_export.py`](../tests/test_export.py), with planted secrets the check must find |
| The Deal Room's steps hold no secret limit; the limits are only in a separate audience block the page shows on request | [`tests/test_room.py`](../tests/test_room.py) (`test_the_steps_never_hold_a_secret_limit`, and for every Claude replay), with planted secrets the check must find |
| What account managers read can't show a secret limit | A fourth import-linter contract: `humans` never imports the vault; [`tests/test_handover.py`](../tests/test_handover.py) |
| A person is told what happened and what to do whenever one is needed | [`tests/test_handover.py`](../tests/test_handover.py) (approval, a stopped agent on either side, near miss) |
| The Deal Room loads nothing from the internet | `test_the_page_loads_everything_from_this_computer` in [`tests/test_room.py`](../tests/test_room.py) |
| Editing `market.toml` changes what the commands do | [`tests/test_cli.py`](../tests/test_cli.py), [`tests/test_config.py`](../tests/test_config.py) |
| Fees match an independent calculation to the penny | [`tests/test_properties.py`](../tests/test_properties.py) |
| The results in EVALS.md come from the recordings in the repo | [`tests/test_sim.py`](../tests/test_sim.py) replays both Claude runs and checks the same results |
| No secret limit appears in any recorded Claude request or response (over 4,100 calls) | Canary searches over every tapped call: [`tests/test_bench_moves.py`](../tests/test_bench_moves.py), [`tests/test_bench_tactics.py`](../tests/test_bench_tactics.py), [`tests/test_redteam.py`](../tests/test_redteam.py), each with a planted-canary check in [`tests/test_bench.py`](../tests/test_bench.py) |
| No recorded Claude negotiation on the bench ends outside a limit (0 of 510, 95% upper bound 0.59%) | The same three test files |
| Attackers that know the code get within 2% of Tommy's floor on 62% of lots; an 8% secret margin cuts that to 37% for 4 points of deals | [`tests/test_bench_moves.py`](../tests/test_bench_moves.py), [`tests/test_privacy.py`](../tests/test_privacy.py); `fleek leak --sweep` redraws the chart |
| With the privacy layer on, no counter goes below the floor Tommy works to, and no deal breaks a real limit | [`tests/test_privacy.py`](../tests/test_privacy.py) (100 lots, both Tommy styles) |
| The match gate never gives a false yes, and its budget is per lot, not per account | [`tests/test_gate.py`](../tests/test_gate.py), [`tests/test_funnel.py`](../tests/test_funnel.py) |
| Behind the listing reader, none of the seller's words reach Ralph | Text by text over every recorded run: [`tests/test_bench_tactics.py`](../tests/test_bench_tactics.py), [`tests/test_redteam.py`](../tests/test_redteam.py); a spy on both sides in [`tests/test_reader.py`](../tests/test_reader.py) |
| Probing and returning buyers reach the account managers' watch list from the event log | [`tests/test_monitors.py`](../tests/test_monitors.py), scored in [`tests/test_bench_monitoring.py`](../tests/test_bench_monitoring.py) |
| In firm mode, a different floor changes nothing the buyer sees: not a card, not matching's answer, not a byte of what Claude is sent | [`tests/test_firm.py`](../tests/test_firm.py), with a haggle-mode control that does change |
| In blind mode, two listings that differ only in their words give Ralph byte-identical requests | [`tests/test_reader.py`](../tests/test_reader.py), with a control that differs |
| Who must approve a deal can't depend on a secret limit | A fifth import-linter contract: `orchestrator/approval.py` never imports the vault; [`tests/test_approval.py`](../tests/test_approval.py) |
| Everyone asked must approve; any one can reject; a person can stop or hand over at any point before agreement | [`tests/test_approval.py`](../tests/test_approval.py), [`tests/test_controls.py`](../tests/test_controls.py) |
| A buyer gets 3 failed tries per lot; a limit can't change while a negotiation on it is going | [`tests/test_probing.py`](../tests/test_probing.py), [`tests/test_limits.py`](../tests/test_limits.py) |
| The seller's offer to buyers who walked away is checked against the floor when it's set, and kept by code | [`tests/test_offers.py`](../tests/test_offers.py) |
| The live demo shows each side only its own secret; a secret typed into a box an agent reads is refused | [`tests/test_live.py`](../tests/test_live.py), including a replay of the recorded Claude run searched for both secrets |
| Every number in SAFETY_CASE.md comes from the recordings in the repo | The replay tests above check the recorded numbers exactly |

## What this doesn't show

**About the market**

- **The market is made up.** 500 buyers, 50 sellers and 1,494 lots, generated from a seed. Shapes
  come from Fleek's public pages and a 44-listing sample ([ASSUMPTIONS.md](ASSUMPTIONS.md)); prices
  and limits are invented. Real buyers and sellers would behave differently.
- **Sellers are assumed to state a floor.** Many won't. Estimating it from past offers isn't built.
- **No real buyer or seller has used it.**

**About the results**

- **Samples, not benchmarks.** Claude Haiku 5.5 on 30 buyers and Claude Sonnet 5.5 on 10, one
  recorded run each. A different day could give different numbers.
- **Replays show the code handles those answers, not that the model would give them today.** The
  3 live tests are skipped in CI.
- **Matching quality isn't measured.** One known case is tested (decision 002); the simulation
  measures deals, not whether each buyer got the best lot for them.
- **"Inside both limits" isn't the same as "a good deal".** The harness keeps every deal inside
  the limits. Within them, the agent can still negotiate badly. The simulation measures how well;
  the code doesn't enforce it.

**About safety**

- **The Deal Room's market is three warehouses, fixed for the demo.** Its scenario labels say
  how the scripted agents end each one; Claude's endings are its own (on the near-miss numbers,
  Claude Tommy tried a counter below his floor instead).
- **The attacks are the strongest published ones I could build, not every possible one.**
  `fleek safety`'s four text attacks are one recorded run each. The deep dive's bench adds
  attackers that know the code, many lots, and an attacker that adapts, but a human red team
  would still find others ([SAFETY_CASE.md](SAFETY_CASE.md), section 6).
- **Every protection is on in `fleek live`, but not in the older commands.** The Deal Room,
  `fleek simulate`, `fleek negotiate` and `fleek safety` run without the margin, the gate and
  blind mode: their recordings were made before these existed (a replay only answers the exact
  requests it saw), and the Deal Room's stories are tuned to exact numbers. The bench keeps an
  "off" to measure each layer against.
- **The live demo replays Claude only for the ready-made example.** Anything else typed in needs
  the scripted agents, or `--live` and a key.
- **Firm mode's cost is measured on generated lots, with one firm-price rule for every lot.** Real
  sellers would pick their own firm prices; how many deals it costs on real floors is unknown.
- **The crowd count is easy to dodge** by having each fake account also ask about other lots.
- **The leak scanner catches numbers, not words.** "1600p", "£16" and "16.00" are caught;
  "sixteen pounds" is not.
- **Matching's yes/no can map a floor, and the gate only blurs it.** With many accounts, open
  matching gave a floor away to the penny in about 12 questions. Through the match gate, 12
  accounts still land within 2% on 48% of lots: the pass mark I set (more than 100 accounts) was
  missed. A 10% grid halves that, for more lost matches.
- **Every haggle reveals something about a limit.** Measured: an attacker who knows the code
  gets within 2% of Tommy's floor on 62% of lots. A secret margin of M% caps that at about 4/M
  and costs deals: 4 points on the bench, about 10% of real matches on the seeded market. Firm
  mode reveals nothing and costs about 40 points of deals. Which to use is a business choice,
  best made on Fleek's own past deals.

**About running it for real**

- **One process and SQLite.** Concurrency is tested with threads (10 at once), not with many
  machines. [SCALE_AND_ROLLOUT.md](SCALE_AND_ROLLOUT.md) says what changes.
- **No sign-in.** Anyone who can run `fleek approve` can approve a deal.
- **Two settings in `market.toml` aren't backed by evidence yet.** Deals of £1,000 or more go to
  Sonnet 5.5, though Sonnet did no better than Haiku on the 10 buyers measured; and a digest model
  is named, but the digest is plain code and calls no model.
- **Payments, shipping, disputes and returns** are Fleek's existing systems and aren't modelled.

## Words I don't use about this

Production-ready, secure, guaranteed, unhackable, proves, fully autonomous. The table above says
what's enforced and where it's tested; that is the claim.
