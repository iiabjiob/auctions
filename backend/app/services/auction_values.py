from __future__ import annotations

from decimal import Decimal, InvalidOperation


def parse_price(value: str | None) -> Decimal | None:
    if not value:
        return None
    normalized = value.replace(" ", "").replace("\xa0", "").replace(",", ".")
    normalized = "".join(char for char in normalized if char.isdigit() or char == ".")
    if not normalized:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None
