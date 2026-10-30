# 001. The secret limits never enter the model

**Status:** accepted, 30 Oct 2026
**Built in:** #15 (SecretMoney), #16 and #18 (bands, yes/no checks), #19 (property tests), #20 (import rule)

## Context

Ralph negotiates for a buyer with a private maximum. Tommy negotiates for a seller with a private
floor. If either number reaches the other side, the negotiation is over: every deal ends at the
leaked limit. The brief puts "who knows what, and what stays private" at the centre of the design.

The agents need *some* sense of their limit to negotiate well. The question is where the number
lives.

## Options

| | Option | Problem |
|---|---|---|
| A | Put the limit in the agent's prompt and tell it never to reveal it | The instruction is the only defence. A planted instruction in a listing, a long conversation, or a plain mistake can get past it. |
| B | As A, plus a filter that scans the agent's output for the number | Better, but the number is still in the context. A filter catches the exact digits, not a hint ("I can go a little above twelve"). |
| C | **Keep the limit in code. The agent asks code questions and gets coarse answers back** | The agent negotiates with less information. Chosen. |

## Decision

Option C. The buyer's max and the seller's floor are held by the vault as `SecretMoney`. The agents
and the AI client can't import the vault. What an agent gets instead:
- **a band** for a price it's considering: strong, acceptable, stretch or outside (one check per
  round, from a later PR);
- **yes/no** from code before any accept: is this price inside both limits?

Matching uses another yes/no, "is any deal possible?", to skip pairs that can never close, before
any AI is called.

The rule from the plan: **the AI decides what to offer; code decides what's allowed.**

## Why not trust the instruction

- Research on LLM negotiators lists, among their common failures, that agents "explicitly leak
  private price limits" (Liu et al., 2026, *Instructing LLMs to Negotiate using Reinforcement
  Learning with Verifiable Rewards*, [arXiv:2604.09855](https://arxiv.org/abs/2604.09855),
  Introduction). The paper doesn't give a rate for this, so this record doesn't claim one.
- OWASP's Top 10 for LLM applications (2025) covers this as
  [LLM07: System Prompt Leakage](https://genai.owasp.org/llmrisk/llm072025-system-prompt-leakage/).
  It says sensitive data shouldn't be in the system prompt, and that critical controls should sit
  outside the model: "Implement a system of guardrails outside of the LLM itself."
- If the number isn't in the context, there is nothing in the context to leak.

## How it's enforced

| Layer | What it stops | PR |
|---|---|---|
| `SecretMoney` | Printing, logging, JSON, copying, comparing, or putting a secret in any Pydantic model (every AI tool input and output is one) | #15 |
| Import rule (import-linter, in CI) | Agent or AI-client code importing the vault, directly or through another module | #20 |
| Bands and yes/no checks | Anything but four words or True/False leaving the vault | #16, #18 |
| Property tests | An accepted price outside a limit, for 10,000 generated cases per rule | #19 |
| Not built yet | A leak scanner on every line a person reads; one band check per round | later PRs |

## Consequences

- **The agents know less.** They can't compute "my exact headroom". The bands give enough to
  negotiate sensibly; the simulation (later) will show whether deals suffer.
- **Bands give away a little, on purpose.** "Stretch" tells the agent it's close. One check per
  round and four coarse bands stop it from homing in on the number. A rival could still try to
  infer a limit from how an agent concedes over time; binding offers, one-way concessions and a
  cooldown (later PRs) make that probing expensive.
- **More code than option A.** That code is the part Fleek's engineers can test, which a prompt
  instruction isn't.

## What would change this decision

- If the simulation shows agents with bands close far fewer good deals than agents that know the
  number, revisit how fine the bands are, not where the number lives.
- If Fleek wants buyers to see their own limit in a chat with Ralph, that's the buyer's own number
  shown to the buyer: a separate path that never goes through the negotiating agent's context.
