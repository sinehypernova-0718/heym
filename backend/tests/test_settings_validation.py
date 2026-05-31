"""Tests for Settings validation (SECRET_KEY, ENCRYPTION_KEY)."""

import os
import unittest

import pytest
from pydantic import ValidationError

from app.config import Settings


class TestSecretKeyValidation(unittest.TestCase):
    """Verify SECRET_KEY field_validator rejects missing, placeholder, and short values."""

    def _make_settings(self, secret_key: str) -> Settings:
        """Build Settings with the given SECRET_KEY, isolating env vars."""
        env = {
            "ENCRYPTION_KEY": "a" * 64,  # valid encryption key
            "SECRET_KEY": secret_key,
        }
        return Settings(**env)

    def test_missing_secret_key_rejected(self):
        """Empty string should raise ValidationError."""
        with pytest.raises(ValidationError, match="SECRET_KEY"):
            self._make_settings("")

    def test_placeholder_secret_key_rejected(self):
        """The old default placeholder should raise ValidationError."""
        placeholder = "your-super-secret-key-change-in-production-min-32-chars"
        with pytest.raises(ValidationError, match="SECRET_KEY"):
            self._make_settings(placeholder)

    def test_short_secret_key_rejected(self):
        """Keys shorter than 32 characters should raise ValidationError."""
        with pytest.raises(ValidationError, match="at least 32 characters"):
            self._make_settings("short_key")

    def test_valid_secret_key_accepted(self):
        """A sufficiently long, non-placeholder key should pass."""
        key = "a" * 32
        s = self._make_settings(key)
        assert s.secret_key == key

    def test_long_random_secret_key_accepted(self):
        """A typical generated token_urlsafe(32) key should pass."""
        import secrets

        key = secrets.token_urlsafe(32)
        s = self._make_settings(key)
        assert s.secret_key == key
