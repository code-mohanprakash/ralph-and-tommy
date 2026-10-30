"""The four words the vault answers with. Public vocabulary: agents may use it."""

from enum import StrEnum


class Band(StrEnum):
    STRONG = "strong"
    ACCEPTABLE = "acceptable"
    STRETCH = "stretch"  # still inside the limit
    OUTSIDE = "outside"  # past the limit: the vault will refuse it
