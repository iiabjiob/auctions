from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass, field
from collections.abc import Iterable
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from app.core.config import get_settings
from app.schemas.procurements import ProcurementLotItem, ProcurementSourceInfo
from app.services.procurement_values import parse_money
from app.services.source_http_diagnostics import record_source_http_exchange


BASE_URL = "https://zakupki.gov.ru"
SEARCH_PATH = "/epz/order/extendedsearch/results.html"
DEFAULT_RECORDS_PER_PAGE = 50
DEFAULT_SEARCH_KEYWORDS = (
    "спецодежда",
    "специальная одежда",
    "рабочая одежда",
    "медицинская одежда",
    "халат медицинский",
    "костюм медицинский",
    "спортивная форма",
    "униформа",
    "форменная одежда",
    "пошив одежды",
)
DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.6",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SearchParseDiagnostics:
    total_chunks: int = 0
    parsed_items: int = 0
    skipped_chunks: int = 0
    missing_required_fields: dict[str, int] = field(default_factory=dict)

    def record_missing(self, field_name: str) -> None:
        self.missing_required_fields[field_name] = self.missing_required_fields.get(field_name, 0) + 1


@dataclass(slots=True)
class ParsedSearchResults:
    items: list[ProcurementLotItem]
    diagnostics: SearchParseDiagnostics


def source_info() -> ProcurementSourceInfo:
    return ProcurementSourceInfo(code="zakupki", title="ЕИС Закупки", website=BASE_URL)


def iter_procurement_list(
    *,
    limit: int | None = None,
    start_page: int = 1,
    records_per_page: int = DEFAULT_RECORDS_PER_PAGE,
    search_keywords: tuple[str, ...] | list[str] | None = None,
    timeout: int = 30,
) -> Iterable[ProcurementLotItem]:
    yielded = 0
    seen_external_ids: set[str] = set()
    for keyword in _search_keyword_queries(search_keywords):
        page = max(1, start_page)
        while limit is None or yielded < limit:
            html_text = fetch_search_page(
                page=page,
                records_per_page=records_per_page,
                search_keywords=(keyword,),
                timeout=timeout,
            )
            result = parse_search_results_with_diagnostics(html_text)
            _log_parse_diagnostics(page=page, diagnostics=result.diagnostics)
            items = result.items
            if not items:
                break
            for item in items:
                if item.external_id in seen_external_ids:
                    continue
                seen_external_ids.add(item.external_id)
                yield item
                yielded += 1
                if limit is not None and yielded >= limit:
                    return
            page += 1


def _search_keyword_queries(search_keywords: tuple[str, ...] | list[str] | None = None) -> tuple[str, ...]:
    keywords = tuple(search_keywords or DEFAULT_SEARCH_KEYWORDS)
    return tuple(dict.fromkeys(keyword.strip() for keyword in keywords if keyword.strip()))


def fetch_procurement_list(
    limit: int | None = None,
    *,
    page: int = 1,
    search_keywords: tuple[str, ...] | list[str] | None = None,
) -> list[ProcurementLotItem]:
    return list(iter_procurement_list(limit=limit, start_page=page, search_keywords=search_keywords))


def fetch_search_page(
    *,
    page: int = 1,
    records_per_page: int = DEFAULT_RECORDS_PER_PAGE,
    search_keywords: tuple[str, ...] | list[str] | None = None,
    timeout: int = 30,
) -> str:
    params = build_search_params(page=page, records_per_page=records_per_page, search_keywords=search_keywords)
    logger.info(
        "Fetching zakupki search page",
        extra={
            "page": page,
            "records_per_page": records_per_page,
            "search_keywords": list(search_keywords or DEFAULT_SEARCH_KEYWORDS),
        },
    )
    gateway_response = fetch_search_page_via_gateway(params=params, timeout=timeout)
    if gateway_response is not None:
        return gateway_response

    url = f"{BASE_URL}{SEARCH_PATH}?{urlencode(params)}"
    logger.info("Fetching zakupki search page directly", extra={"url": url})
    return fetch_html_url(url, operation="search_page", timeout=timeout)


def fetch_lot_detail_page(url: str, *, timeout: int = 30) -> dict:
    html_text = fetch_html_url(url, operation="lot_detail", timeout=timeout)
    return parse_lot_detail_page(html_text, url=url)


def fetch_documents_page(url: str, *, timeout: int = 30) -> list[dict]:
    html_text = fetch_html_url(url, operation="documents", timeout=timeout)
    return parse_documents_page(html_text, url=url)


def fetch_html_url(url: str, *, operation: str, timeout: int = 30) -> str:
    gateway_response = fetch_url_via_gateway(url, operation=operation, timeout=timeout)
    if gateway_response is not None:
        return gateway_response

    started_at = datetime.now(UTC)
    status_code: int | None = None
    response_bytes = 0
    error: BaseException | None = None
    request = Request(url, headers=DEFAULT_HEADERS)
    try:
        with urlopen(request, timeout=timeout) as response:
            status_code = getattr(response, "status", None)
            body = response.read()
            response_bytes = len(body)
            return body.decode(_response_encoding(response.headers.get("Content-Type")), "replace")
    except BaseException as exc:
        error = exc
        status_code = getattr(exc, "code", status_code)
        raise
    finally:
        record_source_http_exchange(
            source_code="zakupki",
            operation=operation,
            method="GET",
            url=url,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            status_code=status_code,
            request_bytes=0,
            response_bytes=response_bytes,
            error=error,
        )


def fetch_url_via_gateway(url: str, *, operation: str, timeout: int = 30) -> str | None:
    settings = get_settings()
    gateway_url = (settings.zakupki_fetch_gateway_url or "").strip()
    token = (settings.zakupki_fetch_token or "").strip()
    if not gateway_url:
        return None
    if not token:
        raise RuntimeError("ZAKUPKI_FETCH_TOKEN is required when ZAKUPKI_FETCH_GATEWAY_URL is configured")

    parsed = urlparse(url)
    if parsed.netloc and parsed.netloc != "zakupki.gov.ru":
        return None
    payload = json.dumps(
        {
            "method": "GET",
            "path": parsed.path or url,
            "params": dict(parse_qsl(parsed.query, keep_blank_values=True)),
            "headers": DEFAULT_HEADERS,
        }
    ).encode("utf-8")
    gateway_endpoint = urljoin(f"{gateway_url.rstrip('/')}/", "fetch")
    request = Request(
        gateway_endpoint,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    started_at = datetime.now(UTC)
    gateway_status_code: int | None = None
    response_bytes = 0
    error: BaseException | None = None
    try:
        with urlopen(request, timeout=timeout or settings.zakupki_fetch_timeout_seconds) as response:
            gateway_status_code = getattr(response, "status", None)
            body = response.read()
            response_bytes = len(body)
            response_payload = json.loads(body.decode("utf-8"))
    except BaseException as exc:
        error = exc
        gateway_status_code = getattr(exc, "code", gateway_status_code)
        raise
    finally:
        record_source_http_exchange(
            source_code="zakupki",
            operation=f"{operation}_gateway",
            method="POST",
            url=gateway_endpoint,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            status_code=gateway_status_code,
            request_bytes=len(payload),
            response_bytes=response_bytes,
            error=error,
        )
    status = int(response_payload.get("status") or 0)
    if status < 200 or status >= 300:
        raise RuntimeError(f"Zakupki fetch gateway returned HTTP {status}")
    if response_payload.get("body_base64"):
        raise RuntimeError("Zakupki fetch gateway returned binary response")
    return str(response_payload.get("body") or "")


def fetch_search_page_via_gateway(*, params: dict[str, str | int], timeout: int = 30) -> str | None:
    settings = get_settings()
    gateway_url = (settings.zakupki_fetch_gateway_url or "").strip()
    token = (settings.zakupki_fetch_token or "").strip()
    if not gateway_url:
        return None
    if not token:
        raise RuntimeError("ZAKUPKI_FETCH_TOKEN is required when ZAKUPKI_FETCH_GATEWAY_URL is configured")

    payload = json.dumps(
        {
            "method": "GET",
            "path": SEARCH_PATH,
            "params": params,
            "headers": DEFAULT_HEADERS,
        }
    ).encode("utf-8")
    request = Request(
        urljoin(f"{gateway_url.rstrip('/')}/", "fetch"),
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    started_at = datetime.now(UTC)
    gateway_status_code: int | None = None
    response_bytes = 0
    error: BaseException | None = None
    gateway_endpoint = urljoin(f"{gateway_url.rstrip('/')}/", "fetch")
    try:
        with urlopen(request, timeout=timeout or settings.zakupki_fetch_timeout_seconds) as response:
            gateway_status_code = getattr(response, "status", None)
            body = response.read()
            response_bytes = len(body)
            response_payload = json.loads(body.decode("utf-8"))
    except BaseException as exc:
        error = exc
        gateway_status_code = getattr(exc, "code", gateway_status_code)
        raise
    finally:
        record_source_http_exchange(
            source_code="zakupki",
            operation="search_page_gateway",
            method="POST",
            url=gateway_endpoint,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            status_code=gateway_status_code,
            request_bytes=len(payload),
            response_bytes=response_bytes,
            error=error,
        )

    status = int(response_payload.get("status") or 0)
    logger.info(
        "Fetched zakupki page via gateway",
        extra={
            "gateway_url": gateway_url,
            "target_path": SEARCH_PATH,
            "status": status,
            "elapsed_ms": response_payload.get("elapsed_ms"),
            "body_length": len(str(response_payload.get("body") or "")),
            "truncated": bool(response_payload.get("truncated")),
        },
    )
    if status < 200 or status >= 300:
        raise RuntimeError(f"Zakupki fetch gateway returned HTTP {status}")
    if response_payload.get("body_base64"):
        raise RuntimeError("Zakupki fetch gateway returned binary response")
    return str(response_payload.get("body") or "")


def parse_lot_detail_page(html_text: str, *, url: str) -> dict:
    title = _first_match_text(html_text, r"<h1[^>]*>(.*?)</h1>") or _first_match_text(html_text, r"<title[^>]*>(.*?)</title>")
    fields = _extract_detail_fields(html_text)
    text = _clean_html(html_text)
    return {
        "url": url,
        "title": title,
        "fields": fields,
        "text_excerpt": text[:8000],
        "html_length": len(html_text),
    }


def parse_documents_page(html_text: str, *, url: str) -> list[dict]:
    documents: list[dict] = []
    for href, label in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html_text, re.S | re.I):
        clean_label = _clean_html(label)
        absolute_href = _absolute_url(html.unescape(href))
        if not clean_label and not re.search(r"\.(?:docx?|xlsx?|pdf|zip|rar)(?:\?|$)", absolute_href, re.I):
            continue
        if not _looks_like_document_link(absolute_href, clean_label):
            continue
        documents.append(
            {
                "title": clean_label or absolute_href.rsplit("/", 1)[-1],
                "url": absolute_href,
                "source_url": url,
            }
        )
    seen: set[str] = set()
    unique_documents: list[dict] = []
    for document in documents:
        document_url = str(document.get("url") or "")
        if document_url in seen:
            continue
        seen.add(document_url)
        unique_documents.append(document)
    return unique_documents[:200]


def build_search_url(
    *,
    page: int = 1,
    records_per_page: int = DEFAULT_RECORDS_PER_PAGE,
    search_keywords: tuple[str, ...] | list[str] | None = None,
) -> str:
    params = build_search_params(page=page, records_per_page=records_per_page, search_keywords=search_keywords)
    return f"{BASE_URL}{SEARCH_PATH}?{urlencode(params)}"


def build_search_params(
    *,
    page: int = 1,
    records_per_page: int = DEFAULT_RECORDS_PER_PAGE,
    search_keywords: tuple[str, ...] | list[str] | None = None,
) -> dict[str, str | int]:
    keywords = tuple(search_keywords or DEFAULT_SEARCH_KEYWORDS)
    params: dict[str, str | int] = {
        "morphology": "on",
        "search-filter": "Дате размещения",
        "searchString": " ".join(keyword.strip() for keyword in keywords if keyword.strip()),
        "pageNumber": page,
        "sortDirection": "false",
        "recordsPerPage": f"_{records_per_page}",
        "showLotsInfoHidden": "false",
        "sortBy": "UPDATE_DATE",
        "fz44": "on",
        "fz223": "on",
    }
    return params


def parse_search_results(html_text: str) -> list[ProcurementLotItem]:
    return parse_search_results_with_diagnostics(html_text).items


def parse_search_results_with_diagnostics(html_text: str) -> ParsedSearchResults:
    chunks = _entry_chunks(html_text)
    diagnostics = SearchParseDiagnostics(total_chunks=len(chunks))
    items: list[ProcurementLotItem] = []
    for chunk in chunks:
        item = _parse_entry(chunk, diagnostics=diagnostics)
        if item is not None:
            items.append(item)
            diagnostics.parsed_items += 1
        else:
            diagnostics.skipped_chunks += 1
    return ParsedSearchResults(items=items, diagnostics=diagnostics)


def _entry_chunks(html_text: str) -> list[str]:
    starts = [match.start() for match in re.finditer(r"registry-entry__header-mid__number", html_text)]
    chunks: list[str] = []
    for index, start in enumerate(starts):
        chunk_start = max(0, html_text.rfind("<div", 0, start))
        next_start = starts[index + 1] if index + 1 < len(starts) else len(html_text)
        chunks.append(html_text[chunk_start:next_start])
    return chunks


def _parse_entry(chunk: str, *, diagnostics: SearchParseDiagnostics | None = None) -> ProcurementLotItem | None:
    number_match = re.search(
        r'<div class="registry-entry__header-mid__number">\s*<a[^>]+href="([^"]+)"[^>]*>\s*№\s*([0-9]+)\s*</a>',
        chunk,
        re.S,
    )
    if not number_match:
        if diagnostics is not None:
            diagnostics.record_missing("registry_number")
        return None

    notice_url = _absolute_url(html.unescape(number_match.group(1)))
    registry_number = number_match.group(2)
    raw_fields = _extract_body_fields(chunk)
    title = raw_fields.get("Объект закупки") or raw_fields.get("Наименование закупки")
    status = _first_match_text(chunk, r'registry-entry__header-mid__title[^>]*>\s*(.*?)\s*</div>')
    price = _first_body_value(raw_fields, "Начальная цена", "Начальная (максимальная) цена контракта")
    price = price or _extract_price_block(chunk)
    customer = _first_body_value(raw_fields, "Заказчик", "Организация, осуществляющая размещение")
    customer_inn = _extract_customer_inn(chunk, notice_url=notice_url)
    organizer = _first_body_value(raw_fields, "Организация, осуществляющая размещение", "Размещено")
    procedure_type = _first_body_value(raw_fields, "Способ определения поставщика", "Способ закупки")
    platform = _first_body_value(raw_fields, "Электронная площадка")
    region = _first_body_value(raw_fields, "Регион")
    delivery_region = _first_body_value(raw_fields, "Место поставки", "Регион поставки")
    delivery_address = _first_body_value(raw_fields, "Адрес поставки", "Место поставки")
    publication_date = _extract_labeled_datetime(chunk, "Размещено")
    application_deadline = _extract_labeled_datetime(chunk, "Окончание подачи заявок")
    documents_url = _extract_documents_url(chunk, notice_url=notice_url)

    if diagnostics is not None:
        for field_name, value in (
            ("title", title),
            ("status", status),
            ("customer_name", customer),
            ("initial_price", price),
            ("application_deadline", application_deadline),
        ):
            if not value:
                diagnostics.record_missing(field_name)

    return ProcurementLotItem(
        source="zakupki",
        external_id=registry_number,
        registry_number=registry_number,
        law=_detect_law(notice_url),
        title=title,
        status=status,
        customer_name=customer,
        customer_inn=customer_inn,
        organizer_name=organizer if organizer != customer else None,
        procedure_type=procedure_type,
        platform_name=platform,
        region=region,
        delivery_region=delivery_region,
        delivery_address=delivery_address,
        initial_price=price,
        initial_price_value=parse_money(price),
        currency="RUB" if price and ("₽" in price or "8381" in price or "руб" in price.lower()) else None,
        publication_date=publication_date,
        application_deadline=application_deadline,
        notice_url=notice_url,
        print_url=_extract_print_url(chunk),
        documents_url=documents_url,
        specification_url=documents_url,
        documentation_present=bool(documents_url),
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


def _extract_detail_fields(html_text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for match in re.finditer(
        r'<span[^>]*class="[^"]*(?:section__title|blockInfo__title|cardMainInfo__title)[^"]*"[^>]*>(.*?)</span>'
        r'.{0,1200}?<span[^>]*class="[^"]*(?:section__info|blockInfo__info|cardMainInfo__content)[^"]*"[^>]*>(.*?)</span>',
        html_text,
        re.S | re.I,
    ):
        key = _clean_html(match.group(1)).rstrip(":")
        value = _clean_html(match.group(2))
        if key and value:
            fields[key] = value
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, re.S | re.I):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)
        if len(cells) >= 2:
            key = _clean_html(cells[0]).rstrip(":")
            value = _clean_html(cells[1])
            if key and value and len(key) < 180:
                fields.setdefault(key, value)
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


def _extract_documents_url(chunk: str, *, notice_url: str) -> str | None:
    match = re.search(r'href="([^"]*(?:documents|doc|view/doc)[^"]*)"', chunk, re.I)
    if match:
        return _absolute_url(html.unescape(match.group(1)))
    if "/common-info.html" in notice_url:
        return notice_url.replace("/common-info.html", "/documents.html")
    return None


def _extract_customer_inn(chunk: str, *, notice_url: str) -> str | None:
    for value in (chunk, notice_url):
        match = re.search(r"[?&]inn=(\d{10}|\d{12})(?:&|$)", html.unescape(value))
        if match:
            return match.group(1)
    match = re.search(r"\bИНН\b[^0-9]{0,20}(\d{10}|\d{12})", _clean_html(chunk), re.I)
    return match.group(1) if match else None


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


def _looks_like_document_link(url: str, label: str) -> bool:
    haystack = f"{url} {label}".lower()
    return any(marker in haystack for marker in ("document", "download", "file", "doc", "pdf", "xlsx", "zip", "прикреп", "документ"))


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


def _log_parse_diagnostics(*, page: int, diagnostics: SearchParseDiagnostics) -> None:
    logger.info(
        "Parsed zakupki search page",
        extra={
            "page": page,
            "total_chunks": diagnostics.total_chunks,
            "parsed_items": diagnostics.parsed_items,
            "skipped_chunks": diagnostics.skipped_chunks,
            "missing_required_fields": diagnostics.missing_required_fields,
        },
    )
    if diagnostics.skipped_chunks or diagnostics.missing_required_fields:
        logger.info(
            "Parsed zakupki search page with missing fields",
            extra={
                "page": page,
                "total_chunks": diagnostics.total_chunks,
                "parsed_items": diagnostics.parsed_items,
                "skipped_chunks": diagnostics.skipped_chunks,
                "missing_required_fields": diagnostics.missing_required_fields,
            },
        )
