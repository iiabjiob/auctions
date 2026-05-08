from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch

from app.services import tbankrot_scraper
from app.services.tbankrot_scraper import TBankrotCooldownError, fetch_lot_detail, fetch_price_schedule


MINIMAL_DETAIL_HTML = """
<html>
  <head><meta property="og:title" content="Тестовый лот"></head>
  <body>
    <input name="lot_num" value="Т-1">
    <input name="lot" value="1">
  </body>
</html>
"""

COMPLETED_DETAIL_HTML = """
<html>
  <head><meta property="og:title" content="Торги № 63986-ОТПП ( лот 1 ) Транспорт и техника - Торги состоялись"></head>
  <body>
    <input name="lot_num" value="63986-ОТПП">
    <input name="lot" value="1">
  </body>
</html>
"""


class TBankrotScraperTests(unittest.TestCase):
    def test_fetch_lot_detail_accepts_include_price_schedule_flag(self) -> None:
        signature = inspect.signature(fetch_lot_detail)

        self.assertIn("include_price_schedule", signature.parameters)

    def test_fetch_lot_detail_can_skip_price_schedule(self) -> None:
        with patch("app.services.tbankrot_scraper._fetch_html", return_value=MINIMAL_DETAIL_HTML), patch(
            "app.services.tbankrot_scraper.fetch_price_schedule",
            return_value=[],
        ) as fetch_schedule:
            detail = fetch_lot_detail("123", include_price_schedule=False)

        fetch_schedule.assert_not_called()
        self.assertEqual(detail.lot.price_schedule, [])

    def test_fetch_lot_detail_loads_price_schedule_by_default(self) -> None:
        with patch("app.services.tbankrot_scraper._fetch_html", return_value=MINIMAL_DETAIL_HTML), patch(
            "app.services.tbankrot_scraper.fetch_price_schedule",
            return_value=[],
        ) as fetch_schedule:
            fetch_lot_detail("123")

        fetch_schedule.assert_called_once()

    def test_fetch_lot_detail_extracts_completed_status_from_title(self) -> None:
        with patch("app.services.tbankrot_scraper._fetch_html", return_value=COMPLETED_DETAIL_HTML), patch(
            "app.services.tbankrot_scraper.fetch_price_schedule",
            return_value=[],
        ):
            detail = fetch_lot_detail("123", include_price_schedule=False)

        self.assertEqual(detail.lot.status, "Торги состоялись")

    def test_fetch_price_schedule_retries_without_session_when_authenticated_response_is_empty(self) -> None:
        schedule_html = """
        <table>
            <tr class="down"><td class="date">04.05.2026 - 09:00</td><td class="price">405 000,00</td></tr>
        </table>
        """

        with patch("app.services.tbankrot_scraper.ensure_authenticated") as ensure_authenticated, patch(
            "app.services.tbankrot_scraper._fetch_price_schedule_html",
            side_effect=["", schedule_html],
        ) as fetch_schedule_html:
            steps = fetch_price_schedule("123", authenticate=True, auth_email="user", auth_password="password")

        ensure_authenticated.assert_called_once_with(email="user", password="password")
        self.assertEqual(fetch_schedule_html.call_args_list[0].kwargs, {})
        self.assertEqual(fetch_schedule_html.call_args_list[1].kwargs, {"use_session": False})
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].price, "405 000,00 ₽")

    def test_blocked_cooldown_skips_requests_fast(self) -> None:
        previous_blocked_until = tbankrot_scraper._BLOCKED_UNTIL
        try:
            tbankrot_scraper._start_blocked_cooldown(403, "https://tbankrot.ru/")

            with self.assertRaises(TBankrotCooldownError):
                tbankrot_scraper._wait_for_polite_request_slot("https://tbankrot.ru/")
        finally:
            tbankrot_scraper._BLOCKED_UNTIL = previous_blocked_until


if __name__ == "__main__":
    unittest.main()
