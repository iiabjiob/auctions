from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.auction_sources import TBankrotSourceProvider


class TBankrotSourceProviderTests(unittest.TestCase):
    def test_list_lots_does_not_load_price_schedule(self) -> None:
        provider = TBankrotSourceProvider()

        with patch("app.services.auction_sources.fetch_tbankrot_auction_list", return_value=[]) as fetch_list:
            provider.list_lots(limit=10)

        self.assertFalse(fetch_list.call_args.kwargs["include_price_schedule"])

    def test_iter_lots_does_not_load_price_schedule(self) -> None:
        provider = TBankrotSourceProvider()

        with patch("app.services.auction_sources.iter_tbankrot_auction_list", return_value=iter(())) as iter_list:
            list(provider.iter_lots(limit=10))

        self.assertFalse(iter_list.call_args.kwargs["include_price_schedule"])

    def test_lot_detail_loads_price_schedule_by_default(self) -> None:
        provider = TBankrotSourceProvider()

        with patch("app.services.auction_sources.fetch_tbankrot_lot_detail") as fetch_detail:
            provider.get_lot("123")

        self.assertTrue(fetch_detail.call_args.kwargs["include_price_schedule"])

    def test_lot_detail_can_skip_price_schedule_for_background_enrichment(self) -> None:
        provider = TBankrotSourceProvider()

        with patch("app.services.auction_sources.fetch_tbankrot_lot_detail") as fetch_detail:
            provider.get_lot("123", include_price_schedule=False)

        self.assertFalse(fetch_detail.call_args.kwargs["include_price_schedule"])


if __name__ == "__main__":
    unittest.main()
