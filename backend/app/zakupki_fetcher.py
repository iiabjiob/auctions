import asyncio
import base64
import hmac
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

from fastapi import FastAPI, Header, HTTPException, Query, Request as FastAPIRequest
from pydantic import BaseModel, Field


DEFAULT_BASE_URL = "https://zakupki.gov.ru"
BLOCKED_REQUEST_HEADERS = {
    "authorization",
    "connection",
    "content-length",
    "host",
    "proxy-authorization",
    "transfer-encoding",
}
DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.6",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}


class FetchPayload(BaseModel):
    method: str = "GET"
    url: str | None = None
    path: str | None = None
    params: dict[str, str | int | float | bool | list[str | int | float | bool]] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None


class FetchResponse(BaseModel):
    status: int
    reason: str | None
    url: str
    elapsed_ms: int
    headers: dict[str, str]
    content_type: str | None
    encoding: str | None
    body: str
    body_base64: bool = False
    truncated: bool = False


@dataclass(frozen=True)
class FetchSettings:
    token: str | None
    base_url: str
    allowed_hosts: tuple[str, ...]
    timeout_seconds: float
    max_response_bytes: int


def _settings() -> FetchSettings:
    base_url = os.getenv("ZAKUPKI_FETCH_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    allowed_hosts = tuple(
        host.strip().lower()
        for host in os.getenv("ZAKUPKI_FETCH_ALLOWED_HOSTS", "zakupki.gov.ru").split(",")
        if host.strip()
    )
    return FetchSettings(
        token=os.getenv("ZAKUPKI_FETCH_TOKEN") or None,
        base_url=base_url,
        allowed_hosts=allowed_hosts,
        timeout_seconds=float(os.getenv("ZAKUPKI_FETCH_TIMEOUT_SECONDS", "30")),
        max_response_bytes=int(os.getenv("ZAKUPKI_FETCH_MAX_RESPONSE_BYTES", str(1024 * 1024 * 5))),
    )


def _authorize(expected_token: str | None, authorization: str | None) -> None:
    if not expected_token:
        raise HTTPException(status_code=503, detail="ZAKUPKI_FETCH_TOKEN is not configured")

    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token, expected_token):
        raise HTTPException(status_code=401, detail="Invalid bearer token")


def _host_allowed(hostname: str | None, allowed_hosts: tuple[str, ...]) -> bool:
    if not hostname:
        return False
    hostname = hostname.lower()
    return any(hostname == allowed or hostname.endswith(f".{allowed}") for allowed in allowed_hosts)


def _target_url(payload: FetchPayload, settings: FetchSettings) -> str:
    if bool(payload.url) == bool(payload.path):
        raise HTTPException(status_code=400, detail="Provide exactly one of url or path")

    if payload.path:
        if not payload.path.startswith("/"):
            raise HTTPException(status_code=400, detail="path must start with /")
        url = urljoin(f"{settings.base_url}/", payload.path.lstrip("/"))
    else:
        url = payload.url or ""

    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise HTTPException(status_code=400, detail="Only https URLs are allowed")
    if not _host_allowed(parsed.hostname, settings.allowed_hosts):
        raise HTTPException(status_code=400, detail="Host is not allowed")

    if payload.params:
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        query_pairs.extend(payload.params.items())
        parsed = parsed._replace(query=urlencode(query_pairs, doseq=True))

    return urlunparse(parsed)


def _request_headers(extra_headers: dict[str, str]) -> dict[str, str]:
    headers = dict(DEFAULT_HEADERS)
    for key, value in extra_headers.items():
        if key.lower() not in BLOCKED_REQUEST_HEADERS:
            headers[key] = value
    return headers


def _decode_body(data: bytes, content_type: str | None) -> tuple[str, bool, str | None]:
    encoding = None
    if content_type:
        for part in content_type.split(";")[1:]:
            name, _, value = part.strip().partition("=")
            if name.lower() == "charset" and value:
                encoding = value.strip("\"'")
                break

    if not encoding:
        encoding = "utf-8"

    try:
        return data.decode(encoding), False, encoding
    except UnicodeDecodeError:
        return base64.b64encode(data).decode("ascii"), True, None


def _perform_fetch(payload: FetchPayload, settings: FetchSettings) -> FetchResponse:
    method = payload.method.upper()
    if method not in {"GET", "POST", "HEAD"}:
        raise HTTPException(status_code=400, detail="Only GET, POST and HEAD are allowed")

    target = _target_url(payload, settings)
    body = payload.body.encode("utf-8") if payload.body is not None else None
    request = Request(target, data=body, headers=_request_headers(payload.headers), method=method)

    started = time.monotonic()
    try:
        response = urlopen(request, timeout=settings.timeout_seconds)
        status = response.status
        reason = response.reason
        response_url = response.url
        headers = dict(response.headers.items())
        data = response.read(settings.max_response_bytes + 1)
    except HTTPError as exc:
        status = exc.code
        reason = exc.reason
        response_url = exc.url
        headers = dict(exc.headers.items())
        data = exc.read(settings.max_response_bytes + 1)
    except URLError as exc:
        raise HTTPException(status_code=502, detail=f"Fetch failed: {exc.reason}") from exc

    truncated = len(data) > settings.max_response_bytes
    if truncated:
        data = data[: settings.max_response_bytes]

    content_type = headers.get("Content-Type")
    decoded_body, is_base64, encoding = _decode_body(data, content_type)
    return FetchResponse(
        status=status,
        reason=reason,
        url=response_url,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        headers=headers,
        content_type=content_type,
        encoding=encoding,
        body=decoded_body,
        body_base64=is_base64,
        truncated=truncated,
    )


app = FastAPI(
    title="Zakupki Fetch Gateway",
    description="Restricted fetch gateway for exploring zakupki.gov.ru from a Russian network.",
    version="0.1.0",
)


@app.get("/health")
async def health() -> dict[str, Any]:
    settings = _settings()
    return {
        "status": "ok",
        "base_url": settings.base_url,
        "allowed_hosts": settings.allowed_hosts,
        "token_configured": bool(settings.token),
    }


@app.post("/fetch", response_model=FetchResponse)
async def fetch(
    payload: FetchPayload,
    authorization: str | None = Header(default=None),
) -> FetchResponse:
    settings = _settings()
    _authorize(settings.token, authorization)
    return await asyncio.to_thread(_perform_fetch, payload, settings)


@app.get("/fetch", response_model=FetchResponse)
async def fetch_get(
    request: FastAPIRequest,
    path: str | None = Query(default=None),
    url: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> FetchResponse:
    settings = _settings()
    _authorize(settings.token, authorization)

    params = dict(request.query_params)
    params.pop("path", None)
    params.pop("url", None)
    payload = FetchPayload(method="GET", path=path, url=url, params=params)
    return await asyncio.to_thread(_perform_fetch, payload, settings)
