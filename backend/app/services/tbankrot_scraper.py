from __future__ import annotations

import os
import re
import socket
import time
from http.cookiejar import CookieJar
from html import unescape
from urllib.error import URLError
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener

from app.schemas.auctions import (
    AuctionListItem,
    AuctionDocument,
    AuctionSummary,
    DebtorInfo,
    LotImage,
    LotDetailResponse,
    LotSummary,
    OrganizerInfo,
    PriceScheduleStep,
    ScrapedField,
)


BASE_URL = "https://tbankrot.ru"
AUCTIONS_LIST_URL = f"{BASE_URL}/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
DEFAULT_REQUEST_TIMEOUT = 45
REQUEST_RETRY_ATTEMPTS = 3
REQUEST_RETRY_BACKOFF_SECONDS = 1.5
_COOKIE_JAR = CookieJar()
_OPENER = build_opener(HTTPCookieProcessor(_COOKIE_JAR))
_AUTHENTICATED = False


class TBankrotAuthError(RuntimeError):
    pass


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def _is_masked(value: str | None) -> bool:
    return bool(value and "▒" in value)


def _strip_tags(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", unescape(fragment))
    return _normalize_text(text)


def _strip_tags_with_breaks(fragment: str) -> str:
    prepared = re.sub(r"<\s*br\s*/?\s*>", "\n", fragment, flags=re.IGNORECASE)
    prepared = re.sub(r"</\s*(?:p|div|tr|li|h\d)\s*>", "\n", prepared, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", unescape(prepared))
    lines = [_normalize_text(line) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _fetch_html(url: str = AUCTIONS_LIST_URL, timeout: int = DEFAULT_REQUEST_TIMEOUT) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    return _read_response_text(request, timeout=timeout)


def _post_html(
    url: str,
    data: dict[str, str],
    *,
    referer: str,
    timeout: int = DEFAULT_REQUEST_TIMEOUT,
) -> str:
    request = Request(
        url,
        data=urlencode(data).encode(),
        headers={
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": BASE_URL,
            "Referer": referer,
            "User-Agent": USER_AGENT,
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    return _read_response_text(request, timeout=timeout)


def _read_response_text(request: Request, *, timeout: int) -> str:
    last_error: Exception | None = None
    for attempt in range(1, REQUEST_RETRY_ATTEMPTS + 1):
        try:
            with _OPENER.open(request, timeout=timeout) as response:
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
    raise URLError(f"TBankrot request timed out after {REQUEST_RETRY_ATTEMPTS} attempts: {request.full_url}") from last_error


def _is_timeout_error(error: URLError) -> bool:
    reason = error.reason
    return isinstance(reason, TimeoutError | socket.timeout) or "timed out" in str(reason).lower()


def login_tbankrot(email: str | None = None, password: str | None = None) -> bool:
    global _AUTHENTICATED

    email = email or os.getenv("TBANKROT_LOGIN")
    password = password or os.getenv("TBANKROT_PASSWORD")
    if not email or not password:
        raise TBankrotAuthError("Set TBANKROT_LOGIN and TBANKROT_PASSWORD to use authenticated TBankrot requests")

    response = _post_html(
        f"{BASE_URL}/script/ajax.php",
        {"key": "login", "mail": email, "pas": password},
        referer=f"{BASE_URL}/login",
    )
    result = _normalize_text(response)
    if result == "success":
        _AUTHENTICATED = True
        return True
    if result == "badMail":
        raise TBankrotAuthError("TBankrot rejected the login email")
    if result == "badPas":
        raise TBankrotAuthError("TBankrot rejected the password")
    if result in {"badCaptcha", "notCaptcha"}:
        raise TBankrotAuthError("TBankrot requested captcha verification before login")
    raise TBankrotAuthError(f"Unexpected TBankrot login response: {result or '<empty>'}")


def ensure_authenticated(email: str | None = None, password: str | None = None) -> bool:
    if _AUTHENTICATED:
        return True
    return login_tbankrot(email=email, password=password)


def _iter_lot_cards(html: str) -> list[str]:
    starts = [match.start() for match in re.finditer(r'<div\s+class="lot"\s+data-id="\d+"', html)]
    cards: list[str] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else html.find('<div class="pagination"', start)
        if end == -1:
            end = len(html)
        cards.append(html[start:end])
    return cards


def _first_match(fragment: str, pattern: str, flags: int = re.IGNORECASE | re.DOTALL) -> str | None:
    match = re.search(pattern, fragment, flags)
    if not match:
        return None
    value = _normalize_text(unescape(match.group(1)))
    return None if _is_masked(value) else value


def _first_text(fragment: str, pattern: str, flags: int = re.IGNORECASE | re.DOTALL) -> str | None:
    value = _first_match(fragment, pattern, flags)
    if not value:
        return None
    text = _strip_tags(value)
    return None if _is_masked(text) else text


def _first_url(fragment: str, pattern: str) -> str | None:
    value = _first_match(fragment, pattern)
    if not value:
        return None
    return urljoin(BASE_URL, value)


def _extract_category(card_html: str) -> str | None:
    return _first_match(card_html, r'<div\s+class="category_icons".*?<img[^>]+title="([^"]+)"')


def _extract_current_price(card_html: str) -> str | None:
    return _first_text(card_html, r'<div\s+class="current_price"[^>]*>.*?<span[^>]*>(.*?)</span>')


def _extract_minimum_price(card_html: str) -> str | None:
    return _first_text(card_html, r'<div\s+class="minimal_price"[^>]*>.*?<p[^>]*>\s*минимальная цена\s*</p>\s*<p[^>]*>(.*?)</p>')


def _extract_market_value(card_html: str) -> str | None:
    return _first_text(card_html, r'<span[^>]*>\s*Рын\.цена:\s*</span>\s*<span[^>]*>(.*?)</span>')


def _normalize_money_text(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _normalize_text(value)
    if not normalized:
        return None
    if "₽" in normalized or "руб" in normalized.lower():
        return normalized
    if re.search(r"\d", normalized):
        return f"{normalized} ₽"
    return None


def _extract_initial_price(card_html: str, current_price: str | None) -> str | None:
    prices = [_strip_tags(match.group(1)) for match in re.finditer(r'<(?:span|p)[^>]*>([\d\s\xa0]+,[\d]{2}\s*₽)</(?:span|p)>', card_html)]
    prices = [price for price in prices if price]
    if len(prices) >= 2:
        return prices[1]
    return current_price


def _extract_status(card_html: str) -> str | None:
    badge_values = [_strip_tags(match.group(1)) for match in re.finditer(r'<span[^>]+role="badge"[^>]*>(.*?)</span>', card_html, re.IGNORECASE | re.DOTALL)]
    if badge_values:
        return ", ".join(value for value in badge_values if value)

    status_values = [
        _strip_tags(match.group(1))
        for match in re.finditer(
            r'<div\s+class="[^"]*\bdate-(?:green|red|yellow|orange|gray|grey)\b[^"]*"[^>]*>.*?<span[^>]*>(.*?)</span>',
            card_html,
            re.IGNORECASE | re.DOTALL,
        )
    ]
    status_values = [value for value in status_values if value]
    if status_values:
        return ", ".join(status_values)
    return None


def _extract_auction_date(card_html: str) -> str | None:
    for match in re.finditer(r'<div\s+class="[^"]*\bdate\b(?!-[^"]*)[^"]*"[^>]*>.*?<span[^>]*>(.*?)</span>', card_html, re.IGNORECASE | re.DOTALL):
        value = _strip_tags(match.group(1))
        if re.search(r'\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{4}-\d{1,2}-\d{1,2}', value):
            return _normalize_date_text(value)
    return None


def _extract_lot_number(card_html: str) -> str | None:
    return _first_text(card_html, r'<div\s+class="lot_photo".*?<span>(Лот\s*[^<]+)</span>') or _first_text(
        card_html, r'Лот\s*№\s*([\w\-/.]+)'
    )


def _extract_images(card_html: str, title: str | None) -> list[LotImage]:
    urls = _extract_image_urls(card_html)
    return [LotImage(url=url, thumbnail_url=url, alt=title, source="tbankrot") for url in urls]


def _extract_image_urls(fragment: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []

    for tag_match in re.finditer(r'<img\b[^>]*>', fragment, re.IGNORECASE):
        tag = tag_match.group(0)
        for attr_match in re.finditer(r'\b(?:src|data-src|data-lazy|data-original)=["\']([^"\']+)["\']', tag, re.IGNORECASE):
            _append_image_url(urls, seen, attr_match.group(1))
        for srcset_match in re.finditer(r'\bsrcset=["\']([^"\']+)["\']', tag, re.IGNORECASE):
            for srcset_part in srcset_match.group(1).split(','):
                _append_image_url(urls, seen, srcset_part.strip().split(' ')[0])

    for style_match in re.finditer(r'background(?:-image)?\s*:\s*url\(["\']?([^"\')]+)["\']?\)', fragment, re.IGNORECASE):
        _append_image_url(urls, seen, style_match.group(1))

    return [url for url in urls if not _is_locked_image_url(url)] + [url for url in urls if _is_locked_image_url(url)]


def _append_image_url(urls: list[str], seen: set[str], raw_url: str) -> None:
    value = unescape(raw_url).strip()
    if not value or value.startswith('data:'):
        return
    url = urljoin(BASE_URL, value)
    if url in seen or not _is_lot_image_url(url):
        return
    seen.add(url)
    urls.append(url)


def _is_lot_image_url(url: str) -> bool:
    lowered = url.lower()
    if not re.search(r'\.(?:jpe?g|png|webp)(?:\?|$)', lowered):
        return False
    ignored_parts = (
        '/img/cat/',
        '/img/icons/',
        '/img/favicons/',
        '/img/logo',
        '/img/close.',
        '/img/a_down.',
        '/img/autoanalytics/',
        '/img/icon-',
        '/img/vin_',
        'mc.yandex.ru/',
        'top-fwz1.mail.ru/',
        'vk.com/rtrg',
    )
    return not any(part in lowered for part in ignored_parts)


def _is_locked_image_url(url: str) -> bool:
    lowered = url.lower()
    return '/img/blur/' in lowered or '/blur_' in lowered


def _extract_debtor_name(card_html: str) -> str | None:
    return _first_text(card_html, r'<a\s+href="reestr_card\?debtor_id=\d+"[^>]*>(.*?)</a>') or _first_text(
        card_html, r'<div\s+class="lot_row\s+lot_debtor"[^>]*>\s*<span>\s*Должник:\s*(.*?)</span>'
    )


def _extract_detail_debtor_name(html: str) -> str | None:
    return _first_text(html, r'<h1>\s*Торги должника:\s*(.*?)\s*</h1>') or _first_text(
        html, r'<span\s+class="gray">\s*Должник:\s*</span>\s*([^<]+)'
    )


def _extract_detail_organizer_name(html: str) -> str | None:
    return _first_text(html, r'<span\s+class="gray">\s*Организатор:\s*</span>\s*([^<]+)')


def _extract_detail_arbitration_manager(html: str) -> str | None:
    return _first_text(html, r'<span\s+class="gray">\s*Арбитражный управляющий:\s*</span>\s*([^<]+)')


def _extract_input_value(html: str, name: str) -> str | None:
    for match in re.finditer(r'<input\b([^>]+)>', html, re.IGNORECASE | re.DOTALL):
        attrs = match.group(1)
        attr_name = re.search(r'\bname=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
        if not attr_name or attr_name.group(1) != name:
            continue
        attr_value = re.search(r'\bvalue=["\']([^"\']*)["\']', attrs, re.IGNORECASE | re.DOTALL)
        if attr_value:
            value = _normalize_text(unescape(attr_value.group(1)))
            return value or None
    return None


def _extract_lot_text(html: str) -> str | None:
    match = re.search(r'<div\s+class="lot_text"[^>]*>(.*?)</div>', html, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    text = _strip_tags_with_breaks(match.group(1))
    return None if _is_masked(text) else text


def _extract_detail_documents(html: str) -> list[AuctionDocument]:
    documents: list[AuctionDocument] = []
    seen: set[str] = set()
    for match in re.finditer(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL):
        href = unescape(match.group(1)).strip()
        name = _strip_tags(match.group(2))
        if not href or not name:
            continue
        url = urljoin(BASE_URL, href)
        lowered = url.lower()
        if not (
            "files.tbankrot.ru/" in lowered
            or "webapi.torgi.cdtrf.ru/doc/public/file" in lowered
            or re.search(r'\.(?:pdf|docx?|xlsx?|jpe?g|png|webp)(?:\?|$)', lowered)
        ):
            continue
        if url in seen:
            continue
        seen.add(url)
        documents.append(
            AuctionDocument(
                external_id=url,
                name=name,
                url=url,
                document_type=_document_type_from_url_or_name(url, name),
            )
        )
    return documents


def _extract_detail_images_from_documents(documents: list[AuctionDocument], title: str | None) -> list[LotImage]:
    images: list[LotImage] = []
    seen: set[str] = set()
    for document in documents:
        url = document.url or ""
        if not _is_detail_image_document(document):
            continue
        if url in seen:
            continue
        seen.add(url)
        images.append(LotImage(url=url, thumbnail_url=url, alt=document.name or title, source="tbankrot"))
    return images


def _is_detail_image_document(document: AuctionDocument) -> bool:
    url = document.url or ""
    name = document.name or ""
    text = f"{name} {url}".lower()
    if document.document_type == "photo":
        return True
    return bool(re.search(r'\.(?:jpe?g|png|webp)(?:\?|\s|$)', text))


def _document_type_from_url_or_name(url: str, name: str) -> str | None:
    value = f"{name} {url}".lower()
    match = re.search(r'\.(pdf|docx?|xlsx?|jpe?g|png|webp)(?:\?|\s|$)', value)
    if not match:
        return None
    extension = match.group(1).replace("jpeg", "jpg")
    return "photo" if extension in {"jpg", "png", "webp"} else extension


def _extract_raw_fields(html: str) -> list[ScrapedField]:
    fields: list[ScrapedField] = []
    seen: set[tuple[str, str]] = set()

    def add(label: str, value: str | None) -> None:
        clean_label = _normalize_text(label).rstrip(":")
        clean_value = _normalize_text(value or "")
        if not clean_label or not clean_value or _is_masked(clean_value):
            return
        key = (clean_label, clean_value)
        if key in seen:
            return
        seen.add(key)
        fields.append(ScrapedField(name=clean_label, value=clean_value))

    for match in re.finditer(
        r'<div\s+class="row__info"[^>]*>.*?'
        r'<div\s+class="[^"]*flex\s+align-center[^"]*"[^>]*>(.*?)</div>.*?'
        r'<div\b[^>]*class="[^"]*data__row[^"]*"[^>]*>(.*?)</div>',
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        add(_strip_tags(match.group(1)), _strip_tags(match.group(2)))

    for match in re.finditer(r'<div\s+class="row"[^>]*>\s*<div[^>]*>(.*?)</div>\s*<div[^>]*>(.*?)</div>\s*</div>', html, re.IGNORECASE | re.DOTALL):
        add(_strip_tags(match.group(1)), _strip_tags(match.group(2)))

    for match in re.finditer(
        r'<span\s+class="gray">(Прием заявок:|Проведение торгов:)</span>\s*с\s*<span\s+class="date">(.*?)</span>\s*<span\s+class="time">(.*?)</span>\s*до\s*<span\s+class="date">(.*?)</span>\s*<span\s+class="time">(.*?)</span>',
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        add(match.group(1), f"с {_strip_tags(match.group(2))} {_strip_tags(match.group(3))} до {_strip_tags(match.group(4))} {_strip_tags(match.group(5))}")

    inspection_text = _first_text(html, r'<div\s+class="inspection_text[^" ]*[^>]*>\s*<div\s+class="text"[^>]*>(.*?)</div>')
    add("Порядок ознакомления", inspection_text)
    return fields


def _raw_field_value(fields: list[ScrapedField], *names: str) -> str | None:
    wanted = {name.lower().rstrip(":") for name in names}
    for field in fields:
        if field.name.lower().rstrip(":") in wanted:
            return field.value
    return None


def _raw_field_values(fields: list[ScrapedField], *names: str) -> list[str]:
    wanted = {name.lower().rstrip(":") for name in names}
    values: list[str] = []
    for field in fields:
        if field.name.lower().rstrip(":") in wanted:
            values.append(field.value)
    return values


def _extract_cadastral_market_value(fields: list[ScrapedField], category: str | None, title: str | None) -> str | None:
    real_estate_text = " ".join(filter(None, [category, title, _raw_field_value(fields, "Категория площадки", "Категория")])).lower()
    if real_estate_text and not re.search(r"квартир|помещен|здани|дом|земель|участ|недвиж|комнат|гараж|машино-мест", real_estate_text):
        return None

    cadastral_value = _raw_field_value(
        fields,
        "Кадастровая стоимость",
        "Кадастровая стоимость объекта",
        "Кадастровая стоимость имущества",
        "Кадастровая стоимость на дату оценки",
    )
    return _normalize_money_text(cadastral_value)


def _extract_application_dates(html: str, label: str) -> tuple[str | None, str | None]:
    pattern = rf'<span\s+class="gray">\s*{re.escape(label)}:\s*</span>\s*с\s*<span\s+class="date">(.*?)</span>\s*<span\s+class="time">(.*?)</span>\s*до\s*<span\s+class="date">(.*?)</span>\s*<span\s+class="time">(.*?)</span>'
    match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    if not match:
        return None, None
    return (
        _normalize_date_text(f"{_strip_tags(match.group(1))} {_strip_tags(match.group(2))}"),
        _normalize_date_text(f"{_strip_tags(match.group(3))} {_strip_tags(match.group(4))}"),
    )


def _normalize_date_text(value: str) -> str:
    return re.sub(
        r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
        lambda match: f"{int(match.group(1)):02d}.{int(match.group(2)):02d}.{match.group(3)}",
        _normalize_text(value),
    )


def _extract_city(location: str | None) -> str | None:
    if not location:
        return None
    match = re.search(r'(?:^|[,;])\s*(?:г\.|город)\s*([^,;]+)', location, re.IGNORECASE)
    return _normalize_text(match.group(1)) if match else None


def _format_schedule_price(value: str) -> str:
    price = _normalize_text(value)
    if price and "₽" not in price and "руб" not in price.lower():
        price = f"{price} ₽"
    return price


def fetch_price_schedule(
    lot_id: str,
    *,
    authenticate: bool = False,
    auth_email: str | None = None,
    auth_password: str | None = None,
) -> list[PriceScheduleStep]:
    if authenticate:
        ensure_authenticated(email=auth_email, password=auth_password)
    html = _post_html(
        f"{BASE_URL}/script/ajax.php",
        {"key": "get_price_down", "id": lot_id},
        referer=f"{BASE_URL}/item?id={lot_id}",
    )
    steps: list[PriceScheduleStep] = []
    for match in re.finditer(
        r'<tr\s+class="down"[^>]*>\s*<td\s+class="date"[^>]*>(.*?)</td>\s*<td\s+class="price"[^>]*>(.*?)</td>',
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        starts_at = _strip_tags(match.group(1))
        price = _format_schedule_price(_strip_tags(match.group(2)))
        if starts_at and price:
            steps.append(PriceScheduleStep(starts_at=starts_at, price=price))
    return steps


def _build_list_url(page: int = 1) -> str:
    return AUCTIONS_LIST_URL if page <= 1 else f"{AUCTIONS_LIST_URL}?page={page}"


def _extract_last_page(html: str) -> int | None:
    page_numbers = [int(match.group(1)) for match in re.finditer(r'[?&]page=(\d+)', html)]
    return max(page_numbers) if page_numbers else None


def _build_item(
    card_html: str,
    *,
    include_price_schedule: bool = True,
    authenticate: bool = False,
    auth_email: str | None = None,
    auth_password: str | None = None,
) -> AuctionListItem | None:
    item_id = _first_match(card_html, r'data-id="(\d+)"')
    if not item_id:
        return None

    lot_url = f"{BASE_URL}/item?id={item_id}"
    auction_number = _first_text(card_html, r'<a[^>]+class="lot_num[^"]*"[^>]*>(.*?)</a>')
    title = _first_text(card_html, r'<p\s+class="lot_title"[^>]*>\s*<a[^>]*>(.*?)</a>')
    description = _first_text(card_html, r'<div\s+class="text"[^>]*>(.*?)</div>')
    etp_url = _first_url(card_html, r'<a\s+class="etp_link"\s+href="([^"]+)"')
    organizer_name = _first_text(card_html, r'<a\s+class="etp_link"[^>]*>(.*?)</a>')
    auction_date = _extract_auction_date(card_html)
    current_price = _extract_current_price(card_html)
    minimum_price = _extract_minimum_price(card_html)
    market_value = _extract_market_value(card_html)
    initial_price = _extract_initial_price(card_html, current_price)
    debtor_name = _extract_debtor_name(card_html)
    location = _first_text(card_html, r'<span\s+class="debtor_location"[^>]*>.*?<span>(.*?)</span>')
    city = _extract_city(location)
    publication_date = _first_text(card_html, r'<div\s+class="lot_created[^>]*>(.*?)</div>')
    price_schedule = (
        fetch_price_schedule(item_id, authenticate=authenticate, auth_email=auth_email, auth_password=auth_password)
        if include_price_schedule
        else []
    )
    images = _extract_images(card_html, title)

    return AuctionListItem(
        source="tbankrot",
        auction=AuctionSummary(
            source="tbankrot",
            external_id=item_id,
            number=auction_number,
            name=title,
            url=lot_url,
            publication_date=publication_date,
            auction_date=auction_date,
        ),
        lot=LotSummary(
            source="tbankrot",
            external_id=item_id,
            number=_extract_lot_number(card_html),
            name=title,
            url=lot_url,
            category=_extract_category(card_html),
            location=location,
            region=location,
            city=city,
            initial_price=initial_price,
            current_price=current_price,
            minimum_price=minimum_price,
            market_value=market_value,
            status=_extract_status(card_html),
            description=description,
            price_schedule=price_schedule,
            images=images,
            primary_image_url=images[0].url if images else None,
        ),
        organizer=OrganizerInfo(name=organizer_name, website=etp_url),
        debtor=DebtorInfo(name=debtor_name, region=location),
    )


def fetch_auction_list(
    limit: int | None = 20,
    *,
    include_price_schedule: bool = True,
    page: int = 1,
    pages: int | None = 1,
    authenticate: bool = False,
    auth_email: str | None = None,
    auth_password: str | None = None,
) -> list[AuctionListItem]:
    return list(
        iter_auction_list(
            limit=limit,
            include_price_schedule=include_price_schedule,
            page=page,
            pages=pages,
            authenticate=authenticate,
            auth_email=auth_email,
            auth_password=auth_password,
        )
    )


def iter_auction_list(
    limit: int | None = 20,
    *,
    include_price_schedule: bool = True,
    page: int = 1,
    pages: int | None = 1,
    authenticate: bool = False,
    auth_email: str | None = None,
    auth_password: str | None = None,
):
    if authenticate:
        ensure_authenticated(email=auth_email, password=auth_password)
    if pages is not None and pages <= 0:
        pages = None

    yielded = 0
    page_number = page
    last_page: int | None = None
    while True:
        html = _fetch_html(_build_list_url(page_number))
        if pages is None and last_page is None:
            last_page = _extract_last_page(html)
        cards = _iter_lot_cards(html)
        if not cards:
            break
        for card_html in cards:
            item = _build_item(
                card_html,
                include_price_schedule=include_price_schedule,
                authenticate=authenticate,
                auth_email=auth_email,
                auth_password=auth_password,
            )
            if item is None:
                continue
            yield item
            yielded += 1
            if limit is not None and yielded >= limit:
                return
        if pages is not None and page_number >= page + pages - 1:
            break
        if pages is None and last_page is not None and page_number >= last_page:
            break
        page_number += 1


def fetch_lot_detail(
    lot_id: str,
    *,
    authenticate: bool = False,
    auth_email: str | None = None,
    auth_password: str | None = None,
) -> LotDetailResponse:
    if authenticate:
        ensure_authenticated(email=auth_email, password=auth_password)

    url = f"{BASE_URL}/item?id={lot_id}"
    html = _fetch_html(url)
    raw_fields = _extract_raw_fields(html)
    documents = _extract_detail_documents(html)
    lot_text = _extract_lot_text(html)
    title = _first_match(html, r'<meta\s+property="og:title"\s+content="([^"]+)"') or _first_text(html, r'<h1>(.*?)</h1>')
    publication_date = _first_text(html, r'<p\s+class="obtain"[^>]*>.*?<span\s+class="gray">(.*?)</span>')
    application_start, application_deadline = _extract_application_dates(html, "Прием заявок")
    auction_start, auction_end = _extract_application_dates(html, "Проведение торгов")
    images = _extract_detail_images_from_documents(documents, title)

    debtor_name = _extract_detail_debtor_name(html)
    organizer_name = _extract_detail_organizer_name(html)
    arbitration_manager = _extract_detail_arbitration_manager(html)
    inspection_order = _raw_field_value(raw_fields, "Порядок ознакомления")
    platform_category = _raw_field_value(raw_fields, "Категория площадки", "Категория") or _extract_category(html)
    market_value = _extract_cadastral_market_value(raw_fields, platform_category, title)
    inn_values = _raw_field_values(raw_fields, "ИНН")
    debtor_inn = _extract_input_value(html, "debtor_inn") or (inn_values[0] if inn_values else None)
    organizer_inn = inn_values[1] if len(inn_values) > 1 else None

    return LotDetailResponse(
        source="tbankrot",
        url=url,
        auction=AuctionSummary(
            source="tbankrot",
            external_id=lot_id,
            number=_first_text(html, r'<input[^>]+name="lot_num"[^>]+value="([^"]+)"') or _first_text(html, r'Торги №\s*([^<\s]+)'),
            name=title,
            url=url,
            publication_date=publication_date,
            application_start=application_start,
            application_deadline=application_deadline,
            auction_date=auction_start,
            application_order=inspection_order,
        ),
        lot=LotSummary(
            source="tbankrot",
            external_id=lot_id,
            number=_first_text(html, r'<input[^>]+name="lot"[^>]+value="([^"]+)"') or _first_text(html, r'Лот №\s*([\w\-/.]+)'),
            name=title,
            url=url,
            category=platform_category,
            location=_raw_field_value(raw_fields, "Адрес нахождения имущества", "Регион") or _first_text(html, r'Местонахождение:\s*(.*?)(?:\n|$)'),
            region=_raw_field_value(raw_fields, "Регион"),
            city=_extract_city(_raw_field_value(raw_fields, "Регион") or ""),
            initial_price=_first_text(html, r'<div\s+class="start_price"[^>]*>.*?<span\s+class="sum ajax"[^>]*>(.*?)</span>'),
            current_price=_first_text(html, r'<p\s+class="green semibold"[^>]*>(.*?)</p>'),
            minimum_price=_first_text(html, r'<p\s+class="red semibold"[^>]*>(.*?)</p>'),
            market_value=market_value,
            description=lot_text,
            inspection_order=inspection_order,
            images=images,
            primary_image_url=images[0].url if images else None,
        ),
        organizer=OrganizerInfo(name=organizer_name, inn=organizer_inn),
        debtor=DebtorInfo(
            name=debtor_name,
            inn=debtor_inn,
            bankruptcy_case_number=_raw_field_value(raw_fields, "Дело №"),
            arbitration_court=_raw_field_value(raw_fields, "Суд"),
            arbitration_manager=arbitration_manager,
            managers_organization=_raw_field_value(raw_fields, "СРО"),
            region=_raw_field_value(raw_fields, "Регион"),
        ),
        documents=documents,
        raw_fields=raw_fields,
        raw_tables=[],
    )
