"""Changing a secret limit: allowed between negotiations, never during one.

Every negotiation on a lot works to the floor it started with. If a seller lowered their floor
mid-way, Tommy would suddenly give more ground, and the buyer could tell the floor moved (and
roughly where it is now). No product we found lets a limit change mid-negotiation either: Pactum
fixes the limits before a campaign and sends anything outside them to a person. So a change is
refused while any negotiation on the lot (or, for a buyer's max, any of the buyer's
negotiations) is still going or waiting for approval. To change one: stop, change, start again.
"""

from dataclasses import replace

from fleek_agents.domain.money import Pence
from fleek_agents.domain.state import FINAL_STATES
from fleek_agents.store.events import EventLog
from fleek_agents.store.pairings import negotiations_for_lot, negotiations_of
from fleek_agents.vault.secret import SecretMoney
from fleek_agents.vault.seed import Secrets


class LimitLocked(Exception):
    """A negotiation that uses this limit hasn't ended yet."""


def _going(log: EventLog, negotiation_ids: list[str]) -> list[str]:
    return [n for n in negotiation_ids if log.state(n) not in FINAL_STATES]


def change_floor(secrets: Secrets, log: EventLog, *, lot_id: str, floor: Pence) -> Secrets:
    going = _going(log, negotiations_for_lot(log.session, lot_id))
    if going:
        raise LimitLocked(
            f"{lot_id}'s floor is fixed while {', '.join(going)} is going. Stop it to change it."
        )
    old = secrets.lots[lot_id]
    lots = dict(secrets.lots) | {lot_id: replace(old, floor_per_piece=SecretMoney(floor))}
    return Secrets(buyers=secrets.buyers, lots=lots)


def change_max(secrets: Secrets, log: EventLog, *, buyer_id: str, top: Pence) -> Secrets:
    going = _going(log, negotiations_of(log.session, buyer_id))
    if going:
        raise LimitLocked(
            f"{buyer_id}'s top price is fixed while {', '.join(going)} is going. Stop it first."
        )
    old = secrets.buyers[buyer_id]
    buyers = dict(secrets.buyers) | {buyer_id: replace(old, max_per_piece=SecretMoney(top))}
    return Secrets(buyers=buyers, lots=secrets.lots)
