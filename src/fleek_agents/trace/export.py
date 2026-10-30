"""Export a run: every move of every negotiation, as plain JSON for the Deal Room viewer.

Only what's public goes in: the lots, who did what, the prices on the cards, the reason codes, how
each negotiation ended. The file is built from Pydantic models, and SecretMoney refuses to be part
of any Pydantic model, so a secret limit can't be added to a trace by mistake.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Literal

from fleek_agents.domain.models import DomainModel, Lot
from fleek_agents.store.events import EventLog
from fleek_agents.store.pairings import PairingRow

WHO = {"buyer_agent": "ralph", "seller_agent": "tommy", "system": "fleek", "human": "person"}


class TraceMove(DomainModel):
    seq: int
    at: datetime
    who: str  # ralph, tommy, fleek or person
    move: str
    price_pence: int | None = None  # base price per piece on a card
    bundles: int | None = None
    reasons: tuple[str, ...] = ()
    escalated_because: str | None = None


class TraceLot(DomainModel):
    id: str
    title: str
    grade: str
    pieces: int
    list_price_pence: int
    shipping_pence: int


class TraceNegotiation(DomainModel):
    id: str
    buyer_id: str
    lot_id: str
    lot: TraceLot
    outcome: str
    moves: tuple[TraceMove, ...]


class RunTrace(DomainModel):
    format: Literal["ralph-and-tommy/run/1"] = "ralph-and-tommy/run/1"
    title: str
    negotiations: tuple[TraceNegotiation, ...]


def export_run(
    log: EventLog, negotiation_ids: Sequence[str], lots: Mapping[str, Lot], *, title: str
) -> RunTrace:
    negotiations = []
    for negotiation_id in negotiation_ids:
        row = log.session.query(PairingRow).filter_by(negotiation_id=negotiation_id).one()
        lot = lots[row.lot_id]
        moves = tuple(
            TraceMove(
                seq=e.seq,
                at=e.at,
                who=WHO[e.by],
                move=str(e.move),
                price_pence=e.card.base_price.value if e.card else None,
                bundles=e.card.bundles if e.card else None,
                reasons=tuple(str(r) for r in e.card.reason_codes) if e.card else (),
                escalated_because=str(e.reason) if e.reason else None,
            )
            for e in log.read(negotiation_id)
        )
        negotiations.append(
            TraceNegotiation(
                id=negotiation_id,
                buyer_id=row.buyer_id,
                lot_id=lot.id,
                lot=TraceLot(
                    id=lot.id,
                    title=lot.title,
                    grade=lot.grade,
                    pieces=lot.pieces,
                    list_price_pence=lot.base_price.value,
                    shipping_pence=lot.shipping.value,
                ),
                outcome=str(log.state(negotiation_id)),
                moves=moves,
            )
        )
    return RunTrace(title=title, negotiations=tuple(negotiations))
