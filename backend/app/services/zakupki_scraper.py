from __future__ import annotations

import html
import re
from collections.abc import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.schemas.procurements import ProcurementLotItem, ProcurementSourceInfo
from app.services.procurement_values import parse_money


BASE_URL = "https://zakupki.gov.ru"
SEARCH_PATH = "/epz/order/extendedsearch/results.html"
DEFAULT_RECORDS_PER_PAGE = 50
DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.6",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}


def source_info() -> ProcurementSourceInfo:
    return ProcurementSourceInfo(code="zakupki", title="ЕИС Закупки", website=BASE_URL)


def iter_procurement_list(
    *,
    limit: int | None = None,
    start_page: int = 1,
    records_per_page: int = DEFAULT_RECORDS_PER_PAGE,
    timeout: int = 30,
) -> Iterable[ProcurementLotItem]:
    yielded = 0
    page = max(1, start_page)
    while limit is None or yielded < limit:
        html_text = fetch_search_page(page=page, records_per_page=records_per_page, timeout=timeout)
        items = parse_search_results(html_text)
        if not items:
            return
        for item in items:
            yield item
            yielded += 1
            if limit is not None and yielded >= limit:
                return
        page += 1


def fetch_procurement_list(limit: int | None = None, *, page: int = 1) -> list[ProcurementLotItem]:
    return list(iter_procurement_list(limit=limit, start_page=page))


def fetch_search_page(*, page: int = 1, records_per_page: int = DEFAULT_RECORDS_PER_PAGE, timeout: int = 30) -> str:
    params = {
        "morphology": "on",
        "search-filter": "Дате размещения",
        "pageNumber": page,
        "sortDirection": "false",
        "recordsPerPage": f"_{records_per_page}",
        "showLotsInfoHidden": "false",
        "sortBy": "UPDATE_DATE",
        "fz44": "on",
        "fz223": "on",
    }
    url = f"{BASE_URL}{SEARCH_PATH}?{urlencode(params)}"
    request = Request(url, headers=DEFAULT_HEADERS)
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode(_response_encoding(response.headers.get("Content-Type")), "replace")


def parse_search_results(html_text: str) -> list[ProcurementLotItem]:
    chunks = _entry_chunks(html_text)
    items: list[ProcurementLotItem] = []
    for chunk in chunks:
        item = _parse_entry(chunk)
        if item is not None:
            items.append(item)
    return items


def _entry_chunks(html_text: str) -> list[str]:
    starts = [match.start() for match in re.finditer(r"registry-entry__header-mid__number", html_text)]
    chunks: list[str] = []
    for index, start in enumerate(starts):
        chunk_start = max(0, html_text.rfind("<div", 0, start))
        next_start = starts[index + 1] if index + 1 < len(starts) else len(html_text)
        chunks.append(html_text[chunk_start:next_start])
    return chunks


def _parse_entry(chunk: str) -> ProcurementLotItem | None:
    number_match = re.search(
        r'<div class="registry-entry__header-mid__number">\s*<a[^>]+href="([^"]+)"[^>]*>\s*№\s*([0-9]+)\s*</a>',
        chunk,
        re.S,
    )
    if not number_match:
        return None

    notice_url = _absolute_url(html.unescape(number_match.group(1)))
    registry_number = number_match.group(2)
    raw_fields = _extract_body_fields(chunk)
    title = raw_fields.get("Объект закупки") or raw_fields.get("Наименование закупки")
    status = _first_match_text(chunk, r'registry-entry__header-mid__title[^>]*>\s*(.*?)\s*</div>')
    price = _first_body_value(raw_fields, "Начальная цена", "Начальная (максимальная) цена контракта")
    price = price or _extract_price_block(chunk)
    customer = _first_body_value(raw_fields, "Заказчик", "Организация, осуществляющая размещение")
    organizer = _first_body_value(raw_fields, "Организация, осуществляющая размещение", "Размещено")
    procedure_type = _first_body_value(raw_fields, "Способ определения поставщика", "Способ закупки")
    platform = _first_body_value(raw_fields, "Электронная площадка")
    region = _first_body_value(raw_fields, "Регион")
    publication_date = _extract_labeled_datetime(chunk, "Размещено")
    application_deadline = _extract_labeled_datetime(chunk, "Окончание подачи заявок")

    return ProcurementLotItem(
        source="zakupki",
        external_id=registry_number,
        registry_number=registry_number,
        law=_detect_law(notice_url),
        title=title,
        status=status,
        customer_name=customer,
        organizer_name=organizer if organizer != customer else None,
        procedure_type=procedure_type,
        platform_name=platform,
        region=region,
        initial_price=price,
        initial_price_value=parse_money(price),
        currency="RUB" if price and ("₽" in price or "8381" in price or "руб" in price.lower()) else None,
        publication_date=publication_date,
        application_deadline=application_deadline,
        notice_url=notice_url,
        print_url=_extract_print_url(chunk),
        raw_fields=raw_fields,
    )


def _extract_body_fields(chunk: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for block in re.findall(
        r'<div class="registry-entry__body-block">(.*?)(?=\s*<div class="registry-entry__body-block"|\s*<div class="col col d-flex|$)',
        chunk,
        re.S,
    ):
        title_match = re.search(r'registry-entry__body-title[^>]*>(.*?)</div>', block, re.S)
        value_match = re.search(r'registry-entry__body-(?:value|href)[^>]*>(.*?)</div>', block, re.S)
        if not title_match or not value_match:
            continue
        title = _clean_html(title_match.group(1)).rstrip(":")
        value = _clean_html(value_match.group(1))
        if title and value:
            fields[title] = value
    for block in re.findall(r'<div class="price-block">(.*?)</div>\s*</div>', chunk, re.S):
        title_match = re.search(r'price-block__title[^>]*>(.*?)</div>', block, re.S)
        value_match = re.search(r'price-block__value[^>]*>(.*?)</div>', block, re.S)
        if title_match and value_match:
            title = _clean_html(title_match.group(1)).rstrip(":")
            value = _clean_html(value_match.group(1))
            if title and value:
                fields[title] = value
    return fields


def _first_body_value(fields: dict[str, str], *labels: str) -> str | None:
    for label in labels:
        for key, value in fields.items():
            if label.lower() in key.lower():
                return value
    return None


def _extract_labeled_datetime(chunk: str, label: str) -> str | None:
    match = re.search(re.escape(label) + r".{0,500}?(\d{2}\.\d{2}\.\d{4}(?:\s+\d{2}:\d{2})?)", chunk, re.S)
    return _clean_html(match.group(1)) if match else None


def _extract_price_block(chunk: str) -> str | None:
    match = re.search(
        r'price-block__title[^>]*>\s*Начальная[^<]*</div>\s*<div class="price-block__value"[^>]*>(.*?)</div>',
        chunk,
        re.S,
    )
    return _clean_html(match.group(1)) if match else None


def _extract_print_url(chunk: str) -> str | None:
    match = re.search(r'href="([^"]*print-form[^"]+|[^"]*printForm[^"]+)"', chunk, re.I)
    return _absolute_url(html.unescape(match.group(1))) if match else None


def _first_match_text(chunk: str, pattern: str) -> str | None:
    match = re.search(pattern, chunk, re.S)
    return _clean_html(match.group(1)) if match else None


def _clean_html(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>", " ", value, flags=re.S | re.I)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.S | re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def _absolute_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url.replace("http://zakupki.gov.ru", BASE_URL, 1)
    if url.startswith("/"):
        return f"{BASE_URL}{url}"
    return f"{BASE_URL}/{url}"


def _detect_law(url: str) -> str | None:
    if "/223/" in url or "fz223" in url.lower():
        return "223-ФЗ"
    if "/epz/order/" in url:
        return "44-ФЗ"
    return None


def _response_encoding(content_type: str | None) -> str:
    if content_type:
        match = re.search(r"charset=([^;]+)", content_type, re.I)
        if match:
            return match.group(1).strip()
    return "utf-8"
