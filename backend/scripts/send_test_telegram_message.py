from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.config import get_settings
from app.schemas.lot_decision_report import (
    ActionRecommendation,
    DecisionLevel,
    LotDecisionReason,
    LotDecisionReport,
    LotDecisionRisk,
    LotEconomicsDecision,
)
from app.services.lot_decision_report import render_telegram_lot_message
from app.services.telegram_sender import TelegramBotApiSender


def build_test_report() -> LotDecisionReport:
    generated_at = datetime.now(UTC)
    deadline = generated_at + timedelta(hours=36)
    return LotDecisionReport(
        source="tbankrot",
        auction_id="test-auction",
        lot_id="test-lot",
        record_id=0,
        title="Тестовое уведомление: AUDI A3, 2012 г.",
        source_title="TBankrot",
        region="Санкт-Петербург",
        current_price="405 000,00 ₽",
        deadline=deadline.strftime("%d.%m.%Y %H:%M"),
        rating_score=92,
        rating_level="high",
        economics=LotEconomicsDecision(
            current_price=Decimal("405000"),
            market_value=Decimal("650000"),
            expected_costs=Decimal("45000"),
            target_roi=Decimal("0.25"),
            max_buy_price=Decimal("484000"),
            estimated_profit=Decimal("200000"),
            confidence="high",
        ),
        decision_level=DecisionLevel.BID_CANDIDATE,
        recommendation=ActionRecommendation.CALCULATE_MAX_BID,
        reasons=(
            LotDecisionReason(code="test.price", message="Цена ниже целевой оценки", source="test"),
            LotDecisionReason(code="test.deadline", message="До окончания заявок меньше 48 часов", source="test"),
            LotDecisionReason(code="test.documents", message="Есть документы и порядок осмотра", source="test"),
        ),
        risks=(
            LotDecisionRisk(code="test.pledge", message="Проверить залог и ограничения перед заявкой", level="medium"),
        ),
        next_actions=(),
        generated_at=generated_at,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Send a rendered test LotDecisionReport to Telegram.")
    parser.add_argument("--link", default="https://example.test/lots/test-lot", help="Link rendered in the message.")
    parser.add_argument("--print-only", action="store_true", help="Render the message without sending it.")
    args = parser.parse_args()

    settings = get_settings()
    message = render_telegram_lot_message(build_test_report(), link=args.link)
    print(message.text)
    print({"message_length": message.message_length})

    if args.print_only:
        return
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        raise SystemExit("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")

    await TelegramBotApiSender(timeout_seconds=settings.telegram_sender_request_timeout_seconds).send_message(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        text=message.text,
        parse_mode=message.parse_mode,
    )
    print("sent")


if __name__ == "__main__":
    asyncio.run(main())
