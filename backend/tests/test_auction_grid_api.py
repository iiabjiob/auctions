from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.schemas.auction_grid import AuctionLotsGridPullRequest, AuctionLotsGridPullResponse, AuctionLotsGridSummary
from app.schemas.auctions import LotDatagridRow
from app.services.auction_grid import _histogram_filter_model, _normalize_sort_model, pull_auction_lots_grid


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
        payload = AuctionLotsGridPullResponse(
            rows=[],
            total=0,
            dataset_version=7,
            summary=AuctionLotsGridSummary(total=0, new_count=1, open_applications_count=2, high_rating_count=3),
        ).model_dump(by_alias=True)

        self.assertEqual(
            payload,
            {
                "rows": [],
                "total": 0,
                "datasetVersion": 7,
                "summary": {
                    "total": 0,
                    "newCount": 1,
                    "openApplicationsCount": 2,
                    "highRatingCount": 3,
                },
            },
        )

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


class AuctionGridPullServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_pull_response_indexes_are_viewport_positions_not_record_ids(self) -> None:
        request = AuctionLotsGridPullRequest.model_validate({"startRow": 10, "endRow": 12})
        records = [SimpleNamespace(id=101), SimpleNamespace(id=204)]
        rows = [
            LotDatagridRow.model_construct(row_id="row-101"),
            LotDatagridRow.model_construct(row_id="row-204"),
        ]

        with (
            patch("app.services.auction_grid.read_grid_dataset_version", AsyncMock(return_value=7)),
            patch("app.services.auction_grid.pull_persisted_lots_for_grid", AsyncMock(return_value=(list(zip(records, rows)), 100))),
            patch(
                "app.services.auction_grid.summarize_persisted_lots_for_grid",
                AsyncMock(
                    return_value=AuctionLotsGridSummary(
                        total=100,
                        new_count=9,
                        open_applications_count=8,
                        high_rating_count=7,
                    )
                ),
            ),
            patch("app.services.auction_grid.auction_lot_grid_row_id", side_effect=lambda record: f"record-{record.id}"),
        ):
            response = await pull_auction_lots_grid(AsyncMock(), request)

        self.assertEqual([row.index for row in response.rows], [10, 11])
        self.assertEqual([row.id for row in response.rows], ["record-101", "record-204"])
        self.assertEqual(response.total, 100)
        self.assertEqual(response.summary.new_count, 9)
        self.assertEqual(response.summary.open_applications_count, 8)
        self.assertEqual(response.summary.high_rating_count, 7)
        self.assertEqual(response.dataset_version, 7)


if __name__ == "__main__":
    unittest.main()
