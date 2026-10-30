from dataclasses import FrozenInstanceError

import pytest

from fleek_agents.domain.money import Pence


def test_a_price_is_a_whole_number_of_pence() -> None:
    assert Pence(1350).value == 1350


@pytest.mark.parametrize("bad", [12.83, True, "1350", None])
def test_anything_but_a_whole_number_is_refused(bad: object) -> None:
    with pytest.raises(TypeError):
        Pence(bad)  # type: ignore[arg-type]


def test_a_price_cant_be_negative() -> None:
    with pytest.raises(ValueError):
        Pence(-5)


def test_a_price_cant_be_changed_after_it_is_made() -> None:
    price = Pence(1350)
    with pytest.raises(FrozenInstanceError):
        price.value = 1  # type: ignore[misc]


def test_prices_add_up() -> None:
    assert Pence(1120) + Pence(250) == Pence(1370)


def test_adding_a_float_to_a_price_fails() -> None:
    with pytest.raises(TypeError):
        Pence(1120) + 2.5  # type: ignore[operator]


def test_price_times_quantity() -> None:
    assert Pence(1120).times(100) == Pence(112_000)


@pytest.mark.parametrize("bad", [-1, 2.5, True])
def test_quantity_must_be_a_whole_number_of_pieces(bad: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        Pence(1120).times(bad)  # type: ignore[arg-type]


def test_prices_compare_exactly_at_the_limit() -> None:
    limit = Pence(1200)
    assert Pence(1200) <= limit
    assert not Pence(1201) <= limit


def test_a_price_cant_be_compared_with_a_bare_number() -> None:
    with pytest.raises(TypeError):
        _ = Pence(1200) <= 1200  # type: ignore[operator]


@pytest.mark.parametrize(
    ("pence", "shown"), [(1283, "£12.83"), (5, "£0.05"), (0, "£0.00"), (112_000, "£1,120.00")]
)
def test_prices_print_in_pounds(pence: int, shown: str) -> None:
    assert str(Pence(pence)) == shown
