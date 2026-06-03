"""Tests for Settings validation (SECRET_KEY, ENCRYPTION_KEY)."""

import unittest

import pytest
from pydantic import ValidationError

from app.config import _ENCRYPTION_KEY_PLACEHOLDER, _SECRET_KEY_PLACEHOLDER, Settings


class TestSecretKeyValidation(unittest.TestCase):
    """Verify SECRET_KEY field_validator rejects missing, placeholder, and short values."""

    def _make_settings(self, secret_key: str) -> Settings:
        """Build Settings with the given secret_key, isolating env vars."""
        return Settings(
            _env_file=None,
            secret_key=secret_key,
            encryption_key="a" * 64,
        )

    def test_missing_secret_key_rejected(self):
        """Empty string should raise ValidationError."""
        with pytest.raises(ValidationError, match="SECRET_KEY"):
            self._make_settings("")

    def test_placeholder_secret_key_rejected(self):
        """The old default placeholder should raise ValidationError."""
        with pytest.raises(ValidationError, match="SECRET_KEY"):
            self._make_settings(_SECRET_KEY_PLACEHOLDER)

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


class TestEncryptionKeyValidation(unittest.TestCase):
    """Verify ENCRYPTION_KEY field_validator rejects missing and placeholder values."""

    def _make_settings(self, encryption_key: str) -> Settings:
        """Build Settings with the given encryption_key, isolating env vars."""
        return Settings(
            _env_file=None,
            secret_key="a" * 32,
            encryption_key=encryption_key,
        )

    def test_missing_encryption_key_rejected(self):
        """Empty string should raise ValidationError."""
        with pytest.raises(ValidationError, match="ENCRYPTION_KEY"):
            self._make_settings("")

    def test_placeholder_encryption_key_rejected(self):
        """The known placeholder value should raise ValidationError."""
        with pytest.raises(ValidationError, match="ENCRYPTION_KEY"):
            self._make_settings(_ENCRYPTION_KEY_PLACEHOLDER)

    def test_valid_encryption_key_accepted(self):
        """A proper hex key should pass."""
        import secrets

        key = secrets.token_hex(32)
        s = self._make_settings(key)
        assert s.encryption_key == key
