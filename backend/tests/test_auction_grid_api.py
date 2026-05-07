from __future__ import annotations

import unittest

from app.schemas.auction_grid import AuctionLotsGridPullRequest, AuctionLotsGridPullResponse
from app.services.auction_grid import _histogram_filter_model, _normalize_sort_model


class AuctionGridApiTests(unittest.TestCase):
    def test_pull_request_accepts_flat_range_fields(self) -> None:
        request = AuctionLotsGridPullRequest.model_validate(
            {
                "startRow": 10,
                "endRow": 25,
                "sortModel": [{"colId": "ratingScore", "sort": "desc"}],
                "filterModel": {"columnFilters": {}},
            }
        )

        self.assertEqual(request.resolved_start_row, 10)
        self.assertEqual(request.resolved_end_row, 25)
        self.assertEqual(request.sort_model, [{"colId": "ratingScore", "sort": "desc"}])

    def test_pull_request_accepts_nested_range_fields(self) -> None:
        request = AuctionLotsGridPullRequest.model_validate({"range": {"startRow": 0, "endRow": 50}})

        self.assertEqual(request.resolved_start_row, 0)
        self.assertEqual(request.resolved_end_row, 50)

    def test_pull_response_uses_dataset_version_alias(self) -> None:
        payload = AuctionLotsGridPullResponse(rows=[], total=0, dataset_version=7).model_dump(by_alias=True)

        self.assertEqual(payload, {"rows": [], "total": 0, "datasetVersion": 7})

    def test_sort_model_normalizes_affino_and_protocol_shapes(self) -> None:
        normalized = _normalize_sort_model(
            [
                {"key": "price", "direction": "asc"},
                {"colId": "ratingScore", "sort": "desc"},
                {"field": "ignored", "sort": "invalid"},
            ]
        )

        self.assertEqual(
            normalized,
            [
                {"key": "price", "direction": "asc"},
                {"key": "ratingScore", "direction": "desc"},
            ],
        )

    def test_histogram_ignore_self_filter_removes_active_column_filter(self) -> None:
        filter_model = {
            "columnFilters": {
                "status": {"kind": "valueSet", "tokens": ["string:open"]},
                "source": {"kind": "valueSet", "tokens": ["string:tbankrot"]},
            },
            "advancedFilters": {
                "status": {"clauses": []},
            },
        }

        filtered = _histogram_filter_model(filter_model, "status", {"ignoreSelfFilter": True})

        self.assertEqual(filtered["columnFilters"], {"source": {"kind": "valueSet", "tokens": ["string:tbankrot"]}})
        self.assertEqual(filtered["advancedFilters"], {})
        self.assertIn("status", filter_model["columnFilters"])


if __name__ == "__main__":
    unittest.main()
