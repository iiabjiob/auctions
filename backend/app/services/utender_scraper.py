from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from app.schemas.auctions import (
    AuctionDetailResponse,
    AuctionDocument,
    AuctionListItem,
    AuctionSummary,
    DebtorInfo,
    LotDetailResponse,
    LotSummary,
    OrganizerInfo,
    ScrapedField,
)


BASE_URL = "http://utender.ru"
AUCTIONS_LIST_URL = f"{BASE_URL}/public/auctions-all/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def _fetch_html(url: str, timeout: int = 20) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        encoding = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(encoding, errors="replace")


def _post_html(url: str, form_data: dict[str, str], timeout: int = 20) -> str:
    encoded = urlencode(form_data).encode("utf-8")
    request = Request(
        url,
        data=encoded,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        encoding = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(encoding, errors="replace")


class UtenderTableParser(HTMLParser):
    def __init__(self, content_headings: set[str] | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.content_headings = content_headings or set()
        self.rows: list[list[dict[str, Any]]] = []
        self.headings: list[str] = []
        self.content_headings_found: list[str] = []
        self._current_row: list[dict[str, Any]] | None = None
        self._current_cell: dict[str, Any] | None = None
        self._current_heading: list[str] | None = None
        self._active_href: str | None = None
        self._content_started = not self.content_headings

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "tr":
            self._current_row = []
        elif tag in {"td", "th"} and self._current_row is not None:
            self._current_cell = {"text_parts": [], "links": []}
        elif tag == "a" and self._current_cell is not None:
            href = attributes.get("href")
            if href:
                absolute_href = urljoin(BASE_URL, href)
                self._current_cell["links"].append(absolute_href)
                self._active_href = absolute_href
        elif tag in {"h1", "h2", "h3", "h4"}:
            self._current_heading = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "tr" and self._current_row is not None:
            if self._current_row and self._content_started:
                self.rows.append(self._current_row)
            self._current_row = None
        elif tag in {"td", "th"} and self._current_row is not None and self._current_cell is not None:
            text = _normalize_text(" ".join(self._current_cell["text_parts"]))
            self._current_row.append({"text": text, "links": self._current_cell["links"]})
            self._current_cell = None
        elif tag == "a":
            self._active_href = None
        elif tag in {"h1", "h2", "h3", "h4"} and self._current_heading is not None:
            heading = _normalize_text(" ".join(self._current_heading))
            if heading:
                self.headings.append(heading)
                if heading in self.content_headings:
                    self._content_started = True
                    self.content_headings_found.append(heading)
            self._current_heading = None

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell["text_parts"].append(data)
        if self._current_heading is not None:
            self._current_heading.append(data)


class UtenderFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden_inputs: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "input":
            return

        attributes = dict(attrs)
        if attributes.get("type") != "hidden":
            return

        name = attributes.get("name")
        if name:
            self.hidden_inputs[name] = attributes.get("value") or ""


def _parse_html(html: str, content_headings: set[str] | None = None) -> UtenderTableParser:
    parser = UtenderTableParser(content_headings=content_headings)
    parser.feed(html)
    return parser


def _parse_hidden_inputs(html: str) -> dict[str, str]:
    parser = UtenderFormParser()
    parser.feed(html)
    return parser.hidden_inputs


def _extract_pager_links(html: str) -> list[tuple[str, str]]:
    html = unescape(html)
    pattern = re.compile(r'__doPostBack\(\'([^\']+)\',\'\'\)">\s*([^<]+?)\s*</a>')
    return [(target, _normalize_text(label)) for target, label in pattern.findall(html)]


def _extract_next_page_target(html: str, next_page_number: int) -> str | None:
    for target, label in _extract_pager_links(html):
        if label == str(next_page_number):
            return target
    for target, label in _extract_pager_links(html):
        if label == ">>":
            return target
    return None


def _extract_id(url: str, pattern: str) -> str | None:
    match = re.search(pattern, url)
    return match.group(1) if match else None


def _extract_auction_number(html: str) -> str | None:
    match = re.search(r"(?:аукционе|аукциона)\s*№\s*(\d{7})", html, re.IGNORECASE)
    return match.group(1) if match else None


def _build_raw_fields(rows: list[list[dict[str, Any]]]) -> list[ScrapedField]:
    fields: list[ScrapedField] = []
    for row in rows:
        index = 0
        while index + 1 < len(row):
            label = _normalize_text(row[index]["text"]).rstrip(":")
            value = _normalize_text(row[index + 1]["text"])
            if label and value and label not in {"---", "№"}:
                fields.append(ScrapedField(name=label, value=value))
            index += 2
    return fields


def _raw_tables(rows: list[list[dict[str, Any]]]) -> list[list[str]]:
    return [[cell["text"] for cell in row if cell["text"]] for row in rows if any(cell["text"] for cell in row)]


def _first_field(fields: list[ScrapedField], name: str) -> str | None:
    for field in fields:
        if field.name == name:
            return field.value
    return None


def _first_matching_field(fields: list[ScrapedField], *names: str) -> str | None:
    normalized_names = {_normalize_text(name).rstrip(":").lower() for name in names}
    for field in fields:
        field_name = _normalize_text(field.name).rstrip(":").lower()
        if field_name in normalized_names:
            return field.value
    return None


def _fields_after(fields: list[ScrapedField], marker: str) -> list[ScrapedField]:
    for index, field in enumerate(fields):
        if field.name == marker:
            return fields[index:]
    return fields


def _parse_documents(rows: list[list[dict[str, Any]]]) -> list[AuctionDocument]:
    documents: list[AuctionDocument] = []
    for row in rows:
        texts = [cell["text"] for cell in row]
        if len(texts) < 5 or not re.fullmatch(r"\d+", texts[0]):
            continue
        if not re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", texts[1]):
            continue

        document_url = next((link for cell in row for link in cell["links"]), None)

        documents.append(
            AuctionDocument(
                external_id=texts[0],
                received_at=texts[1],
                name=texts[2],
                url=document_url,
                signature_status=texts[3],
                comment=texts[4] if len(texts) >= 6 else None,
                document_type=texts[5] if len(texts) >= 6 else texts[4],
            )
        )
    return documents


def _parse_lots_from_auction_tables(tables: list[list[str]]) -> list[LotSummary]:
    lots: list[LotSummary] = []
    for row in tables:
        if len(row) != 5 or not row[0].isdigit():
            continue
        if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", row[1]):
            continue
        lots.append(
            LotSummary(
                number=row[0],
                name=row[1],
                currency=row[2],
                initial_price=row[3],
                status=row[4],
            )
        )
    return lots


def _build_auction_summary(
    fields: list[ScrapedField],
    *,
    external_id: str | None = None,
    number: str | None = None,
    url: str | None = None,
) -> AuctionSummary:
    return AuctionSummary(
        external_id=external_id,
        number=number,
        name=_first_field(fields, "Наименование"),
        url=url,
        publication_date=_first_matching_field(
            fields,
            "Дата публикации сообщения",
            "Дата размещения сообщения в ЕФРСБ",
            "Дата публикации сообщения о проведении открытых торгов в официальном издании",
            "Дата размещения сообщения в Едином федеральном реестре сведений о банкротстве",
        ),
        participant_form=_first_field(fields, "Форма торга по составу участников"),
        price_offer_form=_first_field(fields, "Форма представления предложений о цене"),
        auction_date=_first_field(fields, "Дата проведения"),
        application_start=_first_field(fields, "Дата начала представления заявок на участие"),
        application_deadline=_first_field(fields, "Дата окончания представления заявок на участие"),
        winner_selection_order=_first_field(fields, "Порядок и критерии определения победителя торгов"),
        application_order=_first_field(fields, "Порядок представления заявок на участие в торгах"),
        repeat=_first_field(fields, "Повторные торги"),
        efrsb_message_number=_first_field(fields, "Номер сообщения в ЕФРСБ"),
    )


def _build_lot_summary(
    fields: list[ScrapedField],
    *,
    external_id: str | None = None,
    url: str | None = None,
) -> LotSummary:
    lot_fields = _fields_after(fields, "Номер")
    return LotSummary(
        external_id=external_id,
        number=_first_field(lot_fields, "Номер"),
        name=_first_field(lot_fields, "Наименование"),
        url=url,
        category=_first_field(lot_fields, "Категория лота"),
        classifier=_first_field(lot_fields, "Классификатор ЕФРСБ"),
        currency=_first_field(lot_fields, "Валюта цены по ОКВ"),
        initial_price=_first_field(lot_fields, "Начальная цена, руб."),
        status=_first_field(lot_fields, "Статус"),
        step_percent=_first_field(lot_fields, "Шаг, % от начальной цены"),
        step_amount=_first_field(lot_fields, "Шаг, руб."),
        deposit_amount=_first_field(fields, "Размер задатка, руб."),
        deposit_method=_first_field(fields, "Способ расчета обеспечения"),
        deposit_payment_date=_first_field(fields, "Дата внесения задатка"),
        deposit_return_date=_first_field(fields, "Дата возврата задатка"),
        deposit_order=_first_field(fields, "Порядок внесения и возврата задатка"),
        applications_count=_first_field(lot_fields, "Всего подано заявок на участие"),
        description=_first_field(lot_fields, "Сведения об имуществе должника, его составе, характеристиках, описание, порядок ознакомления"),
        inspection_order=_first_field(lot_fields, "Порядок ознакомления с имуществом"),
    )


def _build_organizer(fields: list[ScrapedField]) -> OrganizerInfo:
    return OrganizerInfo(
        name=_first_field(fields, "Сокращенное наименование"),
        inn=_first_field(fields, "ИНН"),
        website=_first_field(fields, "Адрес сайта"),
        contact_name=_first_field(fields, "Ф.И.О."),
        phone=_first_field(fields, "Телефон"),
        fax=_first_field(fields, "Факс"),
    )


def _build_debtor(fields: list[ScrapedField]) -> DebtorInfo:
    debtor_fields = _fields_after(fields, "Тип должника")
    return DebtorInfo(
        debtor_type=_first_field(debtor_fields, "Тип должника"),
        name=_first_field(debtor_fields, "ФИО должника") or _first_field(debtor_fields, "Наименование должника"),
        inn=_first_field(debtor_fields, "ИНН"),
        snils=_first_field(debtor_fields, "СНИЛС"),
        bankruptcy_case_number=_first_field(debtor_fields, "Номер дела о банкротстве"),
        arbitration_court=_first_field(debtor_fields, "Наименование арбитражного суда"),
        arbitration_manager=_first_field(debtor_fields, "Арбитражный управляющий"),
        managers_organization=_first_field(debtor_fields, "Наименование организации арбитражных управляющих"),
        region=_first_field(debtor_fields, "Регион"),
    )


def fetch_auction_list(limit: int | None = 20) -> list[AuctionListItem]:
    html = _fetch_html(AUCTIONS_LIST_URL)
    auctions: list[AuctionListItem] = []
    page_number = 1

    while limit is None or len(auctions) < limit:
        parser = _parse_html(html)

        for row in parser.rows:
            if len(row) < 9 or not re.fullmatch(r"\d{7}", row[0]["text"]):
                continue

            auction_url = next(
                (link for link in row[0]["links"] + row[1]["links"] if "/public/auctions/view/" in link),
                None,
            )
            lot_url = next((link for link in row[2]["links"] if "/public/auctions/lots/view/" in link), None)

            auctions.append(
                AuctionListItem(
                    auction=AuctionSummary(
                        external_id=_extract_id(auction_url or "", r"/auctions/view/(\d+)/"),
                        number=row[0]["text"],
                        name=row[1]["text"],
                        url=auction_url,
                        auction_date=row[7]["text"],
                        application_deadline=row[6]["text"],
                    ),
                    lot=LotSummary(
                        external_id=_extract_id(lot_url or "", r"/lots/view/(\d+)/"),
                        number=row[2]["text"],
                        name=row[3]["text"],
                        url=lot_url,
                        initial_price=row[4]["text"],
                        status=row[8]["text"],
                    ),
                    organizer=OrganizerInfo(name=row[5]["text"]),
                    winner=row[9]["text"] if len(row) > 9 else None,
                )
            )
            if limit is not None and len(auctions) >= limit:
                break

        if limit is not None and len(auctions) >= limit:
            break

        page_number += 1
        next_target = _extract_next_page_target(html, page_number)
        if not next_target:
            break

        form_data = _parse_hidden_inputs(html)
        form_data["__EVENTTARGET"] = next_target
        form_data["__EVENTARGUMENT"] = ""
        html = _post_html(AUCTIONS_LIST_URL, form_data)

    return auctions


def fetch_lot_detail(lot_id: str) -> LotDetailResponse:
    url = f"{BASE_URL}/public/auctions/lots/view/{lot_id}/"
    html = _fetch_html(url)
    parser = _parse_detail_html(html)
    fields = _build_raw_fields(parser.rows)
    tables = _raw_tables(parser.rows)
    auction_url_match = re.search(r"/public/auctions/view/(\d+)/", html)
    auction_id = auction_url_match.group(1) if auction_url_match else None

    return LotDetailResponse(
        url=url,
        auction=_build_auction_summary(
            fields,
            external_id=auction_id,
            number=_extract_auction_number(html),
            url=f"{BASE_URL}/public/auctions/view/{auction_id}/" if auction_id else None,
        ),
        lot=_build_lot_summary(fields, external_id=lot_id, url=url),
        documents=_parse_documents(parser.rows),
        raw_fields=fields,
        raw_tables=tables,
    )


def fetch_auction_detail(auction_id: str) -> AuctionDetailResponse:
    url = f"{BASE_URL}/public/auctions/view/{auction_id}/"
    html = _fetch_html(url)
    parser = _parse_detail_html(html)
    fields = _build_raw_fields(parser.rows)
    tables = _raw_tables(parser.rows)

    return AuctionDetailResponse(
        url=url,
        auction=_build_auction_summary(
            fields,
            external_id=auction_id,
            number=_extract_auction_number(html),
            url=url,
        ),
        organizer=_build_organizer(fields),
        debtor=_build_debtor(fields),
        lots=_parse_lots_from_auction_tables(tables),
        documents=_parse_documents(parser.rows),
        raw_fields=fields,
        raw_tables=tables,
    )


def fetch_auction_publication_date(auction_id: str, timeout: int = 8) -> str | None:
    url = f"{BASE_URL}/public/auctions/view/{auction_id}/"
    html = _fetch_html(url, timeout=timeout)
    parser = _parse_detail_html(html)
    fields = _build_raw_fields(parser.rows)
    return _first_matching_field(
        fields,
        "Дата публикации сообщения",
        "Дата размещения сообщения в ЕФРСБ",
        "Дата публикации сообщения о проведении открытых торгов в официальном издании",
        "Дата размещения сообщения в Едином федеральном реестре сведений о банкротстве",
    )


def _parse_detail_html(html: str) -> UtenderTableParser:
    return _parse_html(
        html,
        content_headings={
            "Информация о лоте",
            "Извещение о проведении торгов в электронной форме",
        },
    )


def fetch_detail_by_url(url: str) -> dict[str, Any]:
    html = _fetch_html(url)
    parser = _parse_html(
        html,
        content_headings={
            "Информация о лоте",
            "Извещение о проведении торгов в электронной форме",
        },
    )

    fields: list[dict[str, str]] = []
    tables: list[list[str]] = []
    for row in parser.rows:
        texts = [cell["text"] for cell in row if cell["text"]]
        if not texts:
            continue
        tables.append(texts)

        index = 0
        while index + 1 < len(row):
            label = _normalize_text(row[index]["text"]).rstrip(":")
            value = _normalize_text(row[index + 1]["text"])
            if label and value and label not in {"---", "№"}:
                fields.append({"name": label, "value": value})
            index += 2

    return {
        "source": "utender",
        "url": url,
        "headings": parser.content_headings_found or parser.headings,
        "fields": fields,
        "tables": tables,
    }