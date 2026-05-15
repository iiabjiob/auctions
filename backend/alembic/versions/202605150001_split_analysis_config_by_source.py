"""split analysis config by source

Revision ID: 202605150001
Revises: 202605140006
Create Date: 2026-05-15 00:01:00.000000
"""

from __future__ import annotations

import json

from alembic import op


revision = "202605150001"
down_revision = "202605140006"
branch_labels = None
depends_on = None


PROCUREMENT_CATEGORY_KEYWORDS = {
    "Спецодежда": (
        "спецодежда",
        "специальная одежда",
        "рабочая одежда",
        "костюм рабочий",
        "костюм летний",
        "костюм зимний",
        "комбинезон",
        "куртка рабочая",
        "брюки рабочие",
        "жилет сигнальный",
        "форма рабочая",
    ),
    "Медицинская одежда": (
        "медицинская одежда",
        "халат медицинский",
        "костюм медицинский",
        "одежда медицинская",
        "форма медицинская",
        "одежда для медперсонала",
        "брюки медицинские",
        "блуза медицинская",
    ),
    "Спортивная одежда": (
        "спортивная форма",
        "спортивный костюм",
        "форма спортивная",
        "футболка спортивная",
        "шорты спортивные",
        "экипировка спортивная",
        "форма команды",
    ),
    "Униформа": (
        "униформа",
        "форменная одежда",
        "корпоративная одежда",
        "форма охранника",
        "форма персонала",
        "форма для сотрудников",
        "одежда для сотрудников",
    ),
    "Пошив": (
        "пошив",
        "изготовление одежды",
        "поставка одежды",
        "изготовление формы",
        "пошив формы",
        "пошив спецодежды",
    ),
    "Текстиль с пошивом": (
        "постельное белье",
        "полотенца",
        "текстиль",
        "комплекты белья",
        "белье с пошивом",
    ),
}

PROCUREMENT_EXCLUSION_KEYWORDS = (
    "обувь",
    "сапоги",
    "ботинки",
    "ботинок",
    "перчатки",
    "каски",
    "респираторы",
    "канцтовары",
    "мебель",
    "инвентарь",
    "услуги прачечной",
    "прачечная",
    "химчистка",
    "ремонт одежды",
)


def _jsonb_literal(value) -> str:  # noqa: ANN001
    return "'" + json.dumps(value, ensure_ascii=False).replace("'", "''") + "'::jsonb"


def upgrade() -> None:
    op.execute(
        "DELETE FROM auction_analysis_configs "
        "WHERE id = 'auction' AND EXISTS (SELECT 1 FROM auction_analysis_configs WHERE id = 'default')"
    )
    op.execute("UPDATE auction_analysis_configs SET id = 'auction' WHERE id = 'default'")

    procurement_category_rules = [
        {"category": category, "keywords": list(keywords)}
        for category, keywords in PROCUREMENT_CATEGORY_KEYWORDS.items()
    ]
    procurement_defaults_sql = f"""
        INSERT INTO auction_analysis_configs (
            id,
            category_rules,
            exclusion_keywords,
            legal_risk_rules,
            owner_profile,
            dimension_weights,
            created_at,
            updated_at
        )
        SELECT
            'procurement',
            {_jsonb_literal(procurement_category_rules)},
            {_jsonb_literal(list(PROCUREMENT_EXCLUSION_KEYWORDS))},
            {_jsonb_literal({"high_keywords": [], "medium_keywords": [], "medium_categories": []})},
            {_jsonb_literal(
                {
                    "target_regions": [],
                    "target_categories": [],
                    "min_budget": None,
                    "max_budget": None,
                    "minimum_roi": None,
                    "minimum_market_discount": None,
                    "excluded_terms": [],
                    "discouraged_terms": [],
                    "max_delivery_distance_km": None,
                    "allow_dismantling": True,
                    "legal_risk_tolerance": "medium",
                    "require_documents": False,
                    "require_photos": False,
                }
            )},
            {_jsonb_literal(
                {
                    "economics": "1.0",
                    "risk": "1.0",
                    "urgency": "1.0",
                    "data_quality": "1.0",
                    "operational_readiness": "1.0",
                    "owner_fit": "1.0",
                    "manual_intent": "1.0",
                }
            )},
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        WHERE NOT EXISTS (
            SELECT 1
            FROM auction_analysis_configs
            WHERE id = 'procurement'
        )
    """
    op.execute(procurement_defaults_sql)


def downgrade() -> None:
    op.execute("DELETE FROM auction_analysis_configs WHERE id = 'procurement'")
    op.execute(
        "DELETE FROM auction_analysis_configs "
        "WHERE id = 'default' AND EXISTS (SELECT 1 FROM auction_analysis_configs WHERE id = 'auction')"
    )
    op.execute("UPDATE auction_analysis_configs SET id = 'default' WHERE id = 'auction'")
