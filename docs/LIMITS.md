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
| Editing `market.toml` changes what the commands do | [`tests/test_cli.py`](../tests/test_cli.py), [`tests/test_config.py`](../tests/test_config.py) |
| Fees match an independent calculation to the penny | [`tests/test_properties.py`](../tests/test_properties.py) |
| The results in EVALS.md come from the recordings in the repo | [`tests/test_sim.py`](../tests/test_sim.py) replays both Claude runs and checks the same results |

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

- **The attacks are the ones I thought of.** One recorded run each, on one model. A red team would
  find others. `fleek safety` says so on its last line.
- **Untrusted text still reaches the model.** Listing titles go to Claude Ralph, and the
  planted-listing attack shows text telling him to offer £25. He didn't, and the harness would
  have refused a card past his limit anyway. Text can't move a limit; it could still steer a
  choice inside one.
- **The leak scanner catches numbers, not words.** "1600p", "£16" and "16.00" are caught;
  "sixteen pounds" is not.
- **Matching itself answers a yes/no question about two secrets.** A lot only shows up if some
  price works for both sides. If a buyer could change their maximum freely, they could watch lots
  appear and disappear and narrow down a seller's floor. Today a buyer can't change their maximum
  at all. At scale: limit how often it can change, and count it like a price check.
- **The other side can still read the cards.** How someone concedes says something about their
  limit, as in any negotiation. The system stops secrets leaking; it can't stop inference from
  public moves.

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
