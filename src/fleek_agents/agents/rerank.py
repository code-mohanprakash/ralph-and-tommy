"""Ralph re-ranks the formula's top lots, with a reason for each. AI judgement, checked by code.

Code does the cheap, exact steps first: filters, the vault's yes/no, then the formula score
(matching/score.py). Claude only re-orders the top SHORTLIST, where it can read what the buyer
wrote ("light wash", "ships this week", "waist 30 to 34") in a way fixed weights can't.

What Claude sees is public only: the buyer's words, each lot's title, brand, grade, size of
bundle, delivered list price, the seller's rating and dispatch days, and the formula's score.
Never a limit (this module can't import the vault: an import contract says so), and never a
seller's description. Titles are seller-written, so the prompt marks them as data.

Code checks the answer: the schema only allows lot ids on the shortlist, and every lot must
appear exactly once. Anything else gets a correction; if Claude still can't, or a spend cap is
hit, the formula's order stands. Re-ranking can change the order, never what's on the list.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import Field, StrictStr, create_model, model_validator

from fleek_agents.domain.models import DomainModel, Seller, Want
from fleek_agents.harness.loop import Outcome, Tool, TurnResult, take_turn
from fleek_agents.llm.client import LLMClient
from fleek_agents.matching.score import Scored

SHORTLIST = 5
SYSTEM = (Path(__file__).parent / "prompts" / "ralph_rerank.md").read_text(encoding="utf-8")
FORMULA_KEPT = "The formula's order, kept: Claude's re-rank wasn't available."


class _Placed(DomainModel):
    lot_id: StrictStr
    reason: Annotated[StrictStr, Field(min_length=1, max_length=200)]


class _Ranking(DomainModel):
    order: tuple[_Placed, ...]
    summary: Annotated[StrictStr, Field(min_length=1, max_length=240)]

    @model_validator(mode="after")
    def _each_lot_once(self) -> Self:
        ids = [p.lot_id for p in self.order]
        if len(ids) != len(set(ids)):
            raise ValueError("List each lot exactly once")
        return self


def _ranking_model(lot_ids: Sequence[str]) -> type[_Ranking]:
    """A ranking whose lot ids can only be ones on this shortlist (the schema says so), and that
    must name every one of them (checked here, so a miss goes back to Claude as a correction)."""
    expected = set(lot_ids)
    allowed: Any = Literal[tuple(lot_ids)]
    placed: Any = create_model("PlacedLot", __base__=_Placed, lot_id=(allowed, ...))

    def every_lot(ranking: _Ranking) -> _Ranking:
        missing = expected - {p.lot_id for p in ranking.order}
        if missing:
            raise ValueError(f"Rank every shortlist lot; missing: {', '.join(sorted(missing))}")
        return ranking

    model: type[_Ranking] = create_model(
        "RankLots",
        __base__=_Ranking,
        __validators__={"every_lot": model_validator(mode="after")(every_lot)},  # type: ignore[dict-item]
        order=(tuple[placed, ...], ...),
    )
    return model


@dataclass(frozen=True)
class Reranked:
    order: list[Scored]  # the shortlist in the new order, then the rest in the formula's order
    reasons: dict[str, str]  # lot id: Claude's reason (empty if the formula's order was kept)
    summary: str
    by_ai: bool
    turn: TurnResult | None


def describe(want: Want, shortlist: Sequence[Scored], sellers: Mapping[str, Seller]) -> str:
    """The prompt: the buyer's words, then each lot's public facts. No limit, no description."""
    rows = []
    for rank, s in enumerate(shortlist, 1):
        lot, q, seller = s.lot, s.candidate.quote, sellers[s.lot.seller_id]
        rows.append(
            {
                "lot_id": lot.id,
                "formula_rank": rank,
                "formula_score_out_of_100": round(s.total * 100),
                "title_written_by_seller": lot.title,
                "brand": lot.brand,
                "category": lot.category,
                "grade": lot.grade,
                "pieces_per_bundle": lot.pieces,
                "delivered_list_price_per_piece": str(q.base_price + q.shipping),  # "£17.50"
                "seller_rating_out_of_5": seller.quality_score,
                "seller_dispatch_days": seller.dispatch_days,
            }
        )
    asked = {
        "buyer_wrote": want.text,
        "category": want.category,
        "brands": list(want.brands),
        "grades": list(want.grades),
        "pieces": want.pieces,
    }
    return (
        f"The buyer's request:\n{json.dumps(asked)}\n\n"
        f"The shortlist, in the formula's order:\n{json.dumps(rows)}"
    )


def _formula(ranked: Sequence[Scored], turn: TurnResult | None) -> Reranked:
    return Reranked(list(ranked), {}, FORMULA_KEPT, by_ai=False, turn=turn)


def rerank(
    client: LLMClient,
    *,
    model: str,
    want: Want,
    ranked: Sequence[Scored],
    sellers: Mapping[str, Seller],
) -> Reranked:
    """The formula's ranking with its top SHORTLIST re-ordered by Claude, with reasons."""
    shortlist, rest = list(ranked[:SHORTLIST]), list(ranked[SHORTLIST:])
    if len(shortlist) < 2:
        return _formula(ranked, None)  # nothing to re-order: no model is called
    by_id = {s.lot.id: s for s in shortlist}
    tool = Tool(
        "rank_lots",
        "Every shortlist lot once, best first, each with a one-sentence reason; then a summary.",
        _ranking_model(list(by_id)),
        is_action=True,
    )
    turn = take_turn(
        client,
        model=model,
        system=SYSTEM,
        prompt=describe(want, shortlist, sellers),
        tools=[tool],
        effort="low",
    )
    ranking = turn.action[1] if turn.outcome is Outcome.ACTION and turn.action else None
    if not isinstance(ranking, _Ranking):
        return _formula(ranked, turn)  # no valid answer after corrections: the formula stands
    order = [by_id[p.lot_id] for p in ranking.order] + rest
    reasons = {p.lot_id: p.reason for p in ranking.order}
    return Reranked(order, reasons, ranking.summary, by_ai=True, turn=turn)
