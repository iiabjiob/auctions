from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.procurement_sources import (
    DisabledProcurementSourceProvider,
    get_procurement_source_provider,
    list_enabled_procurement_source_providers,
    list_procurement_source_infos,
)
from app.services.procurement_sync import sync_enabled_procurement_sources


class ProcurementSourceProviderTests(unittest.IsolatedAsyncioTestCase):
    def test_registry_lists_eis_and_disabled_platform_stubs(self) -> None:
        infos = list_procurement_source_infos()
        by_code = {info.code: info for info in infos}

        self.assertTrue(by_code["zakupki"].enabled)
        self.assertEqual(by_code["zakupki"].title, "ЕИС Закупки")
        for code in ("sberbank_ast", "rts_tender", "roseltorg", "nep", "etp_gpb", "tek_torg"):
            self.assertIn(code, by_code)
            self.assertFalse(by_code[code].enabled)

    def test_enabled_provider_list_only_contains_eis_for_v1(self) -> None:
        providers = list_enabled_procurement_source_providers()

        self.assertEqual([provider.info().code for provider in providers], ["zakupki"])

    def test_disabled_provider_refuses_iteration(self) -> None:
        provider = DisabledProcurementSourceProvider(code="test", title="Test", website="https://example.test")

        with self.assertRaisesRegex(NotImplementedError, "disabled"):
            list(provider.iter_lots())

    def test_unsupported_provider_error_lists_supported_sources(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported procurement source 'missing'"):
            get_procurement_source_provider("missing")

    async def test_sync_enabled_sources_loops_enabled_providers_only(self) -> None:
        enabled = SimpleNamespace(info=lambda: SimpleNamespace(code="enabled", enabled=True))
        disabled = SimpleNamespace(info=lambda: SimpleNamespace(code="disabled", enabled=False))
        sync_provider = AsyncMock(side_effect=[SimpleNamespace(source="enabled")])

        with (
            patch("app.services.procurement_sync.list_enabled_procurement_source_providers", return_value=[enabled]),
            patch("app.services.procurement_sync.sync_procurement_source_provider", sync_provider),
        ):
            results = await sync_enabled_procurement_sources(AsyncMock(), limit=20)

        self.assertEqual([result.source for result in results], ["enabled"])
        sync_provider.assert_awaited_once()
        self.assertEqual(sync_provider.await_args.kwargs["provider"], enabled)
        self.assertEqual(sync_provider.await_args.kwargs["limit"], 20)
        self.assertFalse(disabled.info().enabled)


if __name__ == "__main__":
    unittest.main()
