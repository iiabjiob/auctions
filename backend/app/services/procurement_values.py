from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation


SCRAPED_DATETIME_FORMATS = ("%d.%m.%Y %H:%M", "%d.%m.%Y")


def parse_money(value: str | None) -> Decimal | None:
    if not value:
        return None
    normalized = (
        value.replace("\xa0", " ")
        .replace("₽", "")
        .replace("&#8381;", "")
        .replace("руб.", "")
        .replace("руб", "")
        .strip()
    )
    normalized = re.sub(r"\s+", "", normalized).replace(",", ".")
    normalized = re.sub(r"[^0-9.\-]", "", normalized)
    if not normalized:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def parse_scraped_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()
    for fmt in SCRAPED_DATETIME_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None
