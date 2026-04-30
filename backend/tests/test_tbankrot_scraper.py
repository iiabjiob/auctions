from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch

from app.services import tbankrot_scraper
from app.services.tbankrot_scraper import TBankrotCooldownError, fetch_lot_detail


MINIMAL_DETAIL_HTML = """
<html>
  <head><meta property="og:title" content="Тестовый лот"></head>
  <body>
    <input name="lot_num" value="Т-1">
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
