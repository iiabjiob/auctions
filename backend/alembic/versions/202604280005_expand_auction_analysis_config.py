"""expand auction analysis config

Revision ID: 202604280005
Revises: 202604280004
Create Date: 2026-04-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202604280005"
down_revision: Union[str, None] = "202604280004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auction_analysis_configs",
        sa.Column(
            "exclusion_keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "auction_analysis_configs",
        sa.Column(
            "legal_risk_rules",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.execute(
        """
        UPDATE auction_analysis_configs
        SET legal_risk_rules = jsonb_build_object(
            'high_keywords', jsonb_build_array(
                'обремен', 'сервитут', 'арест', 'залог', 'оспарив',
                'право требования', 'права требования', 'дебитор',
                'доля в ооо', 'акции', 'товарный знак', 'товарные знаки'
            ),
            'medium_keywords', jsonb_build_array(
                'земельный участок', 'нежилое здание', 'имущественный комплекс', 'аренда', 'незаверш'
            ),
            'medium_categories', jsonb_build_array('Земля и базы')
        ),
        exclusion_keywords = jsonb_build_array(
            'дебиторская задолженность', 'права требования', 'право требования',
            'доли в ооо', 'доля в ооо', 'акции', 'товарные знаки', 'товарный знак',
            'бытовая мебель', 'одежда', 'личные вещи', 'квартира', 'квартиры',
            'легковой автомобиль', 'легковые автомобили'
        )
        """
    )
    op.alter_column("auction_analysis_configs", "exclusion_keywords", server_default=None)
    op.alter_column("auction_analysis_configs", "legal_risk_rules", server_default=None)


def downgrade() -> None:
    op.drop_column("auction_analysis_configs", "legal_risk_rules")
    op.drop_column("auction_analysis_configs", "exclusion_keywords")