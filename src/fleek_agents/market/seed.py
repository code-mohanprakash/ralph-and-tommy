"""A fake but Fleek-shaped market, the same every time for the same seed.

Shapes come from Fleek's public pages and our 44-listing sample (docs/ASSUMPTIONS.md): most lots
have one available, prices are per piece with shipping on top, most supply is from Pakistan and
India, bulk tiers are 0-15%. The numbers are made up. The secret limits are generated separately,
in vault/seed.py, so this module never touches a secret.
"""

from dataclasses import dataclass
from random import Random

from fleek_agents.domain.models import (
    BulkRules,
    BulkTier,
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


@dataclass(frozen=True)
class Category:
    base: tuple[int, int]  # base price per piece, pence
    shipping: tuple[int, int]  # shipping per piece, pence
    brands: tuple[str, ...]


CATEGORIES = {
    "jeans": Category((800, 1600), (250, 400), ("Levi's", "Wrangler", "Lee", "Diesel")),
    "t-shirts": Category((200, 600), (100, 200), ("Harley-Davidson", "Nike", "Champion", "Mixed")),
    "jackets": Category((1200, 2800), (350, 600), ("Carhartt", "The North Face", "Patagonia")),
    "sweatshirts": Category((600, 1200), (250, 400), ("Champion", "Nike", "Adidas", "Russell")),
    "shirts": Category((400, 900), (150, 250), ("Ralph Lauren", "Tommy Hilfiger", "Mixed")),
    "knitwear": Category((500, 1100), (200, 350), ("Ralph Lauren", "Benetton", "Mixed")),
    "dresses": Category((500, 1200), (150, 300), ("Laura Ashley", "Mixed")),
    "sportswear": Category((400, 1000), (150, 300), ("Nike", "Adidas", "Puma", "Umbro")),
}
GRADES = {Grade.A: 25, Grade.B: 35, Grade.C: 15, Grade.AB: 12, Grade.BC: 10, Grade.ABC: 3}
BUNDLE_SIZES = {10: 10, 15: 8, 20: 12, 25: 10, 30: 10, 40: 8, 50: 12, 60: 6, 80: 4, 100: 5, 150: 3}
SELLER_COUNTRIES = {"PK": 70, "IN": 20, "TH": 4, "AE": 4, "GB": 2}
SELLER_PLACES = ("Karachi", "Lahore", "Faisalabad", "Panipat", "Kandla", "Bangkok", "Dubai")
SELLER_WORDS = ("Textiles", "Denim", "Vintage", "Garments", "Recycling", "Wholesale")
BUYER_KINDS = {BuyerKind.ONLINE_RESELLER: 70, BuyerKind.VINTAGE_SHOP: 25, BuyerKind.ENTERPRISE: 5}
BUYER_COUNTRIES = {"GB": 45, "US": 15, "DE": 8, "FR": 7, "JP": 8, "AU": 7, "NL": 5, "IE": 5}
BUYER_WORDS = (
    ("Second", "Retro", "Loop", "Thread", "Rewind", "Golden", "Wild", "Brick Lane"),
    ("Closet", "Vintage", "Rack", "Finds", "Store", "Archive", "Co", "Studio"),
)
DESCRIPTIONS = (
    "Washed and sorted.",
    "Mixed sizes, mostly M to L.",
    "Vintage 90s pieces.",
    "Some small marks, priced to sell.",
    "Sorted by our graders, photos on request.",
)
SELLERS, BUYERS = 50, 500


def _pick[T](rng: Random, weights: dict[T, int]) -> T:
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def _price(rng: Random, low_high: tuple[int, int]) -> Pence:
    return Pence(rng.randrange(low_high[0], low_high[1] + 1, 5))  # to the nearest 5p


def _seller(rng: Random, n: int) -> Seller:
    tiers = rng.choice([(), ((100, 5),), ((50, 3), (150, 8)), ((100, 5), (200, 10)), ((200, 15),)])
    return Seller(
        id=f"seller-{n:02d}",
        name=f"{rng.choice(SELLER_PLACES)} {rng.choice(SELLER_WORDS)}",
        country=_pick(rng, SELLER_COUNTRIES),
        quality_score=round(rng.uniform(3.5, 5.0), 1),
        dispatch_days=rng.randint(1, 4),
        bulk_rules=BulkRules(tiers=tuple(BulkTier(min_pieces=m, percent_off=p) for m, p in tiers)),
    )


def _lot(rng: Random, n: int, seller_id: str) -> Lot:
    category_name = rng.choice(list(CATEGORIES))
    category = CATEGORIES[category_name]
    brand = rng.choice(category.brands)
    style = rng.choice(["501 ", "505 ", "550 ", ""]) if brand == "Levi's" else ""
    grade = _pick(rng, GRADES)
    pieces = _pick(rng, BUNDLE_SIZES)
    available = 1 if rng.random() < 0.75 else rng.randint(2, 5)
    return Lot(
        id=f"lot-{n:04d}",
        seller_id=seller_id,
        title=f"{brand} {style}{category_name}, grade {grade}, {pieces} pcs",
        brand=brand,
        category=category_name,
        grade=grade,
        listing_type=ListingType.EXACT if available == 1 else ListingType.REPRESENTATIVE,
        pieces=pieces,
        available=available,
        base_price=_price(rng, category.base),
        shipping=_price(rng, category.shipping),
        description=rng.choice(DESCRIPTIONS),
    )


def _buyer_and_want(rng: Random, n: int) -> tuple[Buyer, Want]:
    kind = _pick(rng, BUYER_KINDS)
    buyer = Buyer(
        id=f"buyer-{n:04d}",
        name=f"{rng.choice(BUYER_WORDS[0])} {rng.choice(BUYER_WORDS[1])}",
        kind=kind,
        country=_pick(rng, BUYER_COUNTRIES),
    )
    category_name = rng.choice(list(CATEGORIES))
    brands = (rng.choice(CATEGORIES[category_name].brands),) if rng.random() < 0.6 else ()
    grades = rng.choice(
        [(Grade.A,), (Grade.A, Grade.AB), (Grade.A, Grade.B, Grade.AB), tuple(Grade)]
    )
    pieces = rng.randint(200, 600) if kind is BuyerKind.ENTERPRISE else rng.randint(20, 150)
    brand_text = brands[0] if brands else "any brand"
    grade_text = "any grade" if set(grades) == set(Grade) else "grade " + " or ".join(grades)
    want = Want(
        buyer_id=buyer.id,
        category=category_name,
        brands=brands,
        grades=grades,
        pieces=pieces,
        text=f"Looking for about {pieces} {brand_text} {category_name}, {grade_text}.",
    )
    return buyer, want


def generate_market(seed: int) -> Market:
    """The whole public market. The same seed always gives the same market."""
    rng = Random(seed)
    sellers = tuple(_seller(rng, n) for n in range(1, SELLERS + 1))
    lots: list[Lot] = []
    for seller in sellers:
        for _ in range(rng.randint(20, 40)):
            lots.append(_lot(rng, len(lots) + 1, seller.id))
    pairs = [_buyer_and_want(rng, n) for n in range(1, BUYERS + 1)]
    return Market(
        buyers=tuple(b for b, _ in pairs),
        sellers=sellers,
        lots=tuple(lots),
        wants=tuple(w for _, w in pairs),
    )
