import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException, status

from app.services.upload_limits import read_upload_file_limited


class UploadLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_upload_file_limited_reads_only_limit_plus_one_bytes(self) -> None:
        upload = SimpleNamespace(read=AsyncMock(return_value=b"abc"))

        payload = await read_upload_file_limited(upload, max_bytes=3)

        self.assertEqual(payload, b"abc")
        upload.read.assert_awaited_once_with(4)

    async def test_read_upload_file_limited_rejects_oversized_upload(self) -> None:
        upload = SimpleNamespace(read=AsyncMock(return_value=b"abcd"))

        with self.assertRaises(HTTPException) as ctx:
            await read_upload_file_limited(upload, max_bytes=3)

        self.assertEqual(ctx.exception.status_code, status.HTTP_413_CONTENT_TOO_LARGE)
        self.assertEqual(ctx.exception.detail, "File size exceeds limit (3 bytes)")
