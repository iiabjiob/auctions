from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from app.schemas.procurements import ProcurementLotItem, ProcurementSourceInfo
from app.services.zakupki_scraper import fetch_procurement_list, source_info as zakupki_source_info


class ProcurementSourceProvider(Protocol):
    code: str
    title: str
    website: str
    enabled: bool
    parser_version: str | None

    def info(self) -> ProcurementSourceInfo:
        ...

    def iter_lots(self, limit: int | None = None, *, page: int = 1) -> Iterable[ProcurementLotItem]:
        ...

    def list_lots_page(self, *, keyword: str, page: int = 1, limit: int | None = None) -> list[ProcurementLotItem]:
        ...

    def get_lot_detail(self, external_id: str) -> dict | None:
        ...

    def get_documents(self, external_id: str) -> list[dict]:
        ...


class EisZakupkiProvider:
    code = "zakupki"
    title = "ЕИС Закупки"
    website = "https://zakupki.gov.ru"
    enabled = True
    parser_version = "zakupki-eis-v1"

    def info(self) -> ProcurementSourceInfo:
        info = zakupki_source_info()
        return ProcurementSourceInfo(code=self.code, title=info.title, website=info.website, enabled=True)

    def iter_lots(self, limit: int | None = None, *, page: int = 1) -> Iterable[ProcurementLotItem]:
        return fetch_procurement_list(limit=limit, page=page)

    def list_lots_page(self, *, keyword: str, page: int = 1, limit: int | None = None) -> list[ProcurementLotItem]:
        return fetch_procurement_list(limit=limit, page=page, search_keywords=(keyword,))

    def get_lot_detail(self, external_id: str) -> dict | None:
        del external_id
        return None

    def get_documents(self, external_id: str) -> list[dict]:
        del external_id
        return []


@dataclass(frozen=True)
class DisabledProcurementSourceProvider:
    code: str
    title: str
    website: str
    enabled: bool = False
    parser_version: str | None = None

    def info(self) -> ProcurementSourceInfo:
        return ProcurementSourceInfo(code=self.code, title=self.title, website=self.website, enabled=False)

    def iter_lots(self, limit: int | None = None, *, page: int = 1) -> Iterable[ProcurementLotItem]:
        del limit, page
        raise NotImplementedError(f"Procurement provider '{self.code}' is disabled")

    def list_lots_page(self, *, keyword: str, page: int = 1, limit: int | None = None) -> list[ProcurementLotItem]:
        del keyword, page, limit
        raise NotImplementedError(f"Procurement provider '{self.code}' is disabled")

    def get_lot_detail(self, external_id: str) -> dict | None:
        del external_id
        return None

    def get_documents(self, external_id: str) -> list[dict]:
        del external_id
        return []


SOURCE_PROVIDERS: dict[str, ProcurementSourceProvider] = {
    EisZakupkiProvider.code: EisZakupkiProvider(),
    "sberbank_ast": DisabledProcurementSourceProvider(
        code="sberbank_ast",
        title="Сбербанк-АСТ",
        website="https://www.sberbank-ast.ru",
    ),
    "rts_tender": DisabledProcurementSourceProvider(
        code="rts_tender",
        title="РТС-тендер",
        website="https://www.rts-tender.ru",
    ),
    "roseltorg": DisabledProcurementSourceProvider(
        code="roseltorg",
        title="Росэлторг",
        website="https://www.roseltorg.ru",
    ),
    "nep": DisabledProcurementSourceProvider(
        code="nep",
        title="НЭП",
        website="https://www.etp-ets.ru",
    ),
    "etp_gpb": DisabledProcurementSourceProvider(
        code="etp_gpb",
        title="ЭТП ГПБ",
        website="https://etpgpb.ru",
    ),
    "tek_torg": DisabledProcurementSourceProvider(
        code="tek_torg",
        title="ТЭК-Торг",
        website="https://www.tektorg.ru",
    ),
}


def get_procurement_source_provider(source: str) -> ProcurementSourceProvider:
    try:
        return SOURCE_PROVIDERS[source]
    except KeyError as error:
        supported = ", ".join(sorted(SOURCE_PROVIDERS))
        raise ValueError(f"Unsupported procurement source '{source}'. Supported: {supported}") from error


def list_procurement_source_infos(*, enabled_only: bool = False) -> list[ProcurementSourceInfo]:
    providers = SOURCE_PROVIDERS.values()
    if enabled_only:
        providers = [provider for provider in providers if provider.info().enabled]
    return [provider.info() for provider in providers]


def list_enabled_procurement_source_providers() -> list[ProcurementSourceProvider]:
    return [provider for provider in SOURCE_PROVIDERS.values() if provider.info().enabled]
