from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app.services.telegram_webhook_registration import TelegramWebhookRegistrar


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class TelegramWebhookRegistrarTests(unittest.IsolatedAsyncioTestCase):
    async def test_ensure_webhook_skips_when_disabled_or_incomplete(self) -> None:
        registrar = TelegramWebhookRegistrar()

        disabled = await registrar.ensure_webhook(
            bot_token="token",
            webhook_url="https://app.test/api/v1/telegram/webhook",
            webhook_secret="secret",
            enabled=False,
        )
        missing_url = await registrar.ensure_webhook(
            bot_token="token",
            webhook_url=None,
            webhook_secret="secret",
            enabled=True,
        )

        self.assertFalse(disabled.registered)
        self.assertEqual(disabled.reason, "disabled")
        self.assertFalse(missing_url.registered)
        self.assertEqual(missing_url.reason, "missing_webhook_url")

    async def test_ensure_webhook_calls_telegram_set_webhook(self) -> None:
        registrar = TelegramWebhookRegistrar()

        with patch(
            "app.services.telegram_webhook_registration.urlopen",
            return_value=FakeResponse({"ok": True}),
        ) as urlopen_mock:
            result = await registrar.ensure_webhook(
                bot_token="token",
                webhook_url="https://app.test/api/v1/telegram/webhook",
                webhook_secret="secret",
                enabled=True,
            )

        self.assertTrue(result.registered)
        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.telegram.org/bottoken/setWebhook")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["url"], "https://app.test/api/v1/telegram/webhook")
        self.assertEqual(payload["secret_token"], "secret")
        self.assertEqual(payload["allowed_updates"], ["message"])


if __name__ == "__main__":
    unittest.main()
