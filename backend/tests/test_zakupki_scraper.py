from __future__ import annotations

import unittest
from types import SimpleNamespace
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

from app.services.procurement_scoring import score_procurement_lot
from app.services.procurement_values import parse_money
from app.services.zakupki_scraper import build_search_params, fetch_search_page_via_gateway, parse_search_results, parse_search_results_with_diagnostics


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
        return None

    def read(self) -> bytes:
        return self.body


class ZakupkiScraperTests(unittest.TestCase):
    def test_parse_money_handles_ruble_markup(self) -> None:
        self.assertEqual(parse_money("3 515 367,35 &#8381;"), Decimal("3515367.35"))

    def test_parse_search_results_extracts_procurement_card(self) -> None:
        html = """
        <div class="registry-entry__header-mid__number">
          <a target="_blank" href="https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber=0149200002326002213">
            № 0149200002326002213
          </a>
        </div>
        <div class="registry-entry__header-mid__title text-normal">Подача заявок</div>
        <div class="registry-entry__body">
          <div class="registry-entry__body-block">
            <div class="registry-entry__body-title">Объект закупки</div>
            <div class="registry-entry__body-value">Поставка медицинских изделий</div>
          </div>
          <div class="registry-entry__body-block">
            <div class="registry-entry__body-title">Заказчик</div>
            <div class="registry-entry__body-value"><a>ГОБУЗ БОЛЬНИЦА</a></div>
          </div>
          <div class="registry-entry__body-block">
            <div class="registry-entry__body-title">Начальная цена</div>
            <div class="registry-entry__body-value">12 698 000,00 &#8381;</div>
          </div>
        </div>
        <div>Размещено 13.05.2026</div>
        <div>Окончание подачи заявок 20.05.2026 09:00</div>
        """

        items = parse_search_results(html)

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.registry_number, "0149200002326002213")
        self.assertEqual(item.law, "44-ФЗ")
        self.assertEqual(item.title, "Поставка медицинских изделий")
        self.assertEqual(item.customer_name, "ГОБУЗ БОЛЬНИЦА")
        self.assertEqual(item.initial_price_value, Decimal("12698000.00"))
        self.assertEqual(item.application_deadline, "20.05.2026 09:00")

    def test_build_search_params_uses_apparel_keywords_and_pagination(self) -> None:
        params = build_search_params(
            page=3,
            records_per_page=20,
            search_keywords=("спецодежда", "халат медицинский"),
        )

        self.assertEqual(params["pageNumber"], 3)
        self.assertEqual(params["recordsPerPage"], "_20")
        self.assertEqual(params["searchString"], "спецодежда халат медицинский")
        self.assertEqual(params["fz44"], "on")
        self.assertEqual(params["fz223"], "on")

    def test_fetch_search_page_via_gateway_posts_to_restricted_fetcher(self) -> None:
        settings = SimpleNamespace(
            zakupki_fetch_gateway_url="http://fetcher:8080",
            zakupki_fetch_token="secret",
            zakupki_fetch_timeout_seconds=30,
        )
        response = FakeResponse(
            b'{"status": 200, "body": "<html>ok</html>", "body_base64": false}'
        )

        with (
            patch("app.services.zakupki_scraper.get_settings", return_value=settings),
            patch("app.services.zakupki_scraper.urlopen", return_value=response) as urlopen_mock,
        ):
            body = fetch_search_page_via_gateway(params={"pageNumber": 1}, timeout=15)

        self.assertEqual(body, "<html>ok</html>")
        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, "http://fetcher:8080/fetch")
        self.assertEqual(request.headers["Authorization"], "Bearer secret")
        self.assertEqual(urlopen_mock.call_args.kwargs["timeout"], 15)

    def test_parse_44fz_fixture_extracts_source_fields(self) -> None:
        html = """
        <div class="registry-entry__header-mid__number">
          <a target="_blank" href="https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber=0149200002326002213">
            № 0149200002326002213
          </a>
        </div>
        <div class="registry-entry__header-mid__title text-normal">Подача заявок</div>
        <a href="/epz/order/notice/ea20/view/documents.html?regNumber=0149200002326002213">Документы закупки</a>
        <div class="registry-entry__body-block">
          <div class="registry-entry__body-title">Объект закупки</div>
          <div class="registry-entry__body-value">Поставка медицинской одежды</div>
        </div>
        <div class="registry-entry__body-block">
          <div class="registry-entry__body-title">Заказчик</div>
          <div class="registry-entry__body-href">
            <a href="/epz/organization/view/info.html?inn=5190000000&kpp=519001001">
              ГОБУЗ БОЛЬНИЦА
            </a>
          </div>
        </div>
        <div class="registry-entry__body-block">
          <div class="registry-entry__body-title">Способ определения поставщика</div>
          <div class="registry-entry__body-value">Электронный аукцион</div>
        </div>
        <div class="registry-entry__body-block">
          <div class="registry-entry__body-title">Место поставки</div>
          <div class="registry-entry__body-value">Мурманская область, г. Мурманск</div>
        </div>
        <div class="price-block">
          <div class="price-block__title">Начальная цена</div>
          <div class="price-block__value">12 698 000,00 ₽</div>
        </div>
        <div>Размещено 13.05.2026</div>
        <div>Окончание подачи заявок 20.05.2026 09:00</div>
        """

        item = parse_search_results(html)[0]

        self.assertEqual(item.law, "44-ФЗ")
        self.assertEqual(item.customer_inn, "5190000000")
        self.assertEqual(item.procedure_type, "Электронный аукцион")
        self.assertEqual(item.delivery_region, "Мурманская область, г. Мурманск")
        self.assertEqual(item.documents_url, "https://zakupki.gov.ru/epz/order/notice/ea20/view/documents.html?regNumber=0149200002326002213")
        self.assertTrue(item.documentation_present)

    def test_parse_223fz_fixture_extracts_customer_inn_and_documents_fallback(self) -> None:
        html = """
        <div class="registry-entry__header-mid__number">
          <a target="_blank" href="https://zakupki.gov.ru/223/purchase/public/purchase/info/common-info.html?regNumber=32616004277">
            № 32616004277
          </a>
        </div>
        <div class="registry-entry__header-mid__title text-normal">Работа комиссии</div>
        <a href="/epz/print-form/notice.html?regNumber=32616004277">Печатная форма</a>
        <div class="registry-entry__body-block">
          <div class="registry-entry__body-title">Объект закупки</div>
          <div class="registry-entry__body-value">Поставка специальной одежды</div>
        </div>
        <div class="registry-entry__body-block">
          <div class="registry-entry__body-title">Заказчик</div>
          <div class="registry-entry__body-href">
            <a href="/epz/organization/view223/info.html?&inn=2537139561&kpp=251201001">
              ООО "ИКС"
            </a>
          </div>
        </div>
        <div class="registry-entry__body-block">
          <div class="registry-entry__body-title">Способ закупки</div>
          <div class="registry-entry__body-value">Запрос котировок</div>
        </div>
        <div class="price-block">
          <div class="price-block__title">Начальная цена</div>
          <div class="price-block__value">3 515 367,35 &#8381;</div>
        </div>
        """

        item = parse_search_results(html)[0]

        self.assertEqual(item.law, "223-ФЗ")
        self.assertEqual(item.customer_inn, "2537139561")
        self.assertEqual(item.procedure_type, "Запрос котировок")
        self.assertEqual(item.initial_price_value, Decimal("3515367.35"))
        self.assertEqual(item.documents_url, "https://zakupki.gov.ru/223/purchase/public/purchase/info/documents.html?regNumber=32616004277")
        self.assertEqual(item.print_url, "https://zakupki.gov.ru/epz/print-form/notice.html?regNumber=32616004277")

    def test_parse_search_results_reports_missing_fields(self) -> None:
        result = parse_search_results_with_diagnostics(
            """
            <div class="registry-entry__header-mid__number">
              <a href="https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber=1">№ 1</a>
            </div>
            """
        )

        self.assertEqual(result.diagnostics.total_chunks, 1)
        self.assertEqual(result.diagnostics.parsed_items, 1)
        self.assertGreaterEqual(result.diagnostics.missing_required_fields["title"], 1)
        self.assertGreaterEqual(result.diagnostics.missing_required_fields["initial_price"], 1)

    def test_score_procurement_lot_uses_parser_only_fallback_for_active_items(self) -> None:
        item = parse_search_results(
            """
            <div class="registry-entry__header-mid__number">
              <a href="https://zakupki.gov.ru/223/purchase/public/purchase/info/common-info.html?regNumber=32616004277">№ 32616004277</a>
            </div>
            <div class="registry-entry__header-mid__title text-normal">Подача заявок</div>
            <div class="registry-entry__body-block">
              <div class="registry-entry__body-title">Объект закупки</div>
              <div class="registry-entry__body-value">Поставка оргтехники</div>
            </div>
            <div class="registry-entry__body-block">
              <div class="registry-entry__body-title">Заказчик</div>
              <div class="registry-entry__body-value">АО Заказчик</div>
            </div>
            <div class="registry-entry__body-block">
              <div class="registry-entry__body-title">Начальная цена</div>
              <div class="registry-entry__body-value">8 946 800,00 ₽</div>
            </div>
            <div>Окончание подачи заявок 20.05.2026 09:00</div>
            """
        )[0]

        score = score_procurement_lot(item, current_time=datetime(2026, 5, 13, tzinfo=UTC))

        self.assertEqual(score.level, "low")
        self.assertGreaterEqual(score.score, 40)
