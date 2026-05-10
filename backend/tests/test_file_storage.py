"""Tests for generated file storage path safety."""

import os
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("ENCRYPTION_KEY", "0" * 64)

from app.services.file_storage import get_file_path, store_file


class FileStoragePathSafetyTests(unittest.IsolatedAsyncioTestCase):
    """File storage must keep attacker-controlled names inside the storage root."""

    async def test_store_file_rejects_posix_traversal_filename(self) -> None:
        """A multipart filename with ../ segments must not escape the storage root."""
        owner_id = uuid.uuid4()
        db = AsyncMock()
        db.add = MagicMock()

        with tempfile.TemporaryDirectory() as storage_dir:
            outside_file = Path(storage_dir).parent / "poc-owned-by-attacker.txt"
            if outside_file.exists():
                outside_file.unlink()

            with patch("app.services.file_storage._storage_root", return_value=Path(storage_dir)):
                with self.assertRaisesRegex(ValueError, "path components"):
                    await store_file(
                        db,
                        owner_id=owner_id,
                        file_bytes=b"PWNED",
                        filename="../../../poc-owned-by-attacker.txt",
                    )

            self.assertFalse(outside_file.exists())
            db.add.assert_not_called()
            db.flush.assert_not_awaited()

    async def test_store_file_rejects_windows_path_filename(self) -> None:
        """Backslash-separated path components must be rejected on Unix too."""
        db = AsyncMock()
        db.add = MagicMock()

        with tempfile.TemporaryDirectory() as storage_dir:
            with patch("app.services.file_storage._storage_root", return_value=Path(storage_dir)):
                with self.assertRaisesRegex(ValueError, "path components"):
                    await store_file(
                        db,
                        owner_id=uuid.uuid4(),
                        file_bytes=b"PWNED",
                        filename=r"..\\..\\poc-owned-by-attacker.txt",
                    )

            db.add.assert_not_called()
            db.flush.assert_not_awaited()

    async def test_store_file_writes_valid_filename_under_storage_root(self) -> None:
        """Safe filenames are still persisted below owner/file UUID directories."""
        db = AsyncMock()
        db.add = MagicMock()
        owner_id = uuid.uuid4()
        file_id = uuid.uuid4()

        with tempfile.TemporaryDirectory() as storage_dir:
            with (
                patch("app.services.file_storage._storage_root", return_value=Path(storage_dir)),
                patch("app.services.file_storage.uuid.uuid4", return_value=file_id),
            ):
                row = await store_file(
                    db,
                    owner_id=owner_id,
                    file_bytes=b"safe content",
                    filename="report.txt",
                )

            stored_path = Path(storage_dir) / str(owner_id) / str(file_id) / "report.txt"
            self.assertEqual(stored_path.read_bytes(), b"safe content")
            self.assertEqual(row.storage_path, f"{owner_id}/{file_id}/report.txt")
            db.add.assert_called_once_with(row)
            db.flush.assert_awaited_once()

    def test_get_file_path_rejects_escaped_legacy_storage_path(self) -> None:
        """Legacy DB paths containing traversal are not resolved outside storage root."""
        escaped = SimpleNamespace(storage_path="owner/file/../../../escaped.txt")

        with tempfile.TemporaryDirectory() as storage_dir:
            with patch("app.services.file_storage._storage_root", return_value=Path(storage_dir)):
                with self.assertRaisesRegex(ValueError, "escapes storage root"):
                    get_file_path(escaped)


if __name__ == "__main__":
    unittest.main()
