from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi import HTTPException

from app.models import FilterPresetModel, UserInterestProfileModel
from app.schemas.user_interest_profiles import (
    UserInterestProfileCreate,
    UserInterestProfileFromPreset,
    UserInterestProfileUpdate,
)
from app.services.user_interest_profiles import UserInterestProfileService, build_profile_payload_from_filter_preset


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


def make_profile(**overrides: object) -> UserInterestProfileModel:
    values = {
        "id": "uip_existing",
        "owner_user_id": "user-1",
        "name": "BMW cars",
        "profile_payload": {"desired_keywords": ["BMW"]},
        "min_rating": 70,
        "notification_priority_threshold": "medium",
        "telegram_enabled": True,
        "is_active": True,
    }
    values.update(overrides)
    return UserInterestProfileModel(**values)


def make_preset(**overrides: object) -> FilterPresetModel:
    values = {
        "id": "preset_1",
        "owner_user_id": "user-1",
        "scope": "auction",
        "name": "BMW cars",
        "filters": {
            "minPrice": "2000000",
            "maxPrice": "5000000",
            "minRating": 85,
            "status": "BMW",
        },
        "grid_view": None,
        "is_favorite": False,
    }
    values.update(overrides)
    return FilterPresetModel(**values)


class UserInterestProfileServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_build_profile_payload_from_filter_preset_maps_supported_filters(self) -> None:
        payload = build_profile_payload_from_filter_preset(
            {
                "minPrice": "2 000 000",
                "maxPrice": "5 000 000",
                "status": "BMW",
                "analysisCategory": "Автомобили",
                "targetRegions": ["Москва", "Московская область"],
                "stopWords": "битый, залог",
            }
        )

        self.assertEqual(payload["budget_min"], "2000000")
        self.assertEqual(payload["budget_max"], "5000000")
        self.assertEqual(payload["desired_keywords"], ["BMW"])
        self.assertEqual(payload["target_categories"], ["Автомобили"])
        self.assertEqual(payload["target_regions"], ["Москва", "Московская область"])
        self.assertEqual(payload["stop_words"], ["битый", "залог"])
        self.assertEqual(payload["allowed_legal_risks"], ["low", "medium"])

    async def test_create_stores_normalized_profile_for_user(self) -> None:
        session = FakeSession()
        service = UserInterestProfileService()

        response = await service.create(
            session,
            make_user(),
            UserInterestProfileCreate(
                name="  Special machinery  ",
                profile_payload={"target_categories": ["Спецтехника"], "budget_min": "2000000"},
                min_rating=80,
            ),
        )

        self.assertEqual(response.name, "Special machinery")
        self.assertEqual(response.owner_user_id, "user-1")
        self.assertEqual(response.min_rating, 80)
        self.assertEqual(len(session.added), 1)
        created = session.added[0]
        self.assertIsInstance(created, UserInterestProfileModel)
        self.assertEqual(created.owner_user_id, "user-1")
        self.assertEqual(created.profile_payload["budget_min"], "2000000")
        self.assertEqual(session.commits, 1)
        self.assertEqual(session.refreshed, [created])

    async def test_create_from_preset_stores_link_and_converted_payload(self) -> None:
        preset = make_preset()
        session = FakeSession(scalar_results=[preset, None])
        service = UserInterestProfileService()

        response = await service.create_from_preset(
            session,
            make_user(),
            UserInterestProfileFromPreset(preset_id=preset.id, telegram_enabled=True),
        )

        self.assertEqual(response.name, "BMW cars")
        self.assertEqual(response.source_filter_preset_id, preset.id)
        self.assertEqual(response.min_rating, 85)
        self.assertEqual(response.profile_payload["budget_min"], "2000000")
        self.assertEqual(response.profile_payload["budget_max"], "5000000")
        self.assertEqual(response.profile_payload["desired_keywords"], ["BMW"])
        created = session.added[0]
        self.assertEqual(created.source_filter_preset_id, preset.id)
        self.assertEqual(session.commits, 1)

    async def test_create_from_preset_requires_owned_preset(self) -> None:
        session = FakeSession(scalar_results=[None])
        service = UserInterestProfileService()

        with self.assertRaises(HTTPException) as error:
            await service.create_from_preset(
                session,
                make_user("user-2"),
                UserInterestProfileFromPreset(preset_id="preset_1"),
            )

        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(error.exception.detail, "Preset not found.")
        self.assertEqual(session.added, [])

    async def test_create_duplicate_name_returns_conflict(self) -> None:
        session = FakeSession(scalar_results=[make_profile()])
        service = UserInterestProfileService()

        with self.assertRaises(HTTPException) as error:
            await service.create(session, make_user(), UserInterestProfileCreate(name="BMW cars"))

        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(error.exception.detail, "Profile with this name already exists.")
        self.assertEqual(session.added, [])
        self.assertEqual(session.commits, 0)

    async def test_update_requires_owned_profile(self) -> None:
        session = FakeSession(scalar_results=[None])
        service = UserInterestProfileService()

        with self.assertRaises(HTTPException) as error:
            await service.update(session, make_user("user-2"), "uip_existing", UserInterestProfileUpdate(min_rating=90))

        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(error.exception.detail, "Profile not found.")
        self.assertEqual(session.commits, 0)

    async def test_update_applies_fields_and_checks_name_conflict(self) -> None:
        profile = make_profile()
        session = FakeSession(scalar_results=[profile, None])
        service = UserInterestProfileService()

        response = await service.update(
            session,
            make_user(),
            profile.id,
            UserInterestProfileUpdate(
                name="BMW premium",
                min_rating=85,
                telegram_enabled=False,
                profile_payload={"desired_keywords": ["BMW", "M5"]},
            ),
        )

        self.assertEqual(response.name, "BMW premium")
        self.assertEqual(response.min_rating, 85)
        self.assertFalse(response.telegram_enabled)
        self.assertEqual(profile.name, "BMW premium")
        self.assertEqual(profile.profile_payload["desired_keywords"], ["BMW", "M5"])
        self.assertEqual(session.commits, 1)
        self.assertEqual(session.refreshed, [profile])

    async def test_refresh_from_preset_updates_linked_profile_payload(self) -> None:
        profile = make_profile(source_filter_preset_id="preset_1", min_rating=70)
        preset = make_preset(filters={"minPrice": "3000000", "status": "Mercedes", "minRating": 90})
        session = FakeSession(scalar_results=[profile, preset])
        service = UserInterestProfileService()

        response = await service.refresh_from_preset(session, make_user(), profile.id)

        self.assertEqual(response.profile_payload["budget_min"], "3000000")
        self.assertEqual(response.profile_payload["desired_keywords"], ["Mercedes"])
        self.assertEqual(response.min_rating, 90)
        self.assertEqual(profile.profile_payload["budget_min"], "3000000")
        self.assertEqual(session.commits, 1)
        self.assertEqual(session.refreshed, [profile])

    async def test_refresh_from_preset_requires_linked_profile(self) -> None:
        profile = make_profile(source_filter_preset_id=None)
        session = FakeSession(scalar_results=[profile])
        service = UserInterestProfileService()

        with self.assertRaises(HTTPException) as error:
            await service.refresh_from_preset(session, make_user(), profile.id)

        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(error.exception.detail, "Profile is not linked to a preset.")
        self.assertEqual(session.commits, 0)

    async def test_delete_requires_ownership_and_deletes_owned_profile(self) -> None:
        profile = make_profile()
        service = UserInterestProfileService()

        missing_session = FakeSession(scalar_results=[None])
        with self.assertRaises(HTTPException) as error:
            await service.delete(missing_session, make_user("user-2"), profile.id)
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(missing_session.deleted, [])

        owned_session = FakeSession(scalar_results=[profile])
        await service.delete(owned_session, make_user(), profile.id)

        self.assertEqual(owned_session.deleted, [profile])
        self.assertEqual(owned_session.commits, 1)

    async def test_list_returns_profiles_for_current_user(self) -> None:
        profile = make_profile()
        session = FakeSession(scalars_result=[profile])
        service = UserInterestProfileService()

        response = await service.list_for_user(session, make_user())

        self.assertEqual([item.id for item in response], [profile.id])
        self.assertEqual([item.owner_user_id for item in response], ["user-1"])
        self.assertEqual(len(session.scalars_statements), 1)


if __name__ == "__main__":
    unittest.main()
