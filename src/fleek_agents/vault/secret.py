"""SecretMoney: a price that refuses every ordinary way of being shown or copied.

It guards against accidents: a secret ending up in a log line, an error message, a JSON file or
a prompt. It is not a lock. Python code can still call reveal(), and the import rule keeps
agent code from reaching the vault at all.
"""

from typing import Any, NoReturn, final

from fleek_agents.domain.money import Pence

HIDDEN = "***"


def _refuse(action: str) -> NoReturn:
    raise TypeError(f"SecretMoney can't be {action}")


@final
class SecretMoney:
    __slots__ = ("_pence",)  # no __dict__, so vars() and similar have nothing to dump

    def __init__(self, pence: Pence) -> None:
        if not isinstance(pence, Pence):
            raise TypeError("SecretMoney holds a Pence")
        self._pence = pence

    def reveal(self) -> Pence:
        """The real value. Only vault code calls this; searching for 'reveal' finds every use."""
        return self._pence

    # Shown anywhere: printed, logged, formatted, in an error message.
    def __repr__(self) -> str:
        return f"SecretMoney({HIDDEN})"

    def __str__(self) -> str:
        return HIDDEN

    def __format__(self, _spec: str) -> str:
        return HIDDEN

    # Compared: only vault code may decide anything with the value.
    def __eq__(self, _other: object) -> bool:
        _refuse("compared outside the vault")

    def __lt__(self, _other: object) -> bool:
        _refuse("compared outside the vault")

    __le__ = __gt__ = __ge__ = __lt__
    __hash__ = None  # type: ignore[assignment]  # not usable as a dict key or in a set

    # Copied: pickled for another process, or copied in memory.
    def __reduce_ex__(self, _protocol: Any) -> NoReturn:
        _refuse("copied or pickled")

    def __copy__(self) -> NoReturn:
        _refuse("copied")

    def __deepcopy__(self, _memo: Any) -> NoReturn:
        _refuse("copied")

    # Put inside a Pydantic model: every AI tool input and output is one.
    @classmethod
    def __get_pydantic_core_schema__(cls, _source: Any, _handler: Any) -> NoReturn:
        _refuse("part of a Pydantic model (anything a model or tool could see)")
