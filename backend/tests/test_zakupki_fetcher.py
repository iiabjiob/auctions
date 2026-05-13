from __future__ import annotations

import unittest

from fastapi import HTTPException

from app.zakupki_fetcher import FetchPayload, FetchSettings, _authorize, _target_url


class ZakupkiFetcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = FetchSettings(
            token="secret",
            base_url="https://zakupki.gov.ru",
            allowed_hosts=("zakupki.gov.ru",),
            timeout_seconds=30,
            max_response_bytes=1024,
        )

    def test_authorize_accepts_valid_bearer_token(self) -> None:
        _authorize("secret", "Bearer secret")

    def test_authorize_rejects_missing_configured_token(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            _authorize(None, "Bearer secret")

        self.assertEqual(ctx.exception.status_code, 503)

    def test_target_url_allows_zakupki_path_with_params(self) -> None:
        url = _target_url(
            FetchPayload(
                path="/epz/main/public/siteMap.html",
                params={"searchString": "тест", "pageNumber": 1},
            ),
            self.settings,
        )

        self.assertEqual(
            url,
            "https://zakupki.gov.ru/epz/main/public/siteMap.html?searchString=%D1%82%D0%B5%D1%81%D1%82&pageNumber=1",
        )

    def test_target_url_quotes_cyrillic_query_from_path(self) -> None:
        url = _target_url(
            FetchPayload(path="/epz/order/extendedsearch/results.html?search-filter=Дате размещения"),
            self.settings,
        )

        self.assertEqual(
            url,
            "https://zakupki.gov.ru/epz/order/extendedsearch/results.html?search-filter=%D0%94%D0%B0%D1%82%D0%B5%20%D1%80%D0%B0%D0%B7%D0%BC%D0%B5%D1%89%D0%B5%D0%BD%D0%B8%D1%8F",
        )

    def test_target_url_rejects_non_zakupki_host(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            _target_url(FetchPayload(url="https://example.com/"), self.settings)

        self.assertEqual(ctx.exception.status_code, 400)

    def test_target_url_rejects_plain_http(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            _target_url(FetchPayload(url="http://zakupki.gov.ru/"), self.settings)

        self.assertEqual(ctx.exception.status_code, 400)
