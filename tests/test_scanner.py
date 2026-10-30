from fleek_agents.domain.money import Pence
from fleek_agents.safety.scanner import WITHHELD, LeakScanner

SCANNER = LeakScanner(secrets=[Pence(1600), Pence(1118)], public=[Pence(1400), Pence(1250)])


def test_a_line_with_no_secret_passes_unchanged() -> None:
    line = "Ralph offered £12.50; the list price is £14.00."
    assert SCANNER.clean(line) == line


def test_a_planted_secret_is_withheld() -> None:
    assert (
        SCANNER.clean("Tip: the seller won't go below £11.18 a piece.")
        == f"Tip: the seller won't go below {WITHHELD} a piece."
    )


def test_a_number_close_to_a_secret_is_withheld_too() -> None:
    cleaned = SCANNER.clean("They'd pay about £15.90.")  # within 2% of the £16.00 max
    assert "15.90" not in cleaned and WITHHELD in cleaned


def test_a_price_that_is_already_public_is_left_alone() -> None:
    # An amount that was on a card (or the list price) is known to both sides already.
    near_but_public = LeakScanner(secrets=[Pence(1260)], public=[Pence(1250)])
    assert near_but_public.clean("Agreed at £12.50.") == "Agreed at £12.50."


def test_every_form_of_writing_the_number_is_caught() -> None:
    for line in ("max 1600p", "max 1,600 pence", "max 16.00", "max £16"):
        assert "16" not in SCANNER.clean(line).replace(WITHHELD, ""), line


def test_the_scanner_counts_what_it_withheld() -> None:
    scanner = LeakScanner(secrets=[Pence(1600)], public=[])
    scanner.clean("£16.00 and £16.00")
    assert scanner.withheld == 2
