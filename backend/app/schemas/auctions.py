from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ScrapedField(BaseModel):
    name: str
    value: str


class OrganizerInfo(BaseModel):
    name: str | None = None
    inn: str | None = None
    website: str | None = None
    contact_name: str | None = None
    phone: str | None = None
    fax: str | None = None


class DebtorInfo(BaseModel):
    debtor_type: str | None = None
    name: str | None = None
    inn: str | None = None
    snils: str | None = None
    bankruptcy_case_number: str | None = None
    arbitration_court: str | None = None
    arbitration_manager: str | None = None
    managers_organization: str | None = None
    region: str | None = None


class AuctionSummary(BaseModel):
    source: str = "utender"
    external_id: str | None = None
    number: str | None = None
    name: str | None = None
    url: str | None = None
    publication_date: str | None = None
    participant_form: str | None = None
    price_offer_form: str | None = None
    auction_date: str | None = None
    application_start: str | None = None
    application_deadline: str | None = None
    winner_selection_order: str | None = None
    application_order: str | None = None
    repeat: str | None = None
    efrsb_message_number: str | None = None


class LotSummary(BaseModel):
    source: str = "utender"
    external_id: str | None = None
    number: str | None = None
    name: str | None = None
    url: str | None = None
    category: str | None = None
    location: str | None = None
    region: str | None = None
    city: str | None = None
    address: str | None = None
    coordinates: str | None = None
    classifier: str | None = None
    currency: str | None = None
    initial_price: str | None = None
    current_price: str | None = None
    minimum_price: str | None = None
    status: str | None = None
    step_percent: str | None = None
    step_amount: str | None = None
    deposit_amount: str | None = None
    deposit_method: str | None = None
    deposit_payment_date: str | None = None
    deposit_return_date: str | None = None
    deposit_order: str | None = None
    applications_count: str | None = None
    description: str | None = None
    inspection_order: str | None = None


class AuctionDocument(BaseModel):
    external_id: str | None = None
    received_at: str | None = None
    name: str | None = None
    url: str | None = None
    signature_status: str | None = None
    comment: str | None = None
    document_type: str | None = None


class AuctionListItem(BaseModel):
    source: str = "utender"
    auction: AuctionSummary
    lot: LotSummary
    organizer: OrganizerInfo
    winner: str | None = None


class AuctionListResponse(BaseModel):
    items: list[AuctionListItem]


class LotDetailResponse(BaseModel):
    source: str = "utender"
    url: str
    auction: AuctionSummary
    lot: LotSummary
    documents: list[AuctionDocument]
    raw_fields: list[ScrapedField]
    raw_tables: list[list[str]]


class AuctionDetailResponse(BaseModel):
    source: str = "utender"
    url: str
    auction: AuctionSummary
    organizer: OrganizerInfo
    debtor: DebtorInfo
    lots: list[LotSummary]
    documents: list[AuctionDocument]
    raw_fields: list[ScrapedField]
    raw_tables: list[list[str]]


class AuctionSourceInfo(BaseModel):
    code: str
    title: str
    website: str
    enabled: bool = True
    supports_live_fetch: bool = True


class LotFreshness(BaseModel):
    is_new: bool = False
    published_at: str | None = None
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    status_changed_at: str | None = None


class LotRating(BaseModel):
    score: int
    level: str
    reasons: list[str]


class LotAnalysis(BaseModel):
    status: str = "review"
    color: str = "yellow"
    label: str = "Считать детальнее"
    category: str | None = None
    matched_keyword: str | None = None
    is_excluded: bool = False
    exclusion_keyword: str | None = None
    legal_risk: str = "medium"
    completeness: str = "partial"
    has_documents: bool = False
    has_photos: bool = False
    hours_to_deadline: int | None = None
    reasons: list[str] = Field(default_factory=list)


class DatagridColumn(BaseModel):
    key: str
    title: str
    data_type: str = "text"
    sortable: bool = True
    filterable: bool = True
    width: int | None = None


class LotDatagridRow(BaseModel):
    row_id: str
    source: str
    source_title: str
    auction_id: str | None = None
    auction_number: str | None = None
    auction_name: str | None = None
    auction_url: str | None = None
    publication_date: str | None = None
    lot_id: str | None = None
    lot_number: str | None = None
    lot_name: str | None = None
    lot_url: str | None = None
    category: str | None = None
    location: str | None = None
    location_region: str | None = None
    location_city: str | None = None
    location_address: str | None = None
    location_coordinates: str | None = None
    model_category: str | None = None
    status: str | None = None
    initial_price: str | None = None
    initial_price_value: Decimal | None = None
    current_price: str | None = None
    current_price_value: Decimal | None = None
    minimum_price: str | None = None
    minimum_price_value: Decimal | None = None
    organizer_name: str | None = None
    application_deadline: str | None = None
    auction_date: str | None = None
    market_value: Decimal | None = None
    platform_fee: Decimal | None = None
    delivery_cost: Decimal | None = None
    dismantling_cost: Decimal | None = None
    repair_cost: Decimal | None = None
    storage_cost: Decimal | None = None
    legal_cost: Decimal | None = None
    other_costs: Decimal | None = None
    target_profit: Decimal | None = None
    total_expenses: Decimal | None = None
    full_entry_cost: Decimal | None = None
    potential_profit: Decimal | None = None
    roi: Decimal | None = None
    market_discount: Decimal | None = None
    formula_max_purchase_price: Decimal | None = None
    exclude_from_analysis: bool = False
    exclusion_reason: str | None = None
    freshness: LotFreshness
    rating: LotRating
    analysis: LotAnalysis = Field(default_factory=LotAnalysis)
    work_decision_status: str | None = None


class LotDatagridFilters(BaseModel):
    period: str = "month"
    source: str | None = None
    q: str | None = None
    status: str | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    only_new: bool = False
    shortlist: bool = False
    min_rating: int | None = None


class LotDatagridPagination(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class LotDatagridResponse(BaseModel):
    columns: list[DatagridColumn]
    rows: list[LotDatagridRow]
    filters: LotDatagridFilters
    total: int
    pagination: LotDatagridPagination
    available_sources: list[AuctionSourceInfo]


class SourceSyncResult(BaseModel):
    source: str
    fetched: int
    created: int
    updated: int
    unchanged: int
    status_changed: int


class LotAnalog(BaseModel):
    title: str | None = None
    price: Decimal | None = None
    url: str | None = None
    source: str | None = None
    comment: str | None = None


class LotWorkItemBase(BaseModel):
    decision_status: str | None = None
    assignee: str | None = None
    comment: str | None = None
    inspection_at: datetime | None = None
    inspection_result: str | None = None
    final_decision: str | None = None
    investor: str | None = None
    deposit_status: str | None = None
    application_status: str | None = None
    exclude_from_analysis: bool | None = None
    exclusion_reason: str | None = None
    category_override: str | None = None
    max_purchase_price: Decimal | None = None
    market_value: Decimal | None = None
    platform_fee: Decimal | None = None
    delivery_cost: Decimal | None = None
    dismantling_cost: Decimal | None = None
    repair_cost: Decimal | None = None
    storage_cost: Decimal | None = None
    legal_cost: Decimal | None = None
    other_costs: Decimal | None = None
    target_profit: Decimal | None = None
    analogs: list[LotAnalog] = Field(default_factory=list)


class LotWorkItemUpdate(LotWorkItemBase):
    pass


class LotWorkItemResponse(LotWorkItemBase):
    id: int | None = None
    lot_record_id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LotEconomyResponse(BaseModel):
    current_price: Decimal | None = None
    market_value: Decimal | None = None
    total_expenses: Decimal | None = None
    full_entry_cost: Decimal | None = None
    potential_profit: Decimal | None = None
    roi: Decimal | None = None
    market_discount: Decimal | None = None
    target_profit: Decimal | None = None
    max_purchase_price: Decimal | None = None


class LotFieldChange(BaseModel):
    label: str
    previous: str | None = None
    current: str | None = None
    change_type: str = "changed"


class LotChangeSummary(BaseModel):
    observations_count: int = 0
    detail_observations_count: int = 0
    last_observed_at: datetime | None = None
    previous_observed_at: datetime | None = None
    last_detail_observed_at: datetime | None = None
    previous_detail_observed_at: datetime | None = None
    status_changed_at: datetime | None = None
    content_changed: bool = False
    detail_changed: bool = False
    fields: list[LotFieldChange] = Field(default_factory=list)


class LotWorkspaceResponse(BaseModel):
    record_id: int
    row: LotDatagridRow
    lot_detail: LotDetailResponse | None = None
    auction_detail: AuctionDetailResponse | None = None
    detail_cached_at: datetime | None = None
    work_item: LotWorkItemResponse
    economy: LotEconomyResponse
    changes: LotChangeSummary
