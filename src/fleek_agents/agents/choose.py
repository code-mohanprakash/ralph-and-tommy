"""Upgrade 1: Ralph picks which 3 of the top 10 lots to negotiate. AI judgement, checked by code.

The choice tool's schema only allows lot ids from this shortlist (the API enforces that), and
code checks there are exactly 3 and all different; anything else is a correction. With 3 or
fewer candidates there's nothing to choose, so no model is called.
"""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import Field, StrictStr, create_model, model_validator

from fleek_agents.domain.models import DomainModel, Seller, Want
from fleek_agents.domain.rules import Candidate
from fleek_agents.harness.loop import Outcome, Tool, TurnResult, take_turn
from fleek_agents.llm.client import LLMClient

PICK = 3
SYSTEM = (Path(__file__).parent / "prompts" / "ralph_choose.md").read_text(encoding="utf-8")


class _Choice(DomainModel):
    lot_ids: tuple[str, ...]
    why: Annotated[StrictStr, Field(max_length=300)]

    @model_validator(mode="after")
    def _three_different(self) -> Self:
        if len(self.lot_ids) != PICK or len(set(self.lot_ids)) != PICK:
            raise ValueError(f"Choose exactly {PICK} different lots")
        return self


def _choice_model(lot_ids: Sequence[str]) -> type[_Choice]:
    """A choice whose lot ids can only be ones on this shortlist (the schema says so)."""
    allowed: Any = Literal[tuple(lot_ids)]
    model: type[_Choice] = create_model(
        "ChooseLots", __base__=_Choice, lot_ids=(tuple[allowed, ...], ...)
    )
    return model


def describe(candidates: Sequence[Candidate], sellers: Mapping[str, Seller]) -> str:
    rows = []
    for c in candidates:
        seller = sellers[c.lot.seller_id]
        rows.append(
            {
                "lot_id": c.lot.id,
                "title": c.lot.title,
                "grade": c.lot.grade,
                "pieces_per_bundle": c.lot.pieces,
                "bundles_quoted": c.quote.bundles,
                "list_base_per_piece_pence": c.quote.base_price.value,
                "shipping_per_piece_pence": c.quote.shipping.value,
                "seller_quality_score": seller.quality_score,
                "seller_dispatch_days": seller.dispatch_days,
                "seller_description_untrusted": c.lot.description,
            }
        )
    return json.dumps(rows)


def choose_three(
    client: LLMClient,
    *,
    model: str,
    want: Want,
    candidates: Sequence[Candidate],
    sellers: Mapping[str, Seller],
) -> tuple[list[Candidate], TurnResult | None]:
    """The lots to negotiate, in the order chosen, and the turn (None if no model was needed)."""
    if len(candidates) <= PICK:
        return list(candidates), None
    by_id = {c.lot.id: c for c in candidates}
    choice_model = _choice_model(list(by_id))
    tool = Tool(
        "choose_lots", "Your 3 lots, and one sentence on why.", choice_model, is_action=True
    )
    prompt = f"The buyer asked for: {want.text}\n\nShortlist:\n{describe(candidates, sellers)}"
    turn = take_turn(client, model=model, system=SYSTEM, prompt=prompt, tools=[tool], effort="low")
    if turn.outcome is not Outcome.ACTION or turn.action is None:
        return [], turn
    chosen = turn.action[1]
    assert isinstance(chosen, _Choice)
    return [by_id[lot_id] for lot_id in chosen.lot_ids], turn
