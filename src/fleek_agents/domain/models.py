"""Lots, buyers and sellers: the data every part of the system shares.

Pydantic checks data where it comes in (seed files, and later the AI's tool calls) and refuses
anything that doesn't fit, instead of passing it on.
"""

from typing import Annotated

from pydantic import PlainSerializer, PlainValidator, WithJsonSchema

from fleek_agents.domain.money import Pence


def _read_pence(value: object) -> Pence:
    if isinstance(value, Pence):
        return value
    try:
        return Pence(value)  # type: ignore[arg-type]  # Pence checks the type itself
    except TypeError as error:
        # Pydantic reports ValueError as a validation error; a TypeError would escape as a crash.
        raise ValueError(str(error)) from None


# A price inside a model: read from whole pence, written back as whole pence.
PenceField = Annotated[
    Pence,
    PlainValidator(_read_pence),
    PlainSerializer(lambda price: price.value, return_type=int),
    WithJsonSchema({"type": "integer", "minimum": 0, "description": "Whole pence"}),
]
