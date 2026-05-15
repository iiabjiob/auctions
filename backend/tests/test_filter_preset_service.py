from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi import HTTPException

from app.models import FilterPresetModel
from app.schemas.filter_presets import FilterPresetCreate
from app.services.filter_presets import FilterPresetService


class FakeScalars:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def all(self) -> list[object]:
        return self.values


class FakeSession:
    def __init__(
        self,
        *,
        scalar_results: list[object | None] | None = None,
        scalars_result: list[object] | None = None,
    ) -> None:
        self.scalar_results = list(scalar_results or [])
        self.scalars_result = list(scalars_result or [])
        self.scalar_statements = []
        self.scalars_statements = []
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.commits = 0
        self.refreshed: list[object] = []

    async def scalar(self, statement):  # noqa: ANN001
        self.scalar_statements.append(statement)
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    async def scalars(self, statement):  # noqa: ANN001
        self.scalars_statements.append(statement)
        return FakeScalars(self.scalars_result)

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:
        return None

    async def refresh(self, obj: object) -> None:
        self.refreshed.append(obj)

    async def delete(self, obj: object) -> None:
        self.deleted.append(obj)


def make_user(user_id: str = "user-1") -> SimpleNamespace:
    return SimpleNamespace(id=user_id)


def make_preset(**overrides: object) -> FilterPresetModel:
    values = {
        "id": "preset_1",
        "owner_user_id": "user-1",
        "scope": "auction",
        "name": "BMW cars",
        "filters": {"source": "tbankrot"},
        "grid_view": None,
        "is_favorite": False,
    }
    values.update(overrides)
    return FilterPresetModel(**values)


class FilterPresetServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_for_user_uses_scope_filter(self) -> None:
        session = FakeSession(scalars_result=[make_preset(scope="auction")])
        service = FilterPresetService()

        response = await service.list_for_user(session, make_user(), "auction")

        self.assertEqual(len(response), 1)
        self.assertEqual(response[0].scope, "auction")
        self.assertEqual(len(session.scalars_statements), 1)
        self.assertIn("filter_presets.scope", str(session.scalars_statements[0]))

    async def test_create_sets_scope_and_returns_scoped_response(self) -> None:
        session = FakeSession()
        service = FilterPresetService()

        response = await service.create(
            session,
            make_user(),
            FilterPresetCreate(name="Auction saved view", filters={"source": "tbankrot"}),
            "auction",
        )

        self.assertEqual(response.scope, "auction")
        self.assertEqual(len(session.added), 1)
        created = session.added[0]
        self.assertIsInstance(created, FilterPresetModel)
        self.assertEqual(created.scope, "auction")
        self.assertEqual(session.commits, 1)

    async def test_rejects_invalid_scope(self) -> None:
        session = FakeSession()
        service = FilterPresetService()

        with self.assertRaises(HTTPException) as error:
            await service.list_for_user(session, make_user(), "other")  # type: ignore[arg-type]

        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(error.exception.detail, "Invalid preset scope.")
