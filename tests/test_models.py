import pytest
from pydantic import BaseModel, ValidationError

from fleek_agents.domain.models import Grade, ListingType, Lot, PenceField
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
