import pytest
from pydantic import BaseModel, ValidationError

from fleek_agents.domain.models import (
    Buyer,
    BuyerKind,
    Grade,
    ListingType,
    Lot,
    PenceField,
    Seller,
)
from fleek_agents.domain.money import Pence


class Priced(BaseModel):
    price: PenceField


def test_a_price_is_read_from_whole_pence() -> None:
    assert Priced.model_validate({"price": 1350}).price == Pence(1350)


def test_a_pence_object_is_accepted_as_it_is() -> None:
    assert Priced(price=Pence(1350)).price == Pence(1350)


@pytest.mark.parametrize("bad", [13.5, "1350", True, -1, None])
def test_a_price_that_isnt_whole_pence_is_refused(bad: object) -> None:
    with pytest.raises(ValidationError):
        Priced.model_validate({"price": bad})


def test_a_price_is_written_out_as_whole_pence() -> None:
    assert Priced(price=Pence(1350)).model_dump_json() == '{"price":1350}'


def test_the_json_schema_says_whole_pence() -> None:
    schema = Priced.model_json_schema()["properties"]["price"]
    assert schema["type"] == "integer"
    assert schema["minimum"] == 0


def a_lot(**changes: object) -> dict[str, object]:
    lot: dict[str, object] = {
        "id": "lot-0001",
        "seller_id": "seller-01",
        "title": "Levi's 501 jeans, mixed sizes",
        "brand": "Levi's",
        "category": "jeans",
        "grade": "A",
        "listing_type": "exact",
        "pieces": 50,
        "available": 1,
        "base_price": 1350,
        "shipping": 300,
        "description": "Washed and sorted. Mostly 30-34 waist.",
    }
    return lot | changes


def test_a_lot_is_read_from_plain_data() -> None:
    lot = Lot.model_validate(a_lot())
    assert lot.grade is Grade.A
    assert lot.listing_type is ListingType.EXACT
    assert lot.base_price == Pence(1350)


def test_the_listed_price_includes_shipping() -> None:
    # Fleek's prices include shipping. Only the base price is negotiable.
    assert Lot.model_validate(a_lot()).listed_price == Pence(1650)


@pytest.mark.parametrize(
    "bad",
    [
        {"grade": "D"},
        {"listing_type": "custom_handpick"},
        {"pieces": 0},
        {"pieces": "50"},
        {"available": -1},
        {"base_price": 13.5},
        {"id": "seller-01"},
        {"seller_id": "lot-0001"},
        {"title": ""},
    ],
)
def test_a_lot_with_bad_data_is_refused(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Lot.model_validate(a_lot(**bad))


def test_a_lot_with_an_unknown_field_is_refused() -> None:
    # Anything not in the model is refused, so a stray secret can't ride along unnoticed.
    with pytest.raises(ValidationError):
        Lot.model_validate(a_lot(floor=900))


def test_a_lot_cant_be_changed_after_it_is_made() -> None:
    lot = Lot.model_validate(a_lot())
    with pytest.raises(ValidationError):
        lot.base_price = Pence(1)  # type: ignore[misc]


def test_a_lot_survives_a_round_trip_through_json() -> None:
    lot = Lot.model_validate(a_lot())
    assert Lot.model_validate_json(lot.model_dump_json()) == lot


def test_a_buyer_is_read_from_plain_data() -> None:
    buyer = Buyer.model_validate(
        {"id": "buyer-0001", "name": "Brick Lane Vintage", "kind": "vintage_shop", "country": "GB"}
    )
    assert buyer.kind is BuyerKind.VINTAGE_SHOP


def test_a_seller_is_read_from_plain_data() -> None:
    seller = Seller.model_validate(
        {
            "id": "seller-01",
            "name": "Karachi Denim Co",
            "country": "PK",
            "quality_score": 4.6,
            "dispatch_days": 2,
        }
    )
    assert seller.quality_score == 4.6


@pytest.mark.parametrize(
    "bad",
    [{"kind": "wholesaler"}, {"country": "gb"}, {"country": "GBR"}, {"id": "seller-01"}],
)
def test_a_buyer_with_bad_data_is_refused(bad: dict[str, object]) -> None:
    buyer = {"id": "buyer-0001", "name": "Brick Lane Vintage", "kind": "vintage_shop"}
    with pytest.raises(ValidationError):
        Buyer.model_validate(buyer | {"country": "GB"} | bad)


@pytest.mark.parametrize(
    "bad", [{"quality_score": 5.1}, {"quality_score": -1}, {"dispatch_days": -1}]
)
def test_a_seller_with_bad_data_is_refused(bad: dict[str, object]) -> None:
    seller = {"id": "seller-01", "name": "Karachi Denim Co", "country": "PK"}
    with pytest.raises(ValidationError):
        Seller.model_validate(seller | {"quality_score": 4.6, "dispatch_days": 2} | bad)


@pytest.mark.parametrize("model", [Buyer, Seller, Lot])
def test_no_model_has_a_field_for_a_secret_limit(model: type[BaseModel]) -> None:
    # The buyer's max and the seller's floor live only in the vault. If a field like this is
    # ever added here, it could end up in front of an agent.
    secret_words = ("max", "floor", "limit", "budget", "reserve", "minimum")
    for field in model.model_fields:
        assert not any(word in field for word in secret_words), f"{model.__name__}.{field}"
