# notion-to-bookstack

Migrate Notion Markdown exports to a self-hosted [BookStack](https://www.bookstackapp.com/) instance.

## Features

- **Images** — resized with Pillow and embedded as inline base64 data URIs (no external image hosting needed)
- **Animated GIFs** — preserved as raw bytes, never re-encoded
- **Callout blocks** — Notion `<aside>` callouts converted to styled HTML divs
- **Checkboxes** — `- [ ]` / `- [x]` converted to ☐ / ☑
- **YouTube links** — bare URLs and Markdown links converted to responsive iframes
- **File attachments** — PDF, DOCX, XLSX, PPTX, ZIP, and more uploaded automatically to BookStack
- **Broken link repair** — post-migration helper replaces relative `href` paths with real BookStack attachment URLs
- **Notion quirks handled** — truncated folder names, 32-char hex IDs in filenames, URL-encoded image paths
- **Batch mode** — migrate multiple Notion exports in a single run

## Requirements

- Python 3.10+
- A running BookStack instance with API access enabled
- A BookStack API token (Settings → API Tokens)

Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Edit the constants at the top of `notion_to_bookstack.py`:

```python
BOOKSTACK_URL = "http://your-bookstack-host:port"
TOKEN_ID      = "YOUR_TOKEN_ID"
TOKEN_SECRET  = "YOUR_TOKEN_SECRET"

# Single book migration
EXPORT_ROOT = r"/path/to/notion/export"
BOOK_NAME   = "My Book"

# Batch migration (takes priority over single mode)
BATCH: list[tuple[str, str]] = [
    (r"/path/to/export1", "Book 1"),
    (r"/path/to/export2", "Book 2"),
]
```

## Usage

### 1. Extract the Notion ZIP (Windows)

Notion exports on Windows can have encoding and path-length issues. Use the helper:

```bash
python extract_zip.py notion_export.zip C:\output --prefix "My Workspace/" --max-dir 40
```

Options:
- `--prefix` — path prefix to strip from ZIP entries (default: `Privado y compartido/`)
- `--max-dir` — max characters per folder name component to avoid Windows MAX_PATH (default: `40`)

### 2. Run the migration

```bash
python notion_to_bookstack.py
```

The script will:
1. Connect to BookStack and verify credentials
2. Create a Book (and Chapters) matching the Notion folder structure
3. Convert each `.md` file to HTML and create a Page
4. Upload file attachments found in asset folders next to each page

### 3. Fix broken attachment links (optional)

If pages already exist with broken relative file links, run:

```bash
python fix_attachments.py
```

This fetches all uploaded attachments from BookStack, scans every page for `href="..."` attributes pointing to local relative paths, and replaces them with the real `/attachments/{id}` URLs.

### 4. Enable YouTube iframes (optional)

To render YouTube iframes, add this to your BookStack `.env` or `docker-compose.yml`:

```
ALLOWED_IFRAME_HOSTS=https://www.youtube.com https://www.youtube-nocookie.com
```

Then restart the container. The migration script converts YouTube links automatically; for already-migrated pages run the script again or use `fix_attachments.py`.

## BookStack structure mapping

| Notion | BookStack |
|--------|-----------|
| Export root | Book |
| Top-level folder | Chapter |
| `.md` file | Page |
| Asset folder (images, PDFs…) | Inline images + Attachments |

Folders nested more than one level deep are automatically flattened into Chapters.

## Notes

- Images are embedded as base64 data URIs to avoid managing a separate media server.
  For very large exports this increases page size; consider reducing `IMG_MAX_PX` or `IMG_QUALITY`.
- BookStack limits iframes to hosts listed in `ALLOWED_IFRAME_HOSTS`. YouTube iframes will not render without it.
- On Windows, use short base paths (e.g. `C:\n\`) to stay under the 260-character MAX_PATH limit.

## License

MIT
