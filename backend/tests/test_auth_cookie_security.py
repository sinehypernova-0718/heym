"""Tests for auth cookie Secure flag environment decisions."""

import unittest

from app.api.auth import _should_use_secure_auth_cookies


class AuthCookieSecurityTests(unittest.TestCase):
    def test_local_frontend_url_allows_insecure_dev_cookie(self) -> None:
        self.assertFalse(
            _should_use_secure_auth_cookies("http://localhost:4017", ["http://localhost:4017"])
        )

    def test_https_frontend_url_uses_secure_cookie_even_with_local_cors_first(self) -> None:
        self.assertTrue(
            _should_use_secure_auth_cookies(
                "https://heym.example.com",
                ["http://localhost:4017", "https://heym.example.com"],
            )
        )

    def test_local_frontend_url_uses_secure_cookie_with_https_cors_origin(self) -> None:
        self.assertTrue(
            _should_use_secure_auth_cookies(
                "http://localhost:4017",
                ["https://heym.example.com"],
            )
        )

    def test_blank_frontend_uses_secure_cookie_when_any_cors_origin_is_not_local_http(self) -> None:
        self.assertTrue(
            _should_use_secure_auth_cookies(
                "",
                ["http://localhost:4017", "https://heym.example.com"],
            )
        )

    def test_blank_frontend_allows_insecure_cookie_for_local_http_cors_only(self) -> None:
        self.assertFalse(
            _should_use_secure_auth_cookies(
                "",
                ["http://localhost:4017", "http://127.0.0.1:4017"],
            )
        )

    def test_blank_origin_configuration_fails_secure(self) -> None:
        self.assertTrue(_should_use_secure_auth_cookies("", []))
