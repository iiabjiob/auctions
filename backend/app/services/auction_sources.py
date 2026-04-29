from __future__ import annotations

from typing import Protocol

from app.core.config import get_settings
from app.schemas.auctions import AuctionDetailResponse, AuctionListItem, AuctionSourceInfo, LotDetailResponse
from app.services.tbankrot_scraper import fetch_auction_list as fetch_tbankrot_auction_list
from app.services.tbankrot_scraper import fetch_lot_detail as fetch_tbankrot_lot_detail


settings = get_settings()


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


class TBankrotSourceProvider:
    code = "tbankrot"
    title = "TBankrot"
    website = "https://tbankrot.ru"

    def info(self) -> AuctionSourceInfo:
        return AuctionSourceInfo(code=self.code, title=self.title, website=self.website)

    def list_lots(self, limit: int | None = None) -> list[AuctionListItem]:
        auth_email = settings.tbankrot_login
        auth_password = settings.tbankrot_password
        authenticate = settings.tbankrot_auth_enabled or bool(auth_email and auth_password)
        pages = None if settings.tbankrot_pages <= 0 else settings.tbankrot_pages
        return fetch_tbankrot_auction_list(
            limit=limit,
            include_price_schedule=settings.tbankrot_include_price_schedule,
            page=1,
            pages=pages,
            authenticate=authenticate,
            auth_email=auth_email,
            auth_password=auth_password,
        )

    def get_lot(self, lot_id: str) -> LotDetailResponse:
        auth_email = settings.tbankrot_login
        auth_password = settings.tbankrot_password
        authenticate = settings.tbankrot_auth_enabled or bool(auth_email and auth_password)
        return fetch_tbankrot_lot_detail(
            lot_id,
            authenticate=authenticate,
            auth_email=auth_email,
            auth_password=auth_password,
        )

    def get_auction(self, auction_id: str) -> AuctionDetailResponse:
        raise NotImplementedError("TBankrot auction detail parsing is not implemented yet")

    def get_auction_publication_date(self, auction_id: str) -> str | None:
        return None


SOURCE_PROVIDERS: dict[str, AuctionSourceProvider] = {
    TBankrotSourceProvider.code: TBankrotSourceProvider(),
}


def get_source_provider(source: str) -> AuctionSourceProvider:
    try:
        return SOURCE_PROVIDERS[source]
    except KeyError as error:
        supported = ", ".join(sorted(SOURCE_PROVIDERS))
        raise ValueError(f"Unsupported auction source '{source}'. Supported: {supported}") from error


def list_source_infos() -> list[AuctionSourceInfo]:
    return [provider.info() for provider in SOURCE_PROVIDERS.values()]