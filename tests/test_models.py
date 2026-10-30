import pytest
from pydantic import BaseModel, ValidationError

from fleek_agents.domain.models import PenceField
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
