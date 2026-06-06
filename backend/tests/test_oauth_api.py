import base64
import hashlib
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.api.oauth import (
    _issue_tokens,
    _validate_pkce_request,
    _verify_pkce,
    register_client,
)
from app.db.models import OAuthAccessToken
from app.services.oauth_tokens import hash_oauth_token, oauth_token_lookup_values


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class OAuthPKCETests(unittest.TestCase):
    def test_verify_pkce_accepts_s256_challenge(self) -> None:
        verifier = "correct-horse-battery-staple"
        self.assertTrue(_verify_pkce(_pkce_challenge(verifier), verifier))

    def test_public_client_requires_s256_pkce(self) -> None:
        client = SimpleNamespace(is_confidential=False)

        with self.assertRaises(HTTPException) as ctx:
            _validate_pkce_request(client, "", "")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["error"], "invalid_request")

    def test_confidential_client_may_skip_pkce(self) -> None:
        client = SimpleNamespace(is_confidential=True)

        _validate_pkce_request(client, "", "")

    def test_unsupported_pkce_method_is_rejected(self) -> None:
        client = SimpleNamespace(is_confidential=True)

        with self.assertRaises(HTTPException) as ctx:
            _validate_pkce_request(client, "challenge", "plain")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["error"], "invalid_request")


class OAuthTokenStorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_issue_tokens_stores_hashes_not_returned_token_values(self) -> None:
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        result = await _issue_tokens(db, "client-id", uuid.uuid4(), "mcp")

        token_record = db.add.call_args.args[0]
        self.assertIsInstance(token_record, OAuthAccessToken)
        self.assertEqual(token_record.access_token, hash_oauth_token(result["access_token"]))
        self.assertEqual(token_record.refresh_token, hash_oauth_token(result["refresh_token"]))
        self.assertNotEqual(token_record.access_token, result["access_token"])
        self.assertNotEqual(token_record.refresh_token, result["refresh_token"])

    def test_lookup_values_include_hash_and_legacy_plaintext_token(self) -> None:
        values = oauth_token_lookup_values("legacy-token")

        self.assertEqual(values[0], hash_oauth_token("legacy-token"))
        self.assertEqual(values[1], "legacy-token")


class OAuthRegistrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_register_rejects_unsupported_token_auth_method(self) -> None:
        request = SimpleNamespace(
            headers={},
            client=SimpleNamespace(host="127.0.0.1"),
            json=AsyncMock(
                return_value={
                    "client_name": "Bad Client",
                    "redirect_uris": ["https://example.com/callback"],
                    "token_endpoint_auth_method": "client_secret_jwt",
                }
            ),
        )
        db = AsyncMock()
        db.add = MagicMock()

        with patch("app.api.oauth.oauth_register_limiter.is_allowed", return_value=(True, None)):
            with self.assertRaises(HTTPException) as ctx:
                await register_client(request, db)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["error"], "invalid_client_metadata")
        db.add.assert_not_called()
