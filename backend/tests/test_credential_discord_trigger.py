import unittest

from fastapi import HTTPException

from app.api.credentials import get_masked_value, validate_credential_config
from app.db.models import CredentialType


class DiscordTriggerCredentialTests(unittest.TestCase):
    def test_validate_requires_public_key(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            validate_credential_config(CredentialType.discord_trigger, {})
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("public_key", ctx.exception.detail)

    def test_validate_passes_with_public_key(self) -> None:
        validate_credential_config(
            CredentialType.discord_trigger,
            {"public_key": "a" * 64},
        )

    def test_masked_value_hides_public_key(self) -> None:
        public_key = "a" * 64
        masked = get_masked_value(CredentialType.discord_trigger, {"public_key": public_key})
        self.assertIsNotNone(masked)
        self.assertNotEqual(masked, public_key)


if __name__ == "__main__":
    unittest.main()
