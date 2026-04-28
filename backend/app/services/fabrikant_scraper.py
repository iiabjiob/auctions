from __future__ import annotations

import re
import socket
import time
from html import unescape
from html.parser import HTMLParser
from urllib.error import URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from app.schemas.auctions import (
    AuctionDetailResponse,
    AuctionListItem,
    AuctionSummary,
    DebtorInfo,
    LotDetailResponse,
    LotSummary,
    OrganizerInfo,
    ScrapedField,
)


BASE_URL = "https://fabrikant.ru"
SEARCH_ROUTE = "/procedure/search/sales"
AUCTIONS_LIST_URL = f"{BASE_URL}{SEARCH_ROUTE}?section_ids[]=6"
PROCEDURE_URL_PREFIX = f"{BASE_URL}/v2/trades/procedure/view/"
LOT_URL_PREFIX = f"{BASE_URL}/v2/trades/procedure/lot/view/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
SEARCH_RSC_STATE_TREE = (
    "%5B%22%22%2C%7B%22children%22%3A%5B%22(root)%22%2C%7B%22children%22%3A%5B"
    "%22sales%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D"
    "%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D"
)
DEFAULT_REQUEST_TIMEOUT = 45
REQUEST_RETRY_ATTEMPTS = 3
REQUEST_RETRY_BACKOFF_SECONDS = 1.5


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def _fetch_html(url: str, timeout: int = DEFAULT_REQUEST_TIMEOUT) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    return _read_response_text(request, timeout=timeout)


def _build_search_params(page_number: int) -> list[tuple[str, str]]:
    params: list[tuple[str, str]] = [("section_ids[]", "6")]
    if page_number > 1:
        params.append(("page_number", str(page_number)))
    return params


def _build_search_url(page_number: int) -> str:
    return f"{BASE_URL}{SEARCH_ROUTE}?{urlencode(_build_search_params(page_number))}"


def _build_search_rsc_url(page_number: int) -> str:
    params = _build_search_params(page_number)
    params.append(("_rsc", format(int(time.time() * 1_000_000), "x")))
    return f"{BASE_URL}{SEARCH_ROUTE}?{urlencode(params)}"


def _fetch_search_rsc(page_number: int, timeout: int = DEFAULT_REQUEST_TIMEOUT) -> str:
    referer_page = page_number - 1 if page_number > 1 else page_number
    request = Request(
        _build_search_rsc_url(page_number),
        headers={
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
            "Referer": _build_search_url(referer_page),
            "User-Agent": USER_AGENT,
            "next-router-state-tree": SEARCH_RSC_STATE_TREE,
            "next-url": "/sales",
            "rsc": "1",
        },
    )
    return _read_response_text(request, timeout=timeout)


def _read_response_text(request: Request, *, timeout: int) -> str:
    last_error: Exception | None = None
    for attempt in range(1, REQUEST_RETRY_ATTEMPTS + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                encoding = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(encoding, errors="replace")
        except URLError as error:
            if not _is_timeout_error(error):
                raise
            last_error = error
        except TimeoutError as error:
            last_error = error
        except socket.timeout as error:
            last_error = error

        if attempt < REQUEST_RETRY_ATTEMPTS:
            time.sleep(REQUEST_RETRY_BACKOFF_SECONDS * attempt)

    assert last_error is not None
    raise URLError(
        f"Fabrikant request timed out after {REQUEST_RETRY_ATTEMPTS} attempts: {request.full_url}"
    ) from last_error


def _is_timeout_error(error: URLError) -> bool:
    reason = error.reason
    return isinstance(reason, TimeoutError | socket.timeout) or "timed out" in str(reason).lower()


class FabrikantFieldParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fields: list[ScrapedField] = []
        self._div_depth = 0
        self._label_depth: int | None = None
        self._value_depth: int | None = None
        self._label_parts: list[str] = []
        self._value_parts: list[str] = []
        self._pending_label: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "div":
            return

        self._div_depth += 1
        classes = set((dict(attrs).get("class") or "").split())
        if "col-md-4" in classes and self._label_depth is None:
            self._label_depth = self._div_depth
            self._label_parts = []
            return
        if "col-md-8" in classes and self._value_depth is None:
            self._value_depth = self._div_depth
            self._value_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag != "div":
            return

        if self._value_depth == self._div_depth:
            value = _normalize_text(" ".join(self._value_parts))
            if self._pending_label and value:
                self.fields.append(ScrapedField(name=self._pending_label, value=value))
            self._pending_label = None
            self._value_depth = None
            self._value_parts = []
        elif self._label_depth == self._div_depth:
            label = _normalize_text(" ".join(self._label_parts)).rstrip(":")
            self._pending_label = label or None
            self._label_depth = None
            self._label_parts = []

        self._div_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._label_depth is not None:
            self._label_parts.append(data)
        if self._value_depth is not None:
            self._value_parts.append(data)


def _parse_fields(html: str) -> list[ScrapedField]:
    parser = FabrikantFieldParser()
    parser.feed(html)
    return parser.fields


def _first_matching_field(fields: list[ScrapedField], *names: str) -> str | None:
    normalized_names = {_normalize_text(name).rstrip(":").lower() for name in names}
    for field in fields:
        field_name = _normalize_text(field.name).rstrip(":").lower()
        if field_name in normalized_names:
            return field.value
    return None


def _extract_attr(attrs: str, name: str) -> str | None:
    match = re.search(rf'{name}="([^"]+)"', attrs)
    if match:
        return unescape(match.group(1))
    match = re.search(rf"{name}='([^']+)'", attrs)
    if match:
        return unescape(match.group(1))
    return None


def _strip_tags(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", unescape(fragment))
    return _normalize_text(text)


def _extract_page_title(html: str, fallback: str) -> str:
    match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not match:
        return fallback
    title = _strip_tags(match.group(1))
    title = re.sub(r"\s*[|\-]\s*Фабрикант.*$", "", title, flags=re.IGNORECASE)
    return title or fallback


def _extract_id(url: str, prefix: str) -> str | None:
    if not url.startswith(prefix):
        return None
    tail = url[len(prefix) :]
    return tail.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0] or None


def _compose_lot_external_id(procedure_id: str, lot_id: str) -> str:
    return f"{procedure_id}:{lot_id}"


def _split_lot_external_id(value: str) -> tuple[str, str | None]:
    if ":" not in value:
        return value, None
    procedure_id, lot_id = value.split(":", 1)
    if not procedure_id or not lot_id:
        return value, None
    return procedure_id, lot_id


def _normalize_rsc_text(value: str | None) -> str | None:
    if not value:
        return None
    return _normalize_text(unescape(value.replace("\\t", " ").replace("\\n", " ")))


def _extract_title_anchor_matches(html: str) -> list[re.Match[str]]:
    matches: list[re.Match[str]] = []
    pattern = re.compile(r"<a(?P<attrs>[^>]+)>(?P<body>.*?)</a>", re.IGNORECASE | re.DOTALL)
    for match in pattern.finditer(html):
        attrs = match.group("attrs")
        href = _extract_attr(attrs, "href")
        classes = _extract_attr(attrs, "class") or ""
        role = _extract_attr(attrs, "role") or ""
        data_slot = _extract_attr(attrs, "data-slot") or ""
        if href and href.startswith(PROCEDURE_URL_PREFIX) and "font-bold" in classes and role != "button" and data_slot != "button":
            matches.append(match)
    return matches


def _extract_rsc_card_field(block: str, label: str) -> str | None:
    match = re.search(
        rf'"children":"{re.escape(label)}".{{0,260}}?"children":"([^"]+)"',
        block,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    return _normalize_rsc_text(match.group(1))


def _extract_rsc_card_price(block: str) -> str | None:
    label_match = re.search(r'"children":"начальная цена"', block, re.IGNORECASE)
    if not label_match:
        return None

    window = block[max(0, label_match.start() - 320) : label_match.start()]
    for match in reversed(list(re.finditer(r'"children":\[(.*?)\]', window, re.DOTALL))):
        parts = re.findall(r'"([^"]+)"', match.group(1))
        if not parts:
            continue
        price = _extract_price(" ".join(parts))
        if price:
            return price

    return None


def _extract_rsc_page_items(body: str) -> list[AuctionListItem]:
    lot_matches = list(re.finditer(r'"lotId":(\d+)', body))
    if not lot_matches:
        return []

    items: list[AuctionListItem] = []
    title_pattern = re.compile(
        r'\{"url":"(https://fabrikant\.ru/v2/trades/procedure/view/[^"\\]+)","name":"([^"]+)"'
    )
    for index, lot_match in enumerate(lot_matches):
        start = lot_match.start()
        end = lot_matches[index + 1].start() if index + 1 < len(lot_matches) else len(body)
        block = body[start:end]
        title_match = title_pattern.search(block)
        if not title_match:
            continue

        procedure_url = title_match.group(1)
        procedure_id = _extract_id(procedure_url, PROCEDURE_URL_PREFIX)
        lot_id = lot_match.group(1)
        title = _normalize_rsc_text(title_match.group(2))
        publication_date = _extract_rsc_card_field(block, "Дата публикации")
        application_deadline = _extract_rsc_card_field(block, "Дата окончания приёма заявок")
        organizer_name = _extract_rsc_card_field(block, "Организатор")
        initial_price = _extract_rsc_card_price(block)
        if not procedure_id or not title:
            continue

        lot_external_id = _compose_lot_external_id(procedure_id, lot_id)
        items.append(
            AuctionListItem(
                source="fabrikant",
                auction=AuctionSummary(
                    source="fabrikant",
                    external_id=procedure_id,
                    number=procedure_id,
                    name=title,
                    url=procedure_url,
                    publication_date=publication_date,
                    application_deadline=application_deadline,
                ),
                lot=LotSummary(
                    source="fabrikant",
                    external_id=lot_external_id,
                    number=str(index + 1),
                    name=title,
                    url=procedure_url,
                    initial_price=initial_price,
                    current_price=initial_price,
                ),
                organizer=OrganizerInfo(name=organizer_name),
            )
        )

    return items


def _extract_card_field(card_html: str, *labels: str) -> str | None:
    for label in labels:
        pattern = re.compile(
            rf"<div[^>]*>\s*{re.escape(label)}\s*</div>\s*<div[^>]*>(.*?)</div>",
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(card_html)
        if match:
            value = _strip_tags(match.group(1))
            if value:
                return value
    return None


def _extract_card_price(card_html: str) -> str | None:
    match = re.search(
        r"<div[^>]*justify-end[^>]*>\s*(<div[^>]*font-heading[^>]*font-bold[^>]*>.*?</div>)",
        card_html,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        price = _extract_price(_strip_tags(match.group(1)))
        if price:
            return price

    match = re.search(
        r"(<div[^>]*font-heading[^>]*>.*?</div>)\s*</div>\s*<div[^>]*>\s*начальная цена\s*</div>",
        card_html,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        return _extract_price(_strip_tags(match.group(1)))

    if "начальная цена" not in card_html.lower():
        return None

    label_match = re.search(r"начальная цена", card_html, re.IGNORECASE)
    if not label_match:
        return None

    price_match: re.Match[str] | None = None
    for candidate in re.finditer(r"<div[^>]*font-heading[^>]*font-bold[^>]*>(.*?)</div>", card_html, re.IGNORECASE | re.DOTALL):
        if candidate.end() <= label_match.start():
            price_match = candidate
        else:
            break
    if not price_match:
        return None

    price_text = _strip_tags(price_match.group(1))
    if ("RUB" in card_html or "руб" in card_html.lower()) and "RUB" not in price_text.upper():
        price_text = f"{price_text} RUB"
    return _extract_price(price_text)


def _extract_price(text: str | None) -> str | None:
    if not text:
        return None
    candidates = re.findall(r"\d[\d\s\xa0]*(?:[.,]\d{2})?", text)
    normalized_candidates = [_normalize_text(candidate) for candidate in candidates if candidate.strip()]
    if not normalized_candidates:
        return None
    amount = max(normalized_candidates, key=lambda candidate: (sum(char.isdigit() for char in candidate), len(candidate)))
    lowered = text.lower()
    if "rub" in lowered or "руб" in lowered or "рубль" in lowered:
        return f"{amount} RUB"
    return amount


def _extract_html_page_items(html: str) -> list[AuctionListItem]:
    items: list[AuctionListItem] = []
    title_matches = _extract_title_anchor_matches(html)
    for index, match in enumerate(title_matches):
        attrs = match.group("attrs")
        href = _extract_attr(attrs, "href")
        if not href:
            continue
        end = title_matches[index + 1].start() if index + 1 < len(title_matches) else len(html)
        card_html = html[match.start() : end]
        procedure_id = _extract_id(href, PROCEDURE_URL_PREFIX)
        title = _strip_tags(match.group("body"))
        organizer_name = _extract_card_field(card_html, "Организатор")
        publication_date = _extract_card_field(card_html, "Дата публикации")
        application_deadline = _extract_card_field(
            card_html,
            "Дата окончания приёма заявок",
            "Дата окончания приема заявок",
        )
        initial_price = _extract_card_price(card_html)
        if not procedure_id or not title:
            continue

        items.append(
            AuctionListItem(
                source="fabrikant",
                auction=AuctionSummary(
                    source="fabrikant",
                    external_id=procedure_id,
                    number=procedure_id,
                    name=title,
                    url=href,
                    publication_date=publication_date,
                    application_deadline=application_deadline,
                ),
                lot=LotSummary(
                    source="fabrikant",
                    external_id=procedure_id,
                    number="1",
                    name=title,
                    url=href,
                    initial_price=initial_price,
                    current_price=initial_price,
                ),
                organizer=OrganizerInfo(name=organizer_name),
            )
        )

    return items


def _resolve_auction_name(fields: list[ScrapedField], fallback: str) -> str:
    name = _first_matching_field(fields, "Предмет договора", "Название процедуры на ЭТП", "Наименование")
    if name:
        return name
    return fallback


def _extract_organizer_name(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    for marker in ("Полное наименование", "Почтовый адрес", "ИНН", "Контактное лицо", "E-mail", "Телефон"):
        if marker in raw_value:
            prefix = raw_value.split(marker, 1)[0]
            cleaned = _normalize_text(prefix)
            if cleaned:
                return cleaned
    cleaned = _normalize_text(raw_value)
    return cleaned or None


def _extract_location_parts(raw_location: str | None) -> tuple[str | None, str | None, str | None]:
    if not raw_location:
        return None, None, None

    region_match = re.search(
        r"(?:Субъект\s*РФ\\?/?.*?Регион|Регион)\s+(.+?)(?=\s+Адрес:?|$)",
        raw_location,
        re.IGNORECASE,
    )
    address_match = re.search(r"Адрес:?\s+(.+)$", raw_location, re.IGNORECASE)
    region = _normalize_text(region_match.group(1)) if region_match else None
    address = _normalize_text(address_match.group(1)) if address_match else None
    city_match = re.search(r"(?:г\.|город)\s*([^,]+)", address or raw_location, re.IGNORECASE)
    city = _normalize_text(city_match.group(1)) if city_match else None
    return region, city, address


def _join_location_parts(*parts: str | None) -> str | None:
    values: list[str] = []
    for part in parts:
        if not part:
            continue
        normalized = _normalize_text(part)
        if normalized and normalized not in values:
            values.append(normalized)
    if not values:
        return None
    return ", ".join(values)


def _extract_lot_links(auction_id: str, html: str) -> list[tuple[str, str]]:
    pattern = re.compile(
        rf'href="(?P<href>/v2/trades/procedure/lot/view/{re.escape(auction_id)}/(?P<lot_id>[^"/?#]+))"',
        re.IGNORECASE,
    )
    seen: set[str] = set()
    links: list[tuple[str, str]] = []
    for match in pattern.finditer(html):
        lot_id = match.group("lot_id")
        if lot_id in seen:
            continue
        seen.add(lot_id)
        links.append((lot_id, urljoin(BASE_URL, match.group("href"))))
    return links


def _build_auction_summary(
    auction_id: str,
    url: str,
    fields: list[ScrapedField],
    *,
    name: str | None = None,
) -> AuctionSummary:
    return AuctionSummary(
        source="fabrikant",
        external_id=auction_id,
        number=auction_id,
        name=name or _extract_page_title(url, auction_id),
        url=url,
        publication_date=_first_matching_field(fields, "Дата публикации"),
        auction_date=_first_matching_field(fields, "Дата проведения торгов", "Дата начала торгов"),
        application_deadline=_first_matching_field(
            fields,
            "Дата окончания приёма заявок",
            "Дата окончания приема заявок",
        ),
    )


def _build_lot_summary(
    lot_id: str,
    url: str,
    fields: list[ScrapedField],
    *,
    fallback_name: str | None = None,
    external_id: str | None = None,
) -> LotSummary:
    raw_location = _first_matching_field(fields, "Местонахождение объекта продажи")
    region, city, address = _extract_location_parts(raw_location)
    price = _extract_price(_first_matching_field(fields, "Начальная цена предмета договора", "Начальная цена"))
    name = _first_matching_field(fields, "Предмет договора", "Наименование") or fallback_name
    location = _join_location_parts(region, address)
    return LotSummary(
        source="fabrikant",
        external_id=external_id or lot_id,
        number="1",
        name=name,
        url=url,
        location=location,
        region=region,
        city=city,
        address=address,
        initial_price=price,
        current_price=price,
        description=name,
    )


def fetch_auction_list(limit: int | None = 20) -> list[AuctionListItem]:
    auctions: list[AuctionListItem] = []

    seen_lot_ids: set[str] = set()
    page_number = 1

    while limit is None or len(auctions) < limit:
        page_items: list[AuctionListItem] = []
        try:
            page_items = _extract_rsc_page_items(_fetch_search_rsc(page_number))
        except Exception:
            page_items = []

        if not page_items:
            html = _fetch_html(_build_search_url(page_number))
            page_items = _extract_html_page_items(html)

        if not page_items:
            break

        page_added = 0
        for item in page_items:
            if not item.lot.external_id or item.lot.external_id in seen_lot_ids:
                continue

            seen_lot_ids.add(item.lot.external_id)
            page_added += 1
            auctions.append(item)
            if limit is not None and len(auctions) >= limit:
                break

        if limit is not None and len(auctions) >= limit:
            break
        if page_added == 0:
            break
        page_number += 1

    return auctions


def fetch_lot_detail(lot_id: str) -> LotDetailResponse:
    requested_lot_id = lot_id
    procedure_id, explicit_lot_id = _split_lot_external_id(lot_id)
    procedure_url = f"{PROCEDURE_URL_PREFIX}{procedure_id}"
    procedure_html = _fetch_html(procedure_url)
    procedure_fields = _parse_fields(procedure_html)
    procedure_name = _resolve_auction_name(procedure_fields, _extract_page_title(procedure_html, procedure_id))
    lot_links = _extract_lot_links(procedure_id, procedure_html)

    detail_url = procedure_url
    detail_fields = procedure_fields
    detail_lot_id = explicit_lot_id or lot_id
    if explicit_lot_id:
        matching_lot = next((entry for entry in lot_links if entry[0] == explicit_lot_id), None)
        if matching_lot is None and len(lot_links) == 1:
            matching_lot = lot_links[0]
        if matching_lot is not None:
            detail_lot_id, detail_url = matching_lot
            detail_html = _fetch_html(detail_url)
            detail_fields = _parse_fields(detail_html)
    elif len(lot_links) == 1:
        detail_lot_id, detail_url = lot_links[0]
        detail_html = _fetch_html(detail_url)
        detail_fields = _parse_fields(detail_html)
    auction_summary = AuctionSummary(
        source="fabrikant",
        external_id=procedure_id,
        number=procedure_id,
        name=procedure_name,
        url=procedure_url,
        publication_date=_first_matching_field(detail_fields, "Дата публикации")
        or _first_matching_field(procedure_fields, "Дата публикации"),
        auction_date=_first_matching_field(
            procedure_fields,
            "Дата проведения торгов",
            "Дата начала торгов",
            "Дата и время начала аукциона",
        ),
        application_deadline=_first_matching_field(
            procedure_fields,
            "Дата окончания приёма заявок",
            "Дата окончания приема заявок",
            "Дата и время окончания приема заявок",
        ),
    )
    lot_summary = _build_lot_summary(
        detail_lot_id,
        detail_url,
        detail_fields,
        fallback_name=procedure_name,
        external_id=requested_lot_id,
    )

    return LotDetailResponse(
        source="fabrikant",
        url=detail_url,
        auction=auction_summary,
        lot=lot_summary,
        documents=[],
        raw_fields=detail_fields,
        raw_tables=[],
    )


def fetch_auction_detail(auction_id: str) -> AuctionDetailResponse:
    url = f"{PROCEDURE_URL_PREFIX}{auction_id}"
    html = _fetch_html(url)
    fields = _parse_fields(html)
    auction_name = _resolve_auction_name(fields, _extract_page_title(html, auction_id))
    lot_links = _extract_lot_links(auction_id, html)

    lots = [
        LotSummary(
            source="fabrikant",
            external_id=_compose_lot_external_id(auction_id, lot_id),
            number=str(index),
            url=lot_url,
        )
        for index, (lot_id, lot_url) in enumerate(lot_links, start=1)
    ]
    if not lots:
        lots = [LotSummary(source="fabrikant", external_id=auction_id, number="1", name=auction_name, url=url)]

    organizer = OrganizerInfo(
        name=_extract_organizer_name(
            _first_matching_field(fields, "Информация об организаторе", "Организатор", "Наименование организатора")
        ),
        phone=_first_matching_field(fields, "Телефон", "Контактный телефон"),
    )

    return AuctionDetailResponse(
        source="fabrikant",
        url=url,
        auction=AuctionSummary(
            source="fabrikant",
            external_id=auction_id,
            number=auction_id,
            name=auction_name,
            url=url,
            publication_date=_first_matching_field(fields, "Дата публикации"),
            auction_date=_first_matching_field(
                fields,
                "Дата проведения торгов",
                "Дата начала торгов",
                "Дата и время начала аукциона",
            ),
            application_deadline=_first_matching_field(
                fields,
                "Дата окончания приёма заявок",
                "Дата окончания приема заявок",
                "Дата и время окончания приема заявок",
            ),
        ),
        organizer=organizer,
        debtor=DebtorInfo(
            name=_first_matching_field(fields, "Должник", "Наименование должника"),
            inn=_first_matching_field(fields, "ИНН"),
        ),
        lots=lots,
        documents=[],
        raw_fields=fields,
        raw_tables=[],
    )


def fetch_auction_publication_date(auction_id: str, timeout: int = 8) -> str | None:
    url = f"{PROCEDURE_URL_PREFIX}{auction_id}"
    html = _fetch_html(url, timeout=timeout)
    fields = _parse_fields(html)
    return _first_matching_field(fields, "Дата публикации")