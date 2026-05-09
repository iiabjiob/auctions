from __future__ import annotations

import unittest

from app.models.auction import AuctionLotRecord
from app.services.auction_search import build_lot_search_text, update_record_search_text


class AuctionSearchTextTests(unittest.TestCase):
    def test_build_lot_search_text_normalizes_expected_fields(self) -> None:
        search_text = build_lot_search_text(
            lot_name=" BMW   X5 ",
            datagrid_row={
                "source_title": " TBankrot ",
                "location_region": " Москва ",
                "category": " Авто ",
                "organizer_name": " Организатор ",
                "debtor_name": " Должник ",
                "location": " ул. Ленина ",
            },
            normalized_item={},
        )

        self.assertEqual(search_text, "bmw x5 tbankrot москва авто организатор должник ул. ленина")

    def test_update_record_search_text_uses_normalized_fallbacks(self) -> None:
        record = AuctionLotRecord(
            source_code="tbankrot",
            auction_external_id="auction-1",
            lot_external_id="lot-1",
            lot_name="Лот",
            content_hash="hash",
            datagrid_row={"source_title": "TBankrot"},
            normalized_item={
                "lot": {"region": "Санкт-Петербург", "category": "Недвижимость", "location": "Невский"},
                "organizer": {"name": "Организатор"},
                "debtor": {"name": "Должник"},
            },
        )

        update_record_search_text(record)

        self.assertEqual(record.search_text, "лот tbankrot санкт-петербург недвижимость организатор должник невский")


if __name__ == "__main__":
    unittest.main()
