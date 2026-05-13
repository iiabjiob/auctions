from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal

from app.services.procurement_scoring import score_procurement_lot
from app.services.procurement_values import parse_money
from app.services.zakupki_scraper import parse_search_results


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

    def test_score_procurement_lot_prioritizes_active_near_deadline_items(self) -> None:
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

        self.assertEqual(score.level, "high")
        self.assertGreaterEqual(score.score, 80)
