"""Ralph and Tommy as Claude agents: the same Agent interface as the scripted ones.

Each turn is a fresh conversation: the playbook prompt, a short summary of where the negotiation
stands, the tools for this side, then exactly one action. When the turn can't produce a valid
action, the agent hands the negotiation to a person with the reason. The prompt never contains a
number from the vault, because the agent never has one.
"""

from pathlib import Path

from fleek_agents.agents.base import Action, HandOff, View
from fleek_agents.harness.escalation import REASONS
from fleek_agents.harness.loop import Outcome, TurnResult, take_turn
from fleek_agents.harness.tools import to_action, tools_for
from fleek_agents.llm.client import LLMClient

PROMPTS = Path(__file__).parent / "prompts"


def turn_prompt(view: View) -> str:
    side = "buyer" if view.want is not None else "seller"
    lines = [f"It's your turn. You act for the {side}. Cards left: {view.rounds_left}."]
    card = view.on_table
    if card is None:
        lines.append("No card has been sent yet: make the opening offer.")
    else:
        other = "seller's counter" if card.from_role == "seller" else "buyer's offer"
        price = card.base_price.value
        lines.append(f"On the table: the {other} of {price} pence per piece, round {card.round}.")
    if view.want is not None:
        lines.append(f"The buyer asked for: {view.want.text}")
    return "\n".join(lines)


class ClaudeAgent:
    def __init__(
        self, client: LLMClient, *, model: str, prompt: str, effort: str = "medium"
    ) -> None:
        self._client, self._model, self._effort = client, model, effort
        self.model = model
        self._system = (PROMPTS / f"{prompt}.md").read_text(encoding="utf-8")
        self.turns: list[TurnResult] = []  # for cost and behaviour reports

    def decide(self, view: View) -> Action:
        turn = take_turn(
            self._client,
            model=self._model,
            system=self._system,
            prompt=turn_prompt(view),
            tools=tools_for(view),
            effort=self._effort,
        )
        self.turns.append(turn)
        if turn.outcome is Outcome.ACTION and turn.action is not None:
            name, parsed = turn.action
            return to_action(name, parsed, view)
        return HandOff(reason=REASONS[turn.outcome])
