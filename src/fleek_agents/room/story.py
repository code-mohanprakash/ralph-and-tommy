"""Turn a Deal Room run into steps a person can follow: one plain sentence each, plus the detail.

Every step says what happened in plain words (`say`) and which code did it (`detail`, for the
engineer view). The steps hold no secret limit: only the prices on the cards, the band words the
agents got back, and the vault's yes/no answers. The secret limits go in a separate `audience`
block, which the page shows only when the person running the demo chooses to.
"""

from dataclasses import asdict, dataclass, replace
from typing import Any

from fleek_agents.agents.base import Accept, HandOff, Send, WalkAway
from fleek_agents.domain.bands import Band
from fleek_agents.domain.events import EscalationReason, Event
from fleek_agents.domain.fees import buyer_pays, seller_receives
from fleek_agents.domain.money import Pence
from fleek_agents.domain.state import Move, NegotiationState
from fleek_agents.room.play import RoomRun, Turn
from fleek_agents.room.scenario import PLACES

MEANS = {
    Band.STRONG: "very good for you",
    Band.ACCEPTABLE: "fine for you",
    Band.STRETCH: "allowed, but close to your limit",
    Band.OUTSIDE: "past your limit",
}
NAME = {"ralph": "Ralph", "tommy": "Tommy"}
SIDE = {"ralph": "the shop's", "tommy": "the warehouse's"}
OTHER = {"ralph": "tommy", "tommy": "ralph"}

WHY_STOPPED = {
    EscalationReason.CARD_OUTSIDE_LIMIT: "{who} tried to send {price}, past {side} own limit. "
    "The vault stops it, so the card is never sent. A person takes over.",
    EscalationReason.ACCEPT_OUTSIDE_LIMIT: "{who} tried to accept a price outside a limit. "
    "The vault refuses, and a person takes over.",
    EscalationReason.OVER_BUDGET: "That would take the shop past its budget across all its "
    "deals. The vault refuses, and a person takes over.",
    EscalationReason.MODEL_REFUSED: "{who}'s AI refused to answer. A person takes over.",
    EscalationReason.TOO_MANY_CORRECTIONS: "{who}'s AI kept giving answers the rules don't allow. "
    "A person takes over.",
    EscalationReason.SPEND_CAP: "The AI spending limit for this negotiation is reached. "
    "A person takes over.",
}


@dataclass(frozen=True)
class Step:
    actor: str  # who acts: buyer, seller, ralph, tommy, vault, person
    kind: str  # what the page animates: tell, secret, list, filter, check, matched, card, ...
    say: str  # one plain sentence or two
    detail: str  # the code that did it, for the engineer view
    target: str | None = None  # who receives it, when something moves
    seller_id: str | None = None  # which warehouse, when it's about one
    price: int | None = None  # pence: a card's price
    band: str | None = None  # the band word an agent got back
    asked: int | None = None  # pence: the price that band word is about
    ok: bool | None = None  # the vault's or the referee's answer


def _pairs(n: int) -> str:
    return f"{n} pair" + ("" if n == 1 else "s")


def _setup_steps(run: RoomRun) -> list[Step]:
    want = run.market.wants[0]
    lots = run.market.lots
    listed = ", ".join(f"{PLACES[x.seller_id][0]} {x.base_price}" for x in lots)
    steps = [
        Step(
            "buyer",
            "tell",
            f'The vintage shop on Brick Lane tells Ralph: "{want.text}"',
            f"Want(category={want.category!r}, brands={want.brands}, "
            f"grades={tuple(str(g) for g in want.grades)}, pieces={want.pieces})",
            target="ralph",
        ),
        Step(
            "buyer",
            "secret",
            "The shop puts its limit in the vault: the most it will pay a "
            "pair, delivered. Ralph is never told it.",
            "BuyerMandate(max_per_piece=SecretMoney(***)). Only the vault package reads it, and "
            "import-linter stops the agents from importing it.",
            target="vault",
        ),
        Step(
            "seller",
            "list",
            f"Three warehouses list Levi's 501s on Fleek. List prices are public: {listed} a pair.",
            "Lot(...) rows loaded into SQLite with their stock: load_market()",
        ),
        Step(
            "seller",
            "secret",
            "Each warehouse puts its floor in the vault: the least it will "
            "take a pair, after Fleek's 15%. Tommy is never told it.",
            "SellerMandate(floor_per_piece=SecretMoney(***)), one per lot",
            target="vault",
        ),
    ]
    for c in run.checked:
        place = PLACES[c.lot.seller_id][0]
        if not c.passed_filters:
            steps.append(
                Step(
                    "vault",
                    "filter",
                    f"Matching starts with plain filters. {place} is dropped: its "
                    f"lot is grade {c.lot.grade}, and the shop wants grade "
                    f"{'/'.join(str(g) for g in want.grades)}.",
                    "hard_filter(): SQL on category, brand, grade and stock. No secret is used.",
                    seller_id=c.lot.seller_id,
                    ok=False,
                )
            )
    for c in run.checked:
        if c.possible is None:
            continue
        place = PLACES[c.lot.seller_id][0]
        answer = "Yes" if c.possible else "No"
        tail = "" if c.possible else " It doesn't say why, or give a number."
        steps.append(
            Step(
                "vault",
                "check",
                f"The vault is asked one question about {place}: could any price "
                f'work for both sides? "{answer}."{tail}',
                f"deal_possible(buyer, seller, quote) → {c.possible}",
                seller_id=c.lot.seller_id,
                ok=c.possible,
            )
        )
    return steps


def _ask(turn: Turn, on_table: int | None) -> tuple[str, int | None, str | None]:
    """What the agent asked the vault this turn, in a sentence. The first check is the one shown;
    scripted agents are plain code and may check a few prices, the detail lists them all."""
    if not turn.asked:
        return "", None, None
    first = turn.asked[0]
    who = NAME[turn.who]
    about = (
        f"{NAME[OTHER[turn.who]]}'s {first.price}"
        if on_table == first.price.value
        else str(first.price)
    )
    return (
        f'{who} asks the vault about {about}. One word comes back: "{first.band}" '
        f"({MEANS[first.band]}). ",
        first.price.value,
        str(first.band),
    )


def _turn_step(turn: Turn, on_table: int | None, mine: int | None) -> Step:
    who, name = turn.who, NAME[turn.who]
    asked_text, asked, band = _ask(turn, on_table)
    checks = ", ".join(f"view.band({a.price.value}) → {a.band}" for a in turn.asked)
    events = "; ".join(_event_text(e) for e in turn.events)
    detail = f"band checks: {checks or 'none'}. Recorded: {events}"
    stop = next((e for e in turn.events if e.move is Move.ESCALATE), None)
    action = turn.action

    if stop is not None and stop.reason is not None:
        price = action.terms.base_price.value if isinstance(action, Send) else on_table
        text = WHY_STOPPED[stop.reason].format(who=name, price=Pence(price or 0), side=SIDE[who])
        return Step(
            who,
            "blocked",
            asked_text + text,
            detail,
            target="vault",
            price=price,
            band=band,
            asked=asked,
            ok=False,
        )
    if isinstance(action, Send):
        price = action.terms.base_price.value
        if mine is None:
            move = f"{name} {'offers' if who == 'ralph' else 'counters at'} {Pence(price)} a pair."
        elif price == mine:
            move = (
                f"{name} can't move any further inside {SIDE[who]} limit, "
                f"so he repeats {Pence(price)}."
            )
        else:
            move = f"{name} moves to {Pence(price)} a pair."
        check = (
            "The vault checks it's within the shop's limit before it's sent: yes."
            if who == "ralph"
            else "The vault checks it's above the warehouse's floor before it's sent: yes."
        )
        return Step(
            who,
            "card",
            f"{asked_text}{move} {check}",
            detail,
            target=OTHER[who],
            price=price,
            band=band,
            asked=asked,
            ok=True,
        )
    if isinstance(action, Accept):
        return Step(
            who,
            "accept",
            f"{asked_text}So {name} accepts {Pence(on_table or 0)}. "
            "The vault checks the deal against both limits: inside both. The stock is "
            "taken in one step.",
            detail + ". can_accept() → True; store.accept()",
            target="vault",
            price=on_table,
            band=band,
            asked=asked,
            ok=True,
        )
    if isinstance(action, WalkAway):
        return Step(
            who, "walk", f"{asked_text}{name} walks away. No deal.", detail, band=band, asked=asked
        )
    assert isinstance(action, HandOff)
    return Step(
        who,
        "blocked",
        WHY_STOPPED[action.reason].format(who=name, price="", side=SIDE[who]),
        detail,
        ok=False,
    )


def _event_text(e: Event) -> str:
    card = f" base={e.card.base_price.value}" if e.card else ""
    reason = f" reason={e.reason}" if e.reason else ""
    return f"event {e.seq}: {e.move} by {e.by}{card}{reason}"


def _money(price: int, pairs: int, shipping: Pence) -> dict[str, int]:
    paid = buyer_pays(base_price=Pence(price), shipping=shipping, pieces=pairs)
    got = seller_receives(base_price=Pence(price), pieces=pairs)
    return {
        "buyer_pays": paid.total.value,
        "seller_gets": got.net.value,
        "fleek_earns": (paid.protection_fee + got.commission).value,
        "protection_fee": paid.protection_fee.value,
        "commission": got.commission.value,
    }


def story(run: RoomRun) -> dict[str, Any]:
    steps = _setup_steps(run)
    outcome: dict[str, Any] = {"state": "no_match"}
    lot = run.lot
    if lot is None:
        steps.append(
            Step(
                "vault",
                "no_match",
                "No warehouse can work for the shop. Nothing to negotiate, and no AI was called.",
                "rank([]) → nothing to open",
            )
        )
    else:
        pairs = run.bundles * lot.pieces
        place = PLACES[lot.seller_id][0]
        steps.append(
            Step(
                "vault",
                "matched",
                f"{place}'s lot is matched: {run.bundles} bundles, "
                f"{_pairs(pairs)}, list price {lot.base_price} a pair. Ralph buys for the shop, "
                "Tommy sells for the warehouse.",
                f"rank() → {lot.id}; bundles_for() → {run.bundles}; open_negotiation() → "
                f"{run.negotiation_id}",
                seller_id=lot.seller_id,
                ok=True,
            )
        )
        on_table: int | None = None
        last: dict[str, int | None] = {"ralph": None, "tommy": None}
        for turn in run.turns:
            step = _turn_step(turn, on_table, last[turn.who])
            if step.kind == "blocked" and turn.who == "tommy" and run.room.tommy_breaks_a_rule:
                step = replace(
                    step, say="This Tommy is broken on purpose, for the demo. " + step.say
                )
            steps.append(step)
            for e in turn.events:
                if e.card is not None:
                    on_table = last[turn.who] = e.card.base_price.value
        assert run.negotiation_id is not None
        snap = run.log.saved(run.negotiation_id)
        outcome = {"state": str(run.final), "pairs": pairs}
        if snap.agreed is not None:
            price = snap.agreed.base_price.value
            outcome |= {"price": price} | _money(price, pairs, lot.shipping)
            m = outcome
            steps.append(
                Step(
                    "vault",
                    "money",
                    f"The shop pays {Pence(m['buyer_pays'])} for {_pairs(pairs)} "
                    f"at {Pence(price)}, with shipping and Fleek's protection fee. The warehouse "
                    f"gets {Pence(m['seller_gets'])} after Fleek's 15%. Fleek earns "
                    f"{Pence(m['fleek_earns'])}.",
                    "buyer_pays() and seller_receives() in domain/fees.py, whole pence",
                )
            )
            if run.final is NegotiationState.PENDING_APPROVAL:
                steps.append(
                    Step(
                        "person",
                        "waiting",
                        f"The deal waits for a person at Fleek: {run.why_waiting}."
                        " The stock is held until they decide.",
                        f"settle() → pending_approval; pending() → {run.why_waiting!r}",
                    )
                )
            elif run.final is NegotiationState.CLOSED:
                steps.append(
                    Step(
                        "vault",
                        "approved",
                        "Approved by the rule: under £1,500, and the shop has "
                        "closed deals before. No person needed. The deal is final.",
                        "settle() → approve by system → closed",
                    )
                )
        outcome["why_waiting"] = run.why_waiting

    sellers = []
    for c in run.checked:
        city, country = PLACES[c.lot.seller_id]
        sellers.append(
            {
                "id": c.lot.seller_id,
                "city": city,
                "country": country,
                "lot": c.lot.title,
                "grade": str(c.lot.grade),
                "list_price": c.lot.base_price.value,
                "shipping": c.lot.shipping.value,
                "passed_filters": c.passed_filters,
                "possible": c.possible,
                "chosen": lot is not None and c.lot.id == lot.id,
            }
        )
    room = run.room
    return {
        "negotiation_id": run.negotiation_id,
        # What was run, so the page's controls can show it (a scenario button sets them all).
        "input": {
            "pairs": room.pairs,
            "regular_buyer": room.regular_buyer,
            "tommy_breaks_a_rule": room.tommy_breaks_a_rule,
        },
        "buyer": {
            "name": run.market.buyers[0].name,
            "wants": run.market.wants[0].text,
            "pairs": run.room.pairs,
            "regular": run.room.regular_buyer,
        },
        "sellers": sellers,
        "steps": [asdict(s) for s in steps],
        "outcome": outcome,
        # The account manager's summary, when a person is needed. Built without the vault.
        "handover": None
        if run.handover is None
        else asdict(run.handover) | {"at_stake": run.handover.at_stake.value},
        # The secret limits, for the audience only. The page hides them unless asked.
        "audience": {
            "buyer_max": run.room.buyer_max.value,
            "seller_floor": run.room.seller_floor.value,
            "buyer_highest_card": _value(run.limits.buyer_highest),
            "seller_lowest_card": _value(run.limits.seller_lowest),
        },
    }


def _value(p: Pence | None) -> int | None:
    return None if p is None else p.value
