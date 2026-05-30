---
name: drive-convertfile-design
description: Design spec for adding convertFile operation to the Drive node using pandoc (pypandoc) and Pillow
metadata:
  type: project
---

# Drive Node — `convertFile` Operation Design

**Date:** 2026-05-30  
**Branch:** `impl/drive-file-convert`  
**Status:** Approved

---

## Summary

Add a new `convertFile` operation to the existing Drive node. It reads a Drive file by ID, converts it to a user-selected target format using pandoc (for documents) or Pillow (for images), stores the result as a **new Drive file** (original unchanged), and outputs the new file's metadata.

---

## Decisions

| Question | Decision |
|---|---|
| Output behavior | New file — original untouched |
| Format detection | Auto from MIME type / extension |
| Target format selection | Dropdown (static list) in PropertiesPanel |
| Approach | Option A: pypandoc + pandoc binary |
| Unsupported niche formats | Removed: pptx, rst, asciidoc, odt, rtf |
| PDF input | pypdf text extraction → passed to pandoc |
| Image conversion | Pillow (separate code path) |

---

## Format Matrix

### Document conversions — pandoc / pypandoc

| Input MIME / Extension | Output formats |
|---|---|
| `text/markdown` / `.md` | `pdf`, `docx`, `html`, `txt` |
| `text/html` / `.html` | `pdf`, `docx`, `md`, `txt` |
| `application/vnd.openxmlformats-officedocument.wordprocessingml.document` / `.docx` | `pdf`, `html`, `md`, `txt` |
| `text/plain` / `.txt` | `pdf`, `docx`, `html`, `md` |
| `text/csv` / `.csv` | `md` (table), `html`, `txt` |

### PDF input — pypdf → text → pandoc

| Input | Output formats |
|---|---|
| `application/pdf` / `.pdf` | `docx`, `md`, `txt`, `html` |

> Text is extracted via `pypdf.PdfReader`, written to a temp `.txt`, then converted by pandoc.

### Image conversions — Pillow

| Input MIME | Output formats |
|---|---|
| `image/jpeg`, `image/jpg` | `jpg`, `png`, `bmp`, `webp` |
| `image/png` | `jpg`, `png`, `bmp`, `webp` |
| `image/bmp` | `jpg`, `png`, `bmp`, `webp` |
| `image/webp` | `jpg`, `png`, `bmp`, `webp` |

---

## New Node Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `driveConvertFileId` | expression / string | yes | UUID of the source Drive file |
| `driveConvertTargetFormat` | string (enum) | yes | One of: `pdf`, `docx`, `html`, `md`, `txt`, `jpg`, `png`, `bmp`, `webp` |

The target format dropdown options:
```
pdf, docx, html, md, txt      ← documents
jpg, png, bmp, webp           ← images
```

---

## Backend Changes

### `backend/Dockerfile`
```dockerfile
RUN apt-get install -y pandoc weasyprint
```
- `pandoc` — universal document converter binary (~35 MB)
- `weasyprint` — PDF engine used by pandoc for `--pdf-engine=weasyprint`

### `backend/pyproject.toml`
```toml
"pypandoc>=1.13",
"Pillow>=11.0",
```

### `backend/app/services/workflow_executor.py`

Add `"convertFile"` to the Drive node handler (`elif node_type == "drive"`):

```python
elif operation == "convertFile":
    file_id_str = _resolve_template(node_data.get("driveConvertFileId", ""), ...)
    target_format = node_data.get("driveConvertTargetFormat", "")
    # 1. Load source file from DB (ownership check)
    # 2. Auto-detect input format from file_row.mime_type / extension
    # 3. Route: image → Pillow, document/PDF → pandoc
    # 4. Convert to tempfile
    # 5. Store result as new GeneratedFile + FileAccessToken
    # 6. Return output dict with id, filename, mime_type, size_bytes, download_url
```

**Input format detection helper:**
```python
def _detect_pandoc_format(mime_type: str, filename: str) -> str | None:
    """Returns pandoc format string or None if not a document type."""
```

**Image conversion helper:**
```python
def _convert_image(src_bytes: bytes, target_format: str) -> tuple[bytes, str]:
    """Returns (converted_bytes, output_mime_type)."""
```

**PDF-to-text helper:**
```python
def _extract_pdf_text(src_bytes: bytes) -> str:
    """Extract plain text from PDF via pypdf."""
```

---

## Frontend Changes

### `PropertiesPanel.vue`

1. Add `{ value: "convertFile", label: "Convert File" }` to `driveOperationOptions`
2. Add UI block for `convertFile`:
   - **File ID** — ExpressionInput (`driveConvertFileId`), same pattern as other file ID fields
   - **Target Format** — Select dropdown (`driveConvertTargetFormat`) with options for pdf/docx/html/md/txt/jpg/png/bmp/webp
3. Extend `driveExpressionFieldCount` / `isDriveFileIdAgentProvided` checks if needed

---

## DSL Changes

### `backend/app/services/workflow_dsl_prompt.py`

In section `### 29. drive (Drive File Management)`:

1. Add `"convertFile"` to the `driveOperation` enum list
2. Add new fields:
   - `driveConvertFileId`
   - `driveConvertTargetFormat`
3. Add table row for `convertFile`
4. Add a DSL example

---

## Documentation Changes

### `frontend/src/docs/content/nodes/drive-node.md`
- Add `driveConvertFileId` and `driveConvertTargetFormat` to parameters table
- Add `convertFile` row to operations table
- Add `convertFile` example JSON block
- Add output access section for `convertFile`

### `frontend/src/docs/content/reference/drive.md`
- Add brief mention of file conversion capability under "Managing Files from Workflows"

### `frontend/src/docs/content/tabs/drive-tab.md`
- No changes needed (Drive tab UI is read-only; conversions happen via the node)

---

## Output Shape

```json
{
  "status": "success",
  "operation": "convertFile",
  "id": "<new-uuid>",
  "filename": "original_name.pdf",
  "mime_type": "application/pdf",
  "size_bytes": 45231,
  "download_url": "https://your-domain.com/api/files/dl/abc123..."
}
```

Output access:
- `$nodeLabel.id` — UUID of the new converted file
- `$nodeLabel.filename` — converted filename
- `$nodeLabel.mime_type` — MIME type of the converted file
- `$nodeLabel.size_bytes` — file size in bytes
- `$nodeLabel.download_url` — public download URL

---

## Error Handling

| Condition | Error message |
|---|---|
| No file ID provided | `Drive Node: fileId is required for convertFile` |
| File not found / wrong owner | `Drive Node: file not found or access denied: {uuid}` |
| No target format | `Drive Node: targetFormat is required for convertFile` |
| Input format not supported | `Drive Node: convertFile does not support input format '{mime_type}'` |
| Incompatible: image → doc format | `Drive Node: cannot convert image to '{format}' — choose an image output format (jpg, png, bmp, webp)` |
| Incompatible: doc → image format | `Drive Node: cannot convert document to '{format}' — choose a document output format (pdf, docx, html, md, txt)` |
| Pandoc conversion failure | `Drive Node: conversion failed: {reason}` |
| Output exceeds size limit | `Drive Node: converted file exceeds size limit ({N} MB)` |

---

## Backend Tests

File: `backend/tests/test_drive_node.py` — extend existing class or add new `ConvertFileTests`.

| Test | Description |
|---|---|
| `test_convert_md_to_html` | Mocks pypandoc, verifies new file stored, output has `id`/`filename`/`download_url` |
| `test_convert_pdf_to_txt` | Mocks pypdf text extraction + pypandoc, verifies chain |
| `test_convert_image_png_to_jpg` | Mocks Pillow, verifies output MIME type is `image/jpeg` |
| `test_convert_unsupported_format_raises` | Pass `.zip` file, expect `ValueError` with correct message |
| `test_convert_incompatible_formats_raises` | Image input + `docx` target, expect `ValueError` |
| `test_convert_missing_file_id_raises` | Empty `driveConvertFileId`, expect `ValueError` |
| `test_convert_output_stored_as_new_file` | Verifies original file still exists after conversion |

---

## Implementation Order

1. `backend/Dockerfile` — add pandoc + weasyprint
2. `backend/pyproject.toml` — add pypandoc, Pillow
3. `backend/app/services/workflow_executor.py` — add `convertFile` handler + helpers
4. `backend/tests/test_drive_node.py` — add tests
5. `frontend/src/components/Panels/PropertiesPanel.vue` — add UI
6. `backend/app/services/workflow_dsl_prompt.py` — update DSL
7. `frontend/src/docs/content/nodes/drive-node.md` — update docs
8. `frontend/src/docs/content/reference/drive.md` — update docs
