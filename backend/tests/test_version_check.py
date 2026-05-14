import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from app.services.version_check import (
    GithubRelease,
    clear_version_status_cache,
    get_version_status,
    is_version_behind,
)


class VersionCompareTests(unittest.TestCase):
    def test_detects_older_current_version(self) -> None:
        self.assertTrue(is_version_behind("0.0.22", "0.0.25"))

    def test_accepts_v_prefixed_latest_version(self) -> None:
        self.assertTrue(is_version_behind("0.0.22", "v0.0.25"))

    def test_does_not_mark_same_version_as_behind(self) -> None:
        self.assertFalse(is_version_behind("0.0.25", "v0.0.25"))

    def test_ignores_unparseable_versions(self) -> None:
        self.assertFalse(is_version_behind("local-dev", "v0.0.25"))


class VersionStatusTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        clear_version_status_cache()

    def tearDown(self) -> None:
        clear_version_status_cache()

    async def test_get_version_status_builds_github_compare_url(self) -> None:
        release = GithubRelease(
            tag_name="v0.0.25",
            release_url="https://github.com/heymrun/heym/releases/tag/v0.0.25",
            published_at="2026-05-14T00:00:00Z",
        )

        with patch(
            "app.services.version_check._fetch_latest_release",
            new=AsyncMock(return_value=release),
        ):
            status = await get_version_status("0.0.22", force_refresh=True)

        self.assertEqual(status.current_version, "0.0.22")
        self.assertEqual(status.latest_version, "0.0.25")
        self.assertTrue(status.update_available)
        self.assertEqual(status.compare_label, "0.0.22..0.0.25")
        self.assertEqual(
            status.compare_url,
            "https://github.com/heymrun/heym/compare/v0.0.22...v0.0.25",
        )
        self.assertEqual(status.release_url, release.release_url)
        self.assertIsInstance(status.checked_at, datetime)
        self.assertEqual(status.checked_at.tzinfo, UTC)
        self.assertIsNone(status.error)

    async def test_get_version_status_returns_current_version_when_github_fails(self) -> None:
        with patch(
            "app.services.version_check._fetch_latest_release",
            new=AsyncMock(side_effect=RuntimeError("GitHub unavailable")),
        ):
            status = await get_version_status("0.0.22", force_refresh=True)

        self.assertEqual(status.current_version, "0.0.22")
        self.assertIsNone(status.latest_version)
        self.assertFalse(status.update_available)
        self.assertIsNone(status.compare_url)
        self.assertIn("GitHub unavailable", status.error or "")
