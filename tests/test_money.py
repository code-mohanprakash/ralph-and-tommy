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


@pytest.mark.parametrize(
    ("text", "pence"), [("13.50", 1350), ("0.05", 5), ("1120", 112_000), ("12.8", 1280)]
)
def test_prices_are_read_from_text_exactly(text: str, pence: int) -> None:
    assert Pence.from_pounds(text) == Pence(pence)


def test_a_float_is_refused_even_when_reading_pounds() -> None:
    with pytest.raises(TypeError):
        Pence.from_pounds(13.5)  # type: ignore[arg-type]


@pytest.mark.parametrize("text", ["13.505", "abc", "", "NaN", "Infinity"])
def test_text_that_isnt_a_whole_number_of_pence_is_refused(text: str) -> None:
    # 13.505 would need rounding. Rounding happens in one place only: discounts.
    with pytest.raises(ValueError):
        Pence.from_pounds(text)


def test_a_negative_price_in_pounds_is_refused() -> None:
    with pytest.raises(ValueError):
        Pence.from_pounds("-1.00")


@pytest.mark.parametrize(
    ("pence", "percent", "expected"),
    [
        (1350, 5, 1283),  # £13.50 at 5% off is £12.825, which rounds up to £12.83
        (1350, 10, 1215),
        (1350, 0, 1350),
        (1350, 100, 0),
        (1, 50, 1),  # half a penny rounds up
        (3, 50, 2),  # 1.5p rounds up to 2p
    ],
)
def test_a_discount_rounds_half_a_penny_up(pence: int, percent: int, expected: int) -> None:
    assert Pence(pence).discounted(percent) == Pence(expected)


@pytest.mark.parametrize("bad", [-1, 101, 2.5, True])
def test_a_discount_must_be_a_whole_percent_from_0_to_100(bad: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        Pence(1350).discounted(bad)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("pence", "percent", "share"), [(158_300, 2, 3166), (125, 2, 3), (124, 2, 2)]
)
def test_a_percentage_of_a_price_rounds_half_a_penny_up(
    pence: int, percent: int, share: int
) -> None:
    assert Pence(pence).percent(percent) == Pence(share)


def test_prices_subtract() -> None:
    assert Pence(1350) - Pence(300) == Pence(1050)


def test_subtracting_more_than_there_is_fails() -> None:
    with pytest.raises(ValueError):
        Pence(100) - Pence(101)
