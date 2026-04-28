from __future__ import annotations

from typing import Protocol

from app.schemas.auctions import AuctionDetailResponse, AuctionListItem, AuctionSourceInfo, LotDetailResponse
from app.services.fabrikant_scraper import (
    fetch_auction_detail as fetch_fabrikant_auction_detail,
    fetch_auction_list as fetch_fabrikant_auction_list,
    fetch_auction_publication_date as fetch_fabrikant_auction_publication_date,
    fetch_lot_detail as fetch_fabrikant_lot_detail,
)
from app.services.utender_scraper import (
    fetch_auction_detail,
    fetch_auction_list,
    fetch_auction_publication_date,
    fetch_lot_detail,
)


class AuctionSourceProvider(Protocol):
    code: str
    title: str
    website: str

    def info(self) -> AuctionSourceInfo:
        ...

    def list_lots(self, limit: int | None = None) -> list[AuctionListItem]:
        ...

    def get_lot(self, lot_id: str) -> LotDetailResponse:
        ...

    def get_auction(self, auction_id: str) -> AuctionDetailResponse:
        ...

    def get_auction_publication_date(self, auction_id: str) -> str | None:
        ...


class UtenderSourceProvider:
    code = "utender"
    title = "uTender"
    website = "http://utender.ru"

    def info(self) -> AuctionSourceInfo:
        return AuctionSourceInfo(code=self.code, title=self.title, website=self.website)

    def list_lots(self, limit: int | None = None) -> list[AuctionListItem]:
        return fetch_auction_list(limit=limit)

    def get_lot(self, lot_id: str) -> LotDetailResponse:
        return fetch_lot_detail(lot_id)

    def get_auction(self, auction_id: str) -> AuctionDetailResponse:
        return fetch_auction_detail(auction_id)

    def get_auction_publication_date(self, auction_id: str) -> str | None:
        return fetch_auction_publication_date(auction_id)


class FabrikantSourceProvider:
    code = "fabrikant"
    title = "Fabrikant"
    website = "https://www.fabrikant.ru"

    def info(self) -> AuctionSourceInfo:
        return AuctionSourceInfo(code=self.code, title=self.title, website=self.website)

    def list_lots(self, limit: int | None = None) -> list[AuctionListItem]:
        return fetch_fabrikant_auction_list(limit=limit)

    def get_lot(self, lot_id: str) -> LotDetailResponse:
        return fetch_fabrikant_lot_detail(lot_id)

    def get_auction(self, auction_id: str) -> AuctionDetailResponse:
        return fetch_fabrikant_auction_detail(auction_id)

    def get_auction_publication_date(self, auction_id: str) -> str | None:
        return fetch_fabrikant_auction_publication_date(auction_id)


SOURCE_PROVIDERS: dict[str, AuctionSourceProvider] = {
    FabrikantSourceProvider.code: FabrikantSourceProvider(),
    UtenderSourceProvider.code: UtenderSourceProvider(),
}


def get_source_provider(source: str) -> AuctionSourceProvider:
    try:
        return SOURCE_PROVIDERS[source]
    except KeyError as error:
        supported = ", ".join(sorted(SOURCE_PROVIDERS))
        raise ValueError(f"Unsupported auction source '{source}'. Supported: {supported}") from error


def list_source_infos() -> list[AuctionSourceInfo]:
    return [provider.info() for provider in SOURCE_PROVIDERS.values()]