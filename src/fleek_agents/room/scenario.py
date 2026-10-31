"""The Deal Room's market: one Brick Lane vintage shop and three warehouses selling Levi's 501.

Small and fixed on purpose, so the story has the same shape every time and each warehouse shows
one part of matching:

- Lahore lists grade C. The shop wants grade A, so the filters drop it.
- Delhi's floor is above its own list price, so the vault says no price can work.
- Karachi is the one to watch: its floor is the one the person running the demo sets.

The person sets two secret limits: the shop's max (per pair, delivered) and Karachi's floor (per
pair, after Fleek's commission). They go straight into mandates, which only the vault reads.
"""

from dataclasses import dataclass

from fleek_agents.domain.models import (
    Buyer,
    BuyerKind,
    Grade,
    ListingType,
    Lot,
    Market,
    Seller,
    Want,
)
from fleek_agents.domain.money import Pence
from fleek_agents.vault.mandate import BuyerMandate, SellerMandate
from fleek_agents.vault.secret import SecretMoney
from fleek_agents.vault.seed import Secrets

BUYER_ID = "buyer-9001"
LAHORE, KARACHI, DELHI = "seller-9001", "seller-9002", "seller-9003"
PAIRS_A_BUNDLE = 50

# Where each warehouse is, for the page. Public, like a seller's country on Fleek.
PLACES = {
    LAHORE: ("Lahore", "Pakistan"),
    KARACHI: ("Karachi", "Pakistan"),
    DELHI: ("Delhi", "India"),
}

DELHI_FLOOR = Pence(1200)  # £12.00 after commission: needs a card above Delhi's £13.50 list price
LAHORE_FLOOR = Pence(600)


@dataclass(frozen=True)
class RoomInput:
    """What the person running the demo chooses."""

    buyer_max: Pence  # the most the shop pays per pair, delivered (base + shipping + fee)
    seller_floor: Pence  # the least Karachi takes per pair, after Fleek's commission
    pairs: int = 200  # how many pairs the shop wants
    regular_buyer: bool = False  # True: the shop has closed deals before, so the rule may approve
    tommy_breaks_a_rule: bool = False  # a Tommy broken on purpose, to show the vault stopping him

    def __post_init__(self) -> None:
        if not 1 <= self.buyer_max.value <= 10_000 or not 1 <= self.seller_floor.value <= 10_000:
            raise ValueError("Limits must be between 1p and £100 a pair")
        if self.pairs % PAIRS_A_BUNDLE or not PAIRS_A_BUNDLE <= self.pairs <= 300:
            raise ValueError(f"Pairs must be a multiple of {PAIRS_A_BUNDLE}, from 50 to 300")


def _lot(lot_id: str, seller_id: str, grade: Grade, base: int, shipping: int) -> Lot:
    city = PLACES[seller_id][0]
    return Lot(
        id=lot_id,
        seller_id=seller_id,
        title=f"Levi's 501 jeans, grade {grade}, {PAIRS_A_BUNDLE} pairs",
        brand="Levi's",
        category="jeans",
        grade=grade,
        listing_type=ListingType.REPRESENTATIVE,
        pieces=PAIRS_A_BUNDLE,
        available=6,
        base_price=Pence(base),
        shipping=Pence(shipping),
        description=f"Vintage Levi's 501s from a {city} warehouse, sorted by grade.",
    )


def room_market(pairs: int) -> Market:
    buyer = Buyer(
        id=BUYER_ID, name="Vintage shop, Brick Lane", kind=BuyerKind.VINTAGE_SHOP, country="GB"
    )
    sellers = (
        Seller(
            id=LAHORE, name="Lahore Denim House", country="PK", quality_score=4.1, dispatch_days=3
        ),
        Seller(
            id=KARACHI,
            name="Karachi Textile Recycling",
            country="PK",
            quality_score=4.6,
            dispatch_days=2,
        ),
        Seller(
            id=DELHI, name="Delhi Vintage Exports", country="IN", quality_score=4.3, dispatch_days=4
        ),
    )
    lots = (
        _lot("lot-9001", LAHORE, Grade.C, base=900, shipping=300),
        _lot("lot-9002", KARACHI, Grade.A, base=1400, shipping=300),
        _lot("lot-9003", DELHI, Grade.A, base=1350, shipping=320),
    )
    want = Want(
        buyer_id=BUYER_ID,
        category="jeans",
        brands=("Levi's",),
        grades=(Grade.A,),
        pieces=pairs,
        text=f"About {pairs} pairs of Levi's 501, grade A.",
    )
    return Market(buyers=(buyer,), sellers=sellers, lots=lots, wants=(want,))


def room_secrets(market: Market, room: RoomInput) -> Secrets:
    floors = {LAHORE: LAHORE_FLOOR, KARACHI: room.seller_floor, DELHI: DELHI_FLOOR}
    return Secrets(
        buyers={
            BUYER_ID: BuyerMandate(buyer_id=BUYER_ID, max_per_piece=SecretMoney(room.buyer_max))
        },
        lots={
            lot.id: SellerMandate(
                seller_id=lot.seller_id,
                lot_id=lot.id,
                floor_per_piece=SecretMoney(floors[lot.seller_id]),
            )
            for lot in market.lots
        },
    )


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str  # the button
    shows: str  # one line: what it demonstrates
    room: RoomInput


# Each one is checked in tests/test_room.py to end the way its label says.
SCENARIOS = (
    Scenario(
        "deal",
        "A deal a person approves",
        "200 pairs, a new shop: £1,500 or more waits for a person",
        RoomInput(buyer_max=Pence(1550), seller_floor=Pence(935)),
    ),
    Scenario(
        "small",
        "A small deal the rule approves",
        "50 pairs for a shop with deals behind it",
        RoomInput(buyer_max=Pence(1550), seller_floor=Pence(935), pairs=50, regular_buyer=True),
    ),
    Scenario(
        "broken",
        "Tommy breaks a rule",
        "Tommy tries to sell below his floor; the vault stops it",
        RoomInput(buyer_max=Pence(1550), seller_floor=Pence(935), tommy_breaks_a_rule=True),
    ),
    Scenario(
        "near_miss",
        "A near miss",
        "A price existed, but they ran out of cards 2% apart",
        RoomInput(buyer_max=Pence(1620), seller_floor=Pence(1110)),
    ),
    Scenario(
        "no_match",
        "No price can work",
        "The shop's max is below the floor: never matched",
        RoomInput(buyer_max=Pence(1300), seller_floor=Pence(1100)),
    ),
)
