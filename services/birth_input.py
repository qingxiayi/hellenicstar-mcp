"""Shared civil-date validation before calculation or cache access."""

import re
from datetime import datetime


def validated_birth_values(year, month, day, hour, minute):
    """Keep legacy integer strings, rejecting floats, booleans and truncation."""
    values = []
    for name, value in zip(("year", "month", "day", "hour", "minute"),
                           (year, month, day, hour, minute)):
        if isinstance(value, bool):
            raise ValueError(f"{name} must be an integer")
        if isinstance(value, int):
            values.append(value)
        elif isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
            values.append(int(value))
        else:
            raise ValueError(f"{name} must be an integer")
    datetime(*values)
    return tuple(values)
