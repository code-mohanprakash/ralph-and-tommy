import copy
import json
import logging
import pickle

import pytest
from pydantic import BaseModel, ConfigDict

from fleek_agents.domain.money import Pence
from fleek_agents.vault.secret import SecretMoney

FLOOR = SecretMoney(Pence(1137))  # £11.37: digits that would stand out if they leaked


# Every way Python code formats a value, old styles included, on purpose.
SHOWN = [str(FLOOR), repr(FLOOR), f"{FLOOR}", f"{FLOOR!r}", f"{FLOOR:>10}"]
SHOWN += ["%s" % FLOOR, "{}".format(FLOOR)]  # noqa: UP031, UP032


@pytest.mark.parametrize("shown", SHOWN)
def test_printing_a_secret_shows_stars(shown: str) -> None:
    assert "***" in shown
    assert "1137" not in shown
    assert "11.37" not in shown


def test_a_secret_in_a_log_line_shows_stars(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        logging.getLogger("test").info("floor is %s", FLOOR)
    assert "1137" not in caplog.text
    assert "***" in caplog.text


def test_a_secret_in_an_error_message_shows_stars() -> None:
    with pytest.raises(ValueError) as caught:
        raise ValueError(f"offer below floor {FLOOR}")
    assert "1137" not in str(caught.value)


def test_a_secret_refuses_to_become_json() -> None:
    with pytest.raises(TypeError):
        json.dumps({"floor": FLOOR})


@pytest.mark.parametrize("config", [ConfigDict(), ConfigDict(arbitrary_types_allowed=True)])
def test_a_secret_cant_be_part_of_a_pydantic_model(config: ConfigDict) -> None:
    # Tool inputs and outputs for the AI are Pydantic models, so this closes that door, even for
    # a model that tells Pydantic to accept any type at all.
    with pytest.raises(TypeError, match="can't be part of a Pydantic model"):

        class ToolResult(BaseModel):
            model_config = config
            floor: SecretMoney


@pytest.mark.parametrize("copier", [pickle.dumps, copy.copy, copy.deepcopy])
def test_a_secret_cant_be_copied_out(copier: object) -> None:
    with pytest.raises(TypeError):
        copier(FLOOR)  # type: ignore[operator]


@pytest.mark.parametrize(
    "compare",
    [lambda: FLOOR < Pence(1200), lambda: FLOOR == Pence(1137)],  # noqa: SIM300 - secret first, on purpose
)
def test_a_secret_cant_be_compared_outside_the_vault(compare: object) -> None:
    with pytest.raises(TypeError):
        compare()  # type: ignore[operator]


def test_a_secret_holds_pence_only() -> None:
    with pytest.raises(TypeError):
        SecretMoney(1137)  # type: ignore[arg-type]


def test_the_vault_can_read_the_value_on_purpose() -> None:
    assert FLOOR.reveal() == Pence(1137)


def test_a_secret_has_no_attribute_dict_to_dump() -> None:
    assert not hasattr(FLOOR, "__dict__")
