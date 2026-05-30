# Drive Node — `convertFile` Operation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `convertFile` operation to the existing Drive node that converts a stored file to a new format using pandoc (for documents) or Pillow (for images), storing the result as a new Drive file.

**Architecture:** A new `elif operation == "convertFile":` branch is added inside the existing Drive node handler in `workflow_executor.py`, reusing the existing `driveFileId` field for the source file. Three module-level helper functions (`_detect_pandoc_format`, `_convert_image`, `_extract_pdf_text`) are added just before the `WorkflowExecutor` class. The frontend adds one new dropdown field (`driveConvertTargetFormat`) and one new option to the operation selector.

**Tech Stack:** Python `pypandoc` (pandoc wrapper), `Pillow` (image conversion), `pypdf` (already installed, PDF text extraction), pandoc binary + weasyprint (Dockerfile), Vue 3 + TypeScript (frontend dropdown).

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/Dockerfile` | Modify (line 5–10) | Add pandoc + weasyprint to apt-get install |
| `backend/pyproject.toml` | Modify (line 26–28) | Add pypandoc + Pillow dependencies |
| `backend/app/services/workflow_executor.py` | Modify (line 1367, 8998) | Add 3 helper functions + `convertFile` handler branch |
| `backend/tests/test_drive_node.py` | Modify (append) | Add helper unit tests + 7 integration tests |
| `frontend/src/components/Panels/PropertiesPanel.vue` | Modify (line 3147, 9816-area, 10066-area) | Add operation option, target format dropdown, output hint |
| `backend/app/services/workflow_dsl_prompt.py` | Modify (line 2822–2915) | Add convertFile to enum, fields, table, example |
| `frontend/src/docs/content/nodes/drive-node.md` | Modify | Add convertFile to params, operations table, example, output |
| `frontend/src/docs/content/reference/drive.md` | Modify (line 56–63) | Add conversion mention |

---

## Task 1: Add dependencies to Dockerfile and pyproject.toml

**Files:**
- Modify: `backend/Dockerfile:5-10`
- Modify: `backend/pyproject.toml:26-28`

- [ ] **Step 1: Edit Dockerfile — add pandoc and weasyprint to apt-get install**

Current block (lines 5–10):
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tzdata \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*
```

Replace with:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tzdata \
    nodejs \
    npm \
    pandoc \
    weasyprint \
    && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 2: Edit pyproject.toml — add pypandoc and Pillow**

After line 28 (`"python-docx>=1.0.0",`), add two lines:
```toml
    "pypandoc>=1.13",
    "Pillow>=11.0",
```

Result for lines 26–31:
```toml
    "pypdf>=6.10.2",
    "reportlab>=4.0.0",
    "python-docx>=1.0.0",
    "pypandoc>=1.13",
    "Pillow>=11.0",
    "aio-pika>=9.6.2",
```

- [ ] **Step 3: Sync the lockfile**

```bash
cd /Users/cerenakgun/Documents/Projects/heym_workspace/heym/backend
uv sync
```

Expected: resolves and installs `pypandoc` and `Pillow` without errors.

- [ ] **Step 4: Commit**

```bash
git add backend/Dockerfile backend/pyproject.toml backend/uv.lock
git commit -m "feat: add pandoc, weasyprint, pypandoc, Pillow for Drive file conversion"
```

---

## Task 2: Add helper functions with TDD

**Files:**
- Modify: `backend/tests/test_drive_node.py` (append new test class)
- Modify: `backend/app/services/workflow_executor.py` (insert at line 1367)

The three helpers are module-level functions added at the end of the utility section, right before `class WorkflowExecutor:` (currently line 1369).

### Step 2a: Write failing tests for helpers

- [ ] **Step 1: Append helper tests to test_drive_node.py**

Add this entire class at the bottom of `backend/tests/test_drive_node.py` (before `if __name__ == "__main__":`):

```python
# ---------------------------------------------------------------------------
# Task — Drive convertFile helper functions
# ---------------------------------------------------------------------------


class DriveConvertHelpersTests(unittest.TestCase):
    """Unit tests for the three module-level helpers used by convertFile."""

    # --- _detect_pandoc_format ---

    def test_detect_markdown_by_mime(self) -> None:
        from app.services.workflow_executor import _detect_pandoc_format

        self.assertEqual(_detect_pandoc_format("text/markdown", "doc.md"), "markdown")

    def test_detect_html_by_mime(self) -> None:
        from app.services.workflow_executor import _detect_pandoc_format

        self.assertEqual(_detect_pandoc_format("text/html", "page.html"), "html")

    def test_detect_docx_by_mime(self) -> None:
        from app.services.workflow_executor import _detect_pandoc_format

        self.assertEqual(
            _detect_pandoc_format(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "doc.docx",
            ),
            "docx",
        )

    def test_detect_plain_by_mime(self) -> None:
        from app.services.workflow_executor import _detect_pandoc_format

        self.assertEqual(_detect_pandoc_format("text/plain", "notes.txt"), "plain")

    def test_detect_csv_by_mime(self) -> None:
        from app.services.workflow_executor import _detect_pandoc_format

        self.assertEqual(_detect_pandoc_format("text/csv", "data.csv"), "csv")

    def test_detect_md_by_extension_fallback(self) -> None:
        from app.services.workflow_executor import _detect_pandoc_format

        self.assertEqual(_detect_pandoc_format("application/octet-stream", "readme.md"), "markdown")

    def test_detect_unsupported_returns_none(self) -> None:
        from app.services.workflow_executor import _detect_pandoc_format

        self.assertIsNone(_detect_pandoc_format("application/zip", "archive.zip"))

    # --- _extract_pdf_text ---

    def test_extract_pdf_text_returns_string(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.services.workflow_executor import _extract_pdf_text

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Hello from PDF"
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        with patch("pypdf.PdfReader", return_value=mock_reader):
            result = _extract_pdf_text(b"fake-pdf-bytes")

        self.assertEqual(result, "Hello from PDF")

    def test_extract_pdf_text_joins_pages(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.services.workflow_executor import _extract_pdf_text

        pages = [MagicMock(), MagicMock()]
        pages[0].extract_text.return_value = "Page 1"
        pages[1].extract_text.return_value = "Page 2"
        mock_reader = MagicMock()
        mock_reader.pages = pages

        with patch("pypdf.PdfReader", return_value=mock_reader):
            result = _extract_pdf_text(b"fake-pdf-bytes")

        self.assertEqual(result, "Page 1\n\nPage 2")

    # --- _convert_image ---

    def test_convert_image_png_to_jpg(self) -> None:
        import io
        from unittest.mock import MagicMock, patch

        from app.services.workflow_executor import _convert_image

        fake_output = b"fake-jpeg-bytes"

        mock_img = MagicMock()
        mock_img.mode = "RGB"

        def fake_save(buf, format):
            buf.write(fake_output)

        mock_img.save.side_effect = fake_save
        mock_img.convert.return_value = mock_img

        with patch("PIL.Image.open", return_value=mock_img):
            out_bytes, out_mime = _convert_image(b"png-bytes", "jpg")

        self.assertEqual(out_bytes, fake_output)
        self.assertEqual(out_mime, "image/jpeg")
        mock_img.save.assert_called_once()
        call_kwargs = mock_img.save.call_args
        self.assertEqual(call_kwargs[1]["format"], "JPEG")

    def test_convert_image_unsupported_format_raises(self) -> None:
        from app.services.workflow_executor import _convert_image

        with self.assertRaises(ValueError) as ctx:
            _convert_image(b"bytes", "docx")
        self.assertIn("unsupported image output format", str(ctx.exception))

    def test_convert_image_rgba_to_jpg_converts_to_rgb(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.services.workflow_executor import _convert_image

        mock_img = MagicMock()
        mock_img.mode = "RGBA"
        rgb_img = MagicMock()
        rgb_img.mode = "RGB"
        mock_img.convert.return_value = rgb_img

        def fake_save(buf, format):
            buf.write(b"data")

        rgb_img.save.side_effect = fake_save

        with patch("PIL.Image.open", return_value=mock_img):
            _convert_image(b"png-rgba-bytes", "jpg")

        mock_img.convert.assert_called_once_with("RGB")
        rgb_img.save.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/cerenakgun/Documents/Projects/heym_workspace/heym/backend
uv run pytest tests/test_drive_node.py::DriveConvertHelpersTests -v
```

Expected: FAIL with `ImportError: cannot import name '_detect_pandoc_format' from 'app.services.workflow_executor'`

### Step 2b: Implement the helpers

- [ ] **Step 3: Insert helper functions into workflow_executor.py at line 1367**

Insert the following block between the `_restore_sub_workflow_executions` function and `class WorkflowExecutor:` (at line 1368, which is a blank line before `class WorkflowExecutor:`):

```python
def _detect_pandoc_format(mime_type: str, filename: str) -> str | None:
    """Return pandoc input format string for the given MIME type / filename, or None if unsupported."""
    _mime_map: dict[str, str] = {
        "text/markdown": "markdown",
        "text/html": "html",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "text/plain": "plain",
        "text/csv": "csv",
    }
    if mime_type in _mime_map:
        return _mime_map[mime_type]
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    _ext_map: dict[str, str] = {
        "md": "markdown",
        "markdown": "markdown",
        "html": "html",
        "htm": "html",
        "docx": "docx",
        "txt": "plain",
        "csv": "csv",
    }
    return _ext_map.get(ext)


def _extract_pdf_text(src_bytes: bytes) -> str:
    """Extract plain text from a PDF via pypdf."""
    import io

    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(src_bytes))
    parts = [page.extract_text() for page in reader.pages if page.extract_text()]
    return "\n\n".join(parts)


def _convert_image(src_bytes: bytes, target_format: str) -> tuple[bytes, str]:
    """Convert image bytes to target_format. Returns (output_bytes, output_mime_type)."""
    import io

    from PIL import Image

    _fmt_map: dict[str, tuple[str, str]] = {
        "jpg": ("JPEG", "image/jpeg"),
        "jpeg": ("JPEG", "image/jpeg"),
        "png": ("PNG", "image/png"),
        "bmp": ("BMP", "image/bmp"),
        "webp": ("WEBP", "image/webp"),
    }
    if target_format not in _fmt_map:
        raise ValueError(f"Drive Node: unsupported image output format '{target_format}'")
    pil_format, mime_type = _fmt_map[target_format]
    img = Image.open(io.BytesIO(src_bytes))
    if pil_format == "JPEG" and img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format=pil_format)
    return buf.getvalue(), mime_type

```

- [ ] **Step 4: Run helper tests to verify they pass**

```bash
cd /Users/cerenakgun/Documents/Projects/heym_workspace/heym/backend
uv run pytest tests/test_drive_node.py::DriveConvertHelpersTests -v
```

Expected: all 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_drive_node.py backend/app/services/workflow_executor.py
git commit -m "feat: add _detect_pandoc_format, _extract_pdf_text, _convert_image helpers"
```

---

## Task 3: Add `convertFile` executor handler with integration tests

**Files:**
- Modify: `backend/tests/test_drive_node.py` (append new class)
- Modify: `backend/app/services/workflow_executor.py` (insert before line 8998)

### Step 3a: Write failing integration tests

- [ ] **Step 1: Append integration test class to test_drive_node.py**

Add this class at the bottom of `backend/tests/test_drive_node.py` (before `if __name__ == "__main__":`):

```python
# ---------------------------------------------------------------------------
# Task — Drive convertFile operation (executor integration)
# ---------------------------------------------------------------------------


def _make_convert_db_mock(file_row: object) -> MagicMock:
    """DB mock for convertFile: first query returns the source file, then adds two objects."""
    fake_db = MagicMock()
    fake_db.__enter__ = MagicMock(return_value=fake_db)
    fake_db.__exit__ = MagicMock(return_value=False)
    fake_db.query.return_value.filter.return_value.first.return_value = file_row
    fake_db.flush = MagicMock()
    fake_db.commit = MagicMock()
    added: list = []
    fake_db.add.side_effect = lambda obj: added.append(obj)
    fake_db._added = added
    return fake_db


class DriveNodeConvertFileTests(unittest.TestCase):
    """Drive node convertFile operation."""

    def _run_convert_workflow(
        self,
        drive_data: dict,
        owner_id: uuid.UUID,
        db_mock: MagicMock,
        src_bytes: bytes,
        converted_bytes: bytes,
        converted_mime: str,
        is_image: bool = False,
    ) -> dict:
        from app.services.workflow_executor import WorkflowExecutor

        nodes, edges = _make_workflow(drive_data)
        executor = WorkflowExecutor(nodes=nodes, edges=edges)
        executor.trace_user_id = owner_id

        with (
            patch("app.db.session.SessionLocal", return_value=db_mock),
            patch("app.services.file_storage._storage_root") as mock_root,
            patch(
                "app.services.file_storage.build_download_url",
                return_value="/api/files/dl/convtoken",
            ),
            patch("secrets.token_urlsafe", return_value="convtoken"),
        ):
            # Single mock path handles both source read and dest write.
            # exists()=True triggers the read path; read_bytes returns src content.
            # write_bytes/parent.mkdir are no-ops for the output write path.
            storage_path = MagicMock()
            storage_path.exists.return_value = True
            storage_path.read_bytes.return_value = src_bytes

            mock_root.return_value.__truediv__ = MagicMock(return_value=storage_path)

            if is_image:
                with patch(
                    "app.services.workflow_executor._convert_image",
                    return_value=(converted_bytes, converted_mime),
                ):
                    result = executor.execute(
                        workflow_id=uuid.uuid4(),
                        initial_inputs={"headers": {}, "query": {}, "body": {"text": "hi"}},
                    )
            else:
                with (
                    patch(
                        "app.services.workflow_executor._extract_pdf_text",
                        return_value="extracted text",
                    ),
                    patch("pypandoc.convert_file") as mock_pandoc,
                ):
                    def write_output(src, fmt, outputfile, format, extra_args=None):
                        with open(outputfile, "wb") as fh:
                            fh.write(converted_bytes)

                    mock_pandoc.side_effect = write_output
                    result = executor.execute(
                        workflow_id=uuid.uuid4(),
                        initial_inputs={"headers": {}, "query": {}, "body": {"text": "hi"}},
                    )

        nr = next((r for r in result.node_results if r["node_type"] == "drive"), None)
        if nr is None:
            raise AssertionError(
                f"Drive node result not found. Errors: "
                f"{[r for r in result.node_results if r.get('status') == 'error']}"
            )
        return nr

    def test_convert_md_to_html_success(self) -> None:
        owner_id = uuid.uuid4()
        file_id = uuid.uuid4()
        file_row = SimpleNamespace(
            id=file_id,
            owner_id=owner_id,
            filename="readme.md",
            mime_type="text/markdown",
            size_bytes=100,
            storage_path=f"{owner_id}/{file_id}/readme.md",
        )
        db = _make_convert_db_mock(file_row)

        nr = self._run_convert_workflow(
            {
                "label": "convert",
                "driveOperation": "convertFile",
                "driveFileId": str(file_id),
                "driveConvertTargetFormat": "html",
            },
            owner_id,
            db,
            src_bytes=b"# Hello",
            converted_bytes=b"<h1>Hello</h1>",
            converted_mime="text/html",
        )

        self.assertEqual(nr["status"], "success")
        self.assertEqual(nr["output"]["operation"], "convertFile")
        self.assertEqual(nr["output"]["filename"], "readme.html")
        self.assertEqual(nr["output"]["mime_type"], "text/html")
        self.assertIn("id", nr["output"])
        self.assertIn("download_url", nr["output"])

    def test_convert_pdf_to_txt_success(self) -> None:
        owner_id = uuid.uuid4()
        file_id = uuid.uuid4()
        file_row = SimpleNamespace(
            id=file_id,
            owner_id=owner_id,
            filename="report.pdf",
            mime_type="application/pdf",
            size_bytes=500,
            storage_path=f"{owner_id}/{file_id}/report.pdf",
        )
        db = _make_convert_db_mock(file_row)

        nr = self._run_convert_workflow(
            {
                "label": "convert",
                "driveOperation": "convertFile",
                "driveFileId": str(file_id),
                "driveConvertTargetFormat": "txt",
            },
            owner_id,
            db,
            src_bytes=b"%PDF-fake",
            converted_bytes=b"extracted text",
            converted_mime="text/plain",
        )

        self.assertEqual(nr["status"], "success")
        self.assertEqual(nr["output"]["filename"], "report.txt")
        self.assertEqual(nr["output"]["mime_type"], "text/plain")

    def test_convert_image_png_to_jpg_success(self) -> None:
        owner_id = uuid.uuid4()
        file_id = uuid.uuid4()
        file_row = SimpleNamespace(
            id=file_id,
            owner_id=owner_id,
            filename="photo.png",
            mime_type="image/png",
            size_bytes=200,
            storage_path=f"{owner_id}/{file_id}/photo.png",
        )
        db = _make_convert_db_mock(file_row)

        nr = self._run_convert_workflow(
            {
                "label": "convert",
                "driveOperation": "convertFile",
                "driveFileId": str(file_id),
                "driveConvertTargetFormat": "jpg",
            },
            owner_id,
            db,
            src_bytes=b"fake-png",
            converted_bytes=b"fake-jpeg",
            converted_mime="image/jpeg",
            is_image=True,
        )

        self.assertEqual(nr["status"], "success")
        self.assertEqual(nr["output"]["filename"], "photo.jpg")
        self.assertEqual(nr["output"]["mime_type"], "image/jpeg")

    def test_convert_unsupported_input_format_raises(self) -> None:
        owner_id = uuid.uuid4()
        file_id = uuid.uuid4()
        file_row = SimpleNamespace(
            id=file_id,
            owner_id=owner_id,
            filename="archive.zip",
            mime_type="application/zip",
            size_bytes=1000,
            storage_path=f"{owner_id}/{file_id}/archive.zip",
        )
        db = _make_convert_db_mock(file_row)

        from app.services.workflow_executor import WorkflowExecutor

        nodes, edges = _make_workflow(
            {
                "label": "convert",
                "driveOperation": "convertFile",
                "driveFileId": str(file_id),
                "driveConvertTargetFormat": "txt",
            }
        )
        executor = WorkflowExecutor(nodes=nodes, edges=edges)
        executor.trace_user_id = owner_id

        src_path = MagicMock()
        src_path.exists.return_value = True
        src_path.read_bytes.return_value = b"zip-data"

        with (
            patch("app.db.session.SessionLocal", return_value=db),
            patch("app.services.file_storage._storage_root") as mock_root,
            patch("app.services.file_storage.build_download_url", return_value=""),
        ):
            mock_root.return_value.__truediv__ = MagicMock(return_value=src_path)
            result = executor.execute(
                workflow_id=uuid.uuid4(),
                initial_inputs={"headers": {}, "query": {}, "body": {"text": "hi"}},
            )

        nr = next((r for r in result.node_results if r["node_type"] == "drive"), None)
        self.assertIsNotNone(nr)
        self.assertEqual(nr["status"], "error")
        self.assertIn("does not support input format", nr["error"])

    def test_convert_image_to_doc_format_raises(self) -> None:
        owner_id = uuid.uuid4()
        file_id = uuid.uuid4()
        file_row = SimpleNamespace(
            id=file_id,
            owner_id=owner_id,
            filename="photo.png",
            mime_type="image/png",
            size_bytes=200,
            storage_path=f"{owner_id}/{file_id}/photo.png",
        )
        db = _make_convert_db_mock(file_row)

        from app.services.workflow_executor import WorkflowExecutor

        nodes, edges = _make_workflow(
            {
                "label": "convert",
                "driveOperation": "convertFile",
                "driveFileId": str(file_id),
                "driveConvertTargetFormat": "docx",
            }
        )
        executor = WorkflowExecutor(nodes=nodes, edges=edges)
        executor.trace_user_id = owner_id

        src_path = MagicMock()
        src_path.exists.return_value = True
        src_path.read_bytes.return_value = b"png-data"

        with (
            patch("app.db.session.SessionLocal", return_value=db),
            patch("app.services.file_storage._storage_root") as mock_root,
            patch("app.services.file_storage.build_download_url", return_value=""),
        ):
            mock_root.return_value.__truediv__ = MagicMock(return_value=src_path)
            result = executor.execute(
                workflow_id=uuid.uuid4(),
                initial_inputs={"headers": {}, "query": {}, "body": {"text": "hi"}},
            )

        nr = next((r for r in result.node_results if r["node_type"] == "drive"), None)
        self.assertIsNotNone(nr)
        self.assertEqual(nr["status"], "error")
        self.assertIn("cannot convert image", nr["error"])

    def test_convert_missing_file_id_raises(self) -> None:
        owner_id = uuid.uuid4()
        db = _make_convert_db_mock(None)

        from app.services.workflow_executor import WorkflowExecutor

        nodes, edges = _make_workflow(
            {
                "label": "convert",
                "driveOperation": "convertFile",
                "driveFileId": "",
                "driveConvertTargetFormat": "html",
            }
        )
        executor = WorkflowExecutor(nodes=nodes, edges=edges)
        executor.trace_user_id = owner_id

        with (
            patch("app.db.session.SessionLocal", return_value=db),
            patch("app.services.file_storage._storage_root"),
            patch("app.services.file_storage.build_download_url", return_value=""),
        ):
            result = executor.execute(
                workflow_id=uuid.uuid4(),
                initial_inputs={"headers": {}, "query": {}, "body": {"text": "hi"}},
            )

        nr = next((r for r in result.node_results if r["node_type"] == "drive"), None)
        self.assertIsNotNone(nr)
        self.assertEqual(nr["status"], "error")
        self.assertIn("fileId is required", nr["error"])

    def test_convert_output_is_new_file(self) -> None:
        """Original file_id must differ from converted file id in output."""
        owner_id = uuid.uuid4()
        file_id = uuid.uuid4()
        file_row = SimpleNamespace(
            id=file_id,
            owner_id=owner_id,
            filename="doc.md",
            mime_type="text/markdown",
            size_bytes=50,
            storage_path=f"{owner_id}/{file_id}/doc.md",
        )
        db = _make_convert_db_mock(file_row)

        nr = self._run_convert_workflow(
            {
                "label": "convert",
                "driveOperation": "convertFile",
                "driveFileId": str(file_id),
                "driveConvertTargetFormat": "txt",
            },
            owner_id,
            db,
            src_bytes=b"# Hello",
            converted_bytes=b"Hello",
            converted_mime="text/plain",
        )

        self.assertEqual(nr["status"], "success")
        # Output id is a new UUID, not the source
        self.assertNotEqual(nr["output"]["id"], str(file_id))
        # Two objects added to DB: GeneratedFile + FileAccessToken
        self.assertEqual(len(db._added), 2)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/cerenakgun/Documents/Projects/heym_workspace/heym/backend
uv run pytest tests/test_drive_node.py::DriveNodeConvertFileTests -v
```

Expected: FAIL — tests that reach the executor error with `"Drive Node: unknown operation 'convertFile'"`.

### Step 3b: Implement the handler

- [ ] **Step 3: Insert `convertFile` branch before line 8998 in workflow_executor.py**

Find this block (currently lines 8997–8999):
```python
                                output["file_base64"] = _base64.b64encode(file_bytes).decode()

                        elif operation != "getAll":
                            raise ValueError(f"Drive Node: unknown operation '{operation}'")
```

Replace the `elif operation != "getAll":` part with:
```python
                                output["file_base64"] = _base64.b64encode(file_bytes).decode()

                        elif operation == "convertFile":
                            import tempfile as _tempfile

                            import pypandoc as _pypandoc

                            from app.config import settings as _settings

                            target_format = node_data.get("driveConvertTargetFormat", "")
                            if not target_format:
                                raise ValueError(
                                    "Drive Node: targetFormat is required for convertFile"
                                )

                            _IMAGE_FORMATS = {"jpg", "jpeg", "png", "bmp", "webp"}
                            _DOC_FORMATS = {"pdf", "docx", "html", "md", "txt"}

                            src_mime = file_row.mime_type or ""
                            src_filename = file_row.filename or ""
                            _IMAGE_MIMES = {
                                "image/jpeg",
                                "image/jpg",
                                "image/png",
                                "image/bmp",
                                "image/webp",
                            }
                            is_image_input = src_mime in _IMAGE_MIMES

                            if is_image_input and target_format in _DOC_FORMATS:
                                raise ValueError(
                                    f"Drive Node: cannot convert image to '{target_format}' — "
                                    f"choose an image output format (jpg, png, bmp, webp)"
                                )
                            if not is_image_input and target_format in _IMAGE_FORMATS:
                                raise ValueError(
                                    f"Drive Node: cannot convert document to '{target_format}' — "
                                    f"choose a document output format (pdf, docx, html, md, txt)"
                                )

                            disk_path = _storage_root() / file_row.storage_path
                            if not disk_path.exists():
                                raise ValueError(
                                    f"Drive Node: source file not found on disk: {src_filename}"
                                )
                            src_bytes = disk_path.read_bytes()

                            if is_image_input:
                                try:
                                    out_bytes, out_mime = _convert_image(src_bytes, target_format)
                                except Exception as exc:
                                    raise ValueError(
                                        f"Drive Node: conversion failed: {exc}"
                                    ) from exc
                                norm_ext = (
                                    "jpg" if target_format in ("jpg", "jpeg") else target_format
                                )
                                base_name = (
                                    src_filename.rsplit(".", 1)[0]
                                    if "." in src_filename
                                    else src_filename
                                )
                                out_filename = f"{base_name}.{norm_ext}"
                            else:
                                pandoc_fmt = _detect_pandoc_format(src_mime, src_filename)
                                if pandoc_fmt is None and src_mime != "application/pdf":
                                    raise ValueError(
                                        f"Drive Node: convertFile does not support input format '{src_mime}'"
                                    )
                                _FORMAT_TO_EXT = {
                                    "pdf": "pdf",
                                    "docx": "docx",
                                    "html": "html",
                                    "md": "md",
                                    "txt": "txt",
                                }
                                _FORMAT_TO_MIME = {
                                    "pdf": "application/pdf",
                                    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    "html": "text/html",
                                    "md": "text/markdown",
                                    "txt": "text/plain",
                                }
                                _PANDOC_TARGET = {
                                    "pdf": "pdf",
                                    "docx": "docx",
                                    "html": "html",
                                    "md": "markdown",
                                    "txt": "plain",
                                }
                                if target_format not in _PANDOC_TARGET:
                                    raise ValueError(
                                        f"Drive Node: convertFile does not support output format '{target_format}'"
                                    )
                                base_name = (
                                    src_filename.rsplit(".", 1)[0]
                                    if "." in src_filename
                                    else src_filename
                                )
                                out_ext = _FORMAT_TO_EXT[target_format]
                                out_filename = f"{base_name}.{out_ext}"
                                out_mime = _FORMAT_TO_MIME[target_format]
                                try:
                                    with _tempfile.TemporaryDirectory() as tmpdir:
                                        if src_mime == "application/pdf":
                                            extracted = _extract_pdf_text(src_bytes)
                                            src_tmp = f"{tmpdir}/input.txt"
                                            with open(src_tmp, "w", encoding="utf-8") as fh:
                                                fh.write(extracted)
                                            pandoc_fmt = "plain"
                                        else:
                                            src_ext = (
                                                src_filename.rsplit(".", 1)[-1]
                                                if "." in src_filename
                                                else "txt"
                                            )
                                            src_tmp = f"{tmpdir}/input.{src_ext}"
                                            with open(src_tmp, "wb") as fh:
                                                fh.write(src_bytes)
                                        out_tmp = f"{tmpdir}/output.{out_ext}"
                                        extra_args = (
                                            ["--pdf-engine=weasyprint"]
                                            if target_format == "pdf"
                                            else []
                                        )
                                        _pypandoc.convert_file(
                                            src_tmp,
                                            _PANDOC_TARGET[target_format],
                                            outputfile=out_tmp,
                                            format=pandoc_fmt,
                                            extra_args=extra_args,
                                        )
                                        with open(out_tmp, "rb") as fh:
                                            out_bytes = fh.read()
                                except Exception as exc:
                                    raise ValueError(
                                        f"Drive Node: conversion failed: {exc}"
                                    ) from exc

                            _max_bytes = _settings.file_max_size_mb * 1024 * 1024
                            if len(out_bytes) > _max_bytes:
                                raise ValueError(
                                    f"Drive Node: converted file exceeds size limit ({_settings.file_max_size_mb} MB)"
                                )

                            import secrets as _secrets

                            new_uuid = uuid.uuid4()
                            rel_path = f"{owner_id}/{new_uuid}/{out_filename}"
                            abs_path = _storage_root() / rel_path
                            abs_path.parent.mkdir(parents=True, exist_ok=True)
                            abs_path.write_bytes(out_bytes)

                            new_row = GeneratedFile(
                                id=new_uuid,
                                owner_id=owner_id,
                                workflow_id=self.workflow_id,
                                filename=out_filename,
                                storage_path=rel_path,
                                mime_type=out_mime,
                                size_bytes=len(out_bytes),
                                source_node_id=node_id,
                                source_node_label=node_data.get("label"),
                                metadata_json={},
                            )
                            db.add(new_row)
                            db.flush()

                            token_str = _secrets.token_urlsafe(32)
                            db.add(
                                FileAccessToken(
                                    file_id=new_uuid,
                                    token=token_str,
                                    created_by_id=owner_id,
                                )
                            )
                            db.commit()

                            base_url = self._base_url
                            dl_url = build_download_url(base_url, token_str)
                            output = {
                                "status": "success",
                                "operation": "convertFile",
                                "id": str(new_uuid),
                                "filename": out_filename,
                                "mime_type": out_mime,
                                "size_bytes": len(out_bytes),
                                "download_url": dl_url,
                            }

                        elif operation != "getAll":
                            raise ValueError(f"Drive Node: unknown operation '{operation}'")
```

- [ ] **Step 4: Run all Drive node tests to verify they pass**

```bash
cd /Users/cerenakgun/Documents/Projects/heym_workspace/heym/backend
uv run pytest tests/test_drive_node.py -v
```

Expected: all tests PASS (including previous tests and new `DriveNodeConvertFileTests`).

- [ ] **Step 5: Run ruff checks**

```bash
cd /Users/cerenakgun/Documents/Projects/heym_workspace/heym/backend
uv run ruff check app/services/workflow_executor.py
uv run ruff format app/services/workflow_executor.py
```

Expected: no errors. If ruff auto-formats, re-run tests to confirm nothing broke.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/workflow_executor.py backend/tests/test_drive_node.py
git commit -m "feat: add Drive convertFile operation (pandoc + Pillow)"
```

---

## Task 4: Frontend UI — operation option + target format dropdown

**Files:**
- Modify: `frontend/src/components/Panels/PropertiesPanel.vue`

Three changes in PropertiesPanel.vue:
1. Add `convertFile` to `driveOperationOptions` (line ~3147)
2. Add target format dropdown section in the drive template (after the `setMaxDownloads` section, ~line 10033)
3. Add output hint block for `convertFile` (inside the output `<template>` chain, ~line 10066)

- [ ] **Step 1: Add `convertFile` to `driveOperationOptions`**

Find this block (lines 3139–3147):
```typescript
const driveOperationOptions = [
  { value: "get", label: "Get File" },
  { value: "getAll", label: "Get All Files" },
  { value: "downloadUrl", label: "Download from URL" },
  { value: "delete", label: "Delete File" },
  { value: "setPassword", label: "Set Password" },
  { value: "setTtl", label: "Set TTL (Expiry)" },
  { value: "setMaxDownloads", label: "Set Max Downloads" },
];
```

Replace with:
```typescript
const driveOperationOptions = [
  { value: "get", label: "Get File" },
  { value: "getAll", label: "Get All Files" },
  { value: "downloadUrl", label: "Download from URL" },
  { value: "convertFile", label: "Convert File" },
  { value: "delete", label: "Delete File" },
  { value: "setPassword", label: "Set Password" },
  { value: "setTtl", label: "Set TTL (Expiry)" },
  { value: "setMaxDownloads", label: "Set Max Downloads" },
];
```

- [ ] **Step 2: Add `driveConvertFormatOptions` constant**

Right after the `driveOperationOptions` array (after line 3147), insert:
```typescript
const driveConvertFormatOptions = [
  { value: "pdf", label: "PDF (.pdf)" },
  { value: "docx", label: "Word Document (.docx)" },
  { value: "html", label: "HTML (.html)" },
  { value: "md", label: "Markdown (.md)" },
  { value: "txt", label: "Plain Text (.txt)" },
  { value: "jpg", label: "JPEG Image (.jpg)" },
  { value: "png", label: "PNG Image (.png)" },
  { value: "bmp", label: "BMP Image (.bmp)" },
  { value: "webp", label: "WebP Image (.webp)" },
];
```

- [ ] **Step 3: Add target format dropdown in the Drive template**

Find this block (lines 10018–10033):
```vue
            <div
              v-if="selectedNode.data.driveOperation === 'setMaxDownloads'"
              class="space-y-2"
            >
              <Label>Max Downloads</Label>
              <Input
                type="number"
                :model-value="selectedNode.data.driveMaxDownloads ?? ''"
                min="1"
                placeholder="e.g. 5"
                @update:model-value="updateNodeData('driveMaxDownloads', $event !== '' ? Number($event) : undefined)"
              />
              <p class="text-xs text-muted-foreground">
                Maximum number of times the file can be downloaded
              </p>
            </div>
```

After that closing `</div>` (line 10033), insert:
```vue

            <div
              v-if="selectedNode.data.driveOperation === 'convertFile'"
              class="space-y-2"
            >
              <Label>Target Format</Label>
              <Select
                :model-value="selectedNode.data.driveConvertTargetFormat || ''"
                :options="driveConvertFormatOptions"
                @update:model-value="updateNodeData('driveConvertTargetFormat', $event || undefined)"
              />
              <p class="text-xs text-muted-foreground">
                Format to convert the file to
              </p>
            </div>
```

- [ ] **Step 4: Add output hint for `convertFile`**

Find this block (lines 10066–10070):
```vue
                <template v-else-if="selectedNode.data.driveOperation === 'setPassword' || selectedNode.data.driveOperation === 'setTtl' || selectedNode.data.driveOperation === 'setMaxDownloads'">
                  <div>${{ selectedNode.data.label }}.status - "updated"</div>
                  <div>${{ selectedNode.data.label }}.file_id - file ID</div>
                  <div>${{ selectedNode.data.label }}.download_url - new access URL</div>
                </template>
```

Before that block, insert:
```vue
                <template v-else-if="selectedNode.data.driveOperation === 'convertFile'">
                  <div>${{ selectedNode.data.label }}.id - new converted file UUID</div>
                  <div>${{ selectedNode.data.label }}.filename - converted filename</div>
                  <div>${{ selectedNode.data.label }}.mime_type - MIME type</div>
                  <div>${{ selectedNode.data.label }}.size_bytes - file size</div>
                  <div>${{ selectedNode.data.label }}.download_url - Drive download URL</div>
                </template>
```

- [ ] **Step 5: Run typecheck and lint**

```bash
cd /Users/cerenakgun/Documents/Projects/heym_workspace/heym/frontend
bun run typecheck
bun run lint
```

Expected: no errors. Fix any TypeScript warnings before proceeding.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/Panels/PropertiesPanel.vue
git commit -m "feat: add convertFile UI to Drive node properties panel"
```

---

## Task 5: Update DSL prompt

**Files:**
- Modify: `backend/app/services/workflow_dsl_prompt.py` (lines 2822–2915)

- [ ] **Step 1: Add `convertFile` to the driveOperation enum**

Find line 2822:
```
  - `driveOperation`: Operation — `"get"` | `"getAll"` | `"downloadUrl"` | `"delete"` | `"setPassword"` | `"setTtl"` | `"setMaxDownloads"`
```

Replace with:
```
  - `driveOperation`: Operation — `"get"` | `"getAll"` | `"downloadUrl"` | `"convertFile"` | `"delete"` | `"setPassword"` | `"setTtl"` | `"setMaxDownloads"`
```

- [ ] **Step 2: Add the two new fields after line 2829**

After the `driveMaxDownloads` field line (line 2829):
```
  - `driveMaxDownloads`: Max download count as integer (setMaxDownloads only)
```

Add:
```
  - `driveConvertTargetFormat`: Target format for conversion — `"pdf"` | `"docx"` | `"html"` | `"md"` | `"txt"` | `"jpg"` | `"png"` | `"bmp"` | `"webp"` (convertFile only)
```

Note: `convertFile` reuses the existing `driveFileId` field for the source file UUID.

- [ ] **Step 3: Add `convertFile` row to the operations table**

Find line 2841:
```
| `setMaxDownloads` | driveFileId, driveMaxDownloads | Replace default public token with one limited to N downloads |
```

After it, add:
```
| `convertFile` | driveFileId, driveConvertTargetFormat | Convert the file to a new format; stores result as a new Drive file (original unchanged) |
```

- [ ] **Step 4: Add a DSL example for convertFile**

After the last example block (after line 2915, after the `setMaxDownloads` example `}`), add:

```
**Example - Convert Markdown to PDF**:
```json
{
  "id": "drive-convert",
  "type": "drive",
  "position": {"x": 600, "y": 200},
  "data": {
    "label": "convertDoc",
    "driveOperation": "convertFile",
    "driveFileId": "$reportAgent._generated_files[0].id",
    "driveConvertTargetFormat": "pdf"
  }
}
```
Access the converted file downstream: `$convertDoc.id`, `$convertDoc.download_url`
```

- [ ] **Step 5: Run ruff check**

```bash
cd /Users/cerenakgun/Documents/Projects/heym_workspace/heym/backend
uv run ruff check app/services/workflow_dsl_prompt.py
uv run ruff format app/services/workflow_dsl_prompt.py
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/workflow_dsl_prompt.py
git commit -m "docs(dsl): add convertFile operation to Drive node DSL prompt"
```

---

## Task 6: Update written documentation

**Files:**
- Modify: `frontend/src/docs/content/nodes/drive-node.md`
- Modify: `frontend/src/docs/content/reference/drive.md`

### drive-node.md changes

- [ ] **Step 1: Add new fields to the parameters table**

Find the parameters table row for `driveMaxDownloads` (line 24):
```
| `driveMaxDownloads` | number | Maximum allowed downloads (`setMaxDownloads` only) |
```

After it, add:
```
| `driveConvertTargetFormat` | string (enum) | Target format for conversion: `pdf`, `docx`, `html`, `md`, `txt`, `jpg`, `png`, `bmp`, `webp` (`convertFile` only) |
```

Note: `convertFile` reuses `driveFileId` for the source file — no new field needed for the ID.

- [ ] **Step 2: Add `convertFile` row to the operations table**

Find line 56:
```
| `setMaxDownloads` | driveFileId, driveMaxDownloads | Replace the default public token with one limited to N downloads |
```

After it, add:
```
| `convertFile` | driveFileId, driveConvertTargetFormat | Convert the file to a new format using pandoc (documents) or Pillow (images). Stores the result as a new Drive file — original is unchanged. |
```

- [ ] **Step 3: Add `convertFile` example block**

After the "Example — Limit Downloads" block (after line 163), add:

```markdown
## Example — Convert Markdown to PDF

```json
{
  "type": "drive",
  "data": {
    "label": "convertDoc",
    "driveOperation": "convertFile",
    "driveFileId": "$reportAgent._generated_files[0].id",
    "driveConvertTargetFormat": "pdf"
  }
}
```

The original file is preserved. The converted file is stored as a new Drive file.

Reference the converted file downstream: `$convertDoc.id`, `$convertDoc.download_url`

## Example — Convert PNG to JPEG

```json
{
  "type": "drive",
  "data": {
    "label": "compressImage",
    "driveOperation": "convertFile",
    "driveFileId": "$captureNode._generated_files[0].id",
    "driveConvertTargetFormat": "jpg"
  }
}
```
```

- [ ] **Step 4: Add `convertFile` output access section**

Find the `**delete:**` section (after line 193), and add before it:

```markdown
**convertFile:**
- `$nodeLabel.id` — UUID of the newly converted file
- `$nodeLabel.filename` — converted filename (e.g. `report.pdf`)
- `$nodeLabel.mime_type` — MIME type of the converted file
- `$nodeLabel.size_bytes` — file size in bytes
- `$nodeLabel.download_url` — public download URL

**Supported conversions:**
- Documents (via pandoc): `docx`, `html`, `md`, `txt`, `csv`, `pdf` (input) → `pdf`, `docx`, `html`, `md`, `txt`
- Images (via Pillow): `jpg`, `png`, `bmp`, `webp` → `jpg`, `png`, `bmp`, `webp`
- PDF input: text is extracted and converted to the target format

```

### drive.md changes

- [ ] **Step 5: Add conversion mention to drive.md**

Find lines 56–62 in `frontend/src/docs/content/reference/drive.md`:
```markdown
The [Drive node](../nodes/drive-node.md) lets you manage Drive files programmatically from within a workflow. Use it to:

- **List** your files and return metadata such as filename, MIME type, size, source, and download URL
- **Delete** a file after it has been delivered to the user
- **Set a password** on the download link
```

Replace with:
```markdown
The [Drive node](../nodes/drive-node.md) lets you manage Drive files programmatically from within a workflow. Use it to:

- **List** your files and return metadata such as filename, MIME type, size, source, and download URL
- **Convert** a file to a different format — documents via pandoc (docx, html, md, txt, pdf) or images via Pillow (jpg, png, bmp, webp)
- **Delete** a file after it has been delivered to the user
- **Set a password** on the download link
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/docs/content/nodes/drive-node.md frontend/src/docs/content/reference/drive.md
git commit -m "docs: add convertFile operation docs to Drive node and reference"
```

---

## Task 7: Full check

- [ ] **Step 1: Run all backend tests**

```bash
cd /Users/cerenakgun/Documents/Projects/heym_workspace/heym
./run_tests.sh
```

Expected: all tests pass.

- [ ] **Step 2: Run frontend checks**

```bash
cd /Users/cerenakgun/Documents/Projects/heym_workspace/heym/frontend
bun run typecheck
bun run lint
```

Expected: no errors.

- [ ] **Step 3: Run full check script**

```bash
cd /Users/cerenakgun/Documents/Projects/heym_workspace/heym
./check.sh
```

Expected: all checks pass (lint + typecheck + tests).

---

## Self-Review Notes

- `convertFile` reuses `driveFileId` (not a new field) — the frontend File ID section shows automatically since `convertFile` is not in the `['downloadUrl', 'getAll']` exclusion list
- PDF output for document conversions uses `--pdf-engine=weasyprint` (weasyprint installed in Dockerfile)
- PDF as *input* uses pypdf text extraction, not pandoc reading (pandoc can't read PDF)
- Image → doc format cross-conversion raises a descriptive error before any IO
- Output is always a new file; source file is never modified
- `driveExpressionFieldCount` computed already returns `1` for `convertFile` — no change needed
- `isDriveFileIdAgentProvided` already handles `convertFile` since it checks `driveFileId` — no change needed
