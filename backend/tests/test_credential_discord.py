import unittest

from fastapi import HTTPException

from app.api.credentials import get_masked_value, validate_credential_config
from app.db.models import CredentialType


class DiscordCredentialTests(unittest.TestCase):
    def test_validate_requires_webhook_url(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            validate_credential_config(CredentialType.discord, {})
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("webhook_url", ctx.exception.detail)

    def test_validate_passes_with_webhook_url(self) -> None:
        validate_credential_config(
            CredentialType.discord,
            {"webhook_url": "https://discord.com/api/webhooks/123/abc"},
        )

    def test_masked_value_hides_webhook_url(self) -> None:
        webhook_url = "https://discord.com/api/webhooks/1234567890/abcdefg"
        masked = get_masked_value(CredentialType.discord, {"webhook_url": webhook_url})
        self.assertIsNotNone(masked)
        self.assertNotEqual(masked, webhook_url)
