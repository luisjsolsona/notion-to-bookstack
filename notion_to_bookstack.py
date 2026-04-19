#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notion Markdown export → BookStack migrator

Features:
  - Images resized with Pillow and embedded as inline base64 data URIs
  - Animated GIFs preserved (raw bytes, never re-encoded)
  - Notion <aside> callout blocks → styled HTML divs (headings preserved)
  - Notion checkboxes (- [ ] / - [x]) → ☐ / ☑
  - YouTube links (bare URLs and markdown links) → responsive iframes
  - File attachments uploaded to BookStack (PDF, DOCX, XLSX, PPTX, ZIP, …)
  - Broken relative file links in HTML replaced with real attachment URLs
  - Handles Notion-truncated folder names (exact + prefix matching)
  - Batch mode: migrate multiple books in one run
  - Single mode: migrate one directory as one book
"""

import base64
import io
import os
import re
import sys
import urllib.parse

import requests
import markdown as md_lib
from PIL import Image

# Force UTF-8 on Windows stdout/stderr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ── Configuration ─────────────────────────────────────────────────────────────
BOOKSTACK_URL = "http://your-bookstack-host:port"   # e.g. http://192.168.1.10:8080
TOKEN_ID      = "YOUR_TOKEN_ID"
TOKEN_SECRET  = "YOUR_TOKEN_SECRET"

# Single mode: set EXPORT_ROOT and BOOK_NAME, leave BATCH empty
EXPORT_ROOT = r"/path/to/notion/export"
BOOK_NAME   = "My Book"

# Batch mode: list of (export_root, book_name) — takes priority over single mode
BATCH: list[tuple[str, str]] = [
    # (r"/path/to/export1", "Book 1"),
    # (r"/path/to/export2", "Book 2"),
]
# ─────────────────────────────────────────────────────────────────────────────

API          = f"{BOOKSTACK_URL}/api"
HEADERS      = {"Authorization": f"Token {TOKEN_ID}:{TOKEN_SECRET}"}
NOTION_ID_RE = re.compile(r'\s+[0-9a-f]{32}$')
IMG_MAX_PX   = 1200   # max long-side px when resizing images
IMG_QUALITY  = 78     # JPEG quality

ATTACH_EXTS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.odt', '.ods', '.odp', '.csv', '.txt', '.zip', '.yaml', '.yml',
}


# ── API helpers ───────────────────────────────────────────────────────────────

def clean_title(filename: str) -> str:
    name = os.path.splitext(filename)[0]
    return NOTION_ID_RE.sub('', name).strip()


def api_post(endpoint: str, json_data: dict) -> dict:
    r = requests.post(f"{API}/{endpoint}", json=json_data, headers=HEADERS)
    if not r.ok:
        print(f"  ERROR {r.status_code} POST {endpoint}: {r.text[:300]}")
        r.raise_for_status()
    return r.json()


def upload_attachment(page_id: int, file_path: str) -> None:
    file_path = file_path.strip()
    if not os.path.isfile(file_path):
        return
    with open(file_path, 'rb') as f:
        r = requests.post(
            f"{API}/attachments",
            headers=HEADERS,
            data={"uploaded_to": page_id, "name": os.path.basename(file_path)},
            files={"file": (os.path.basename(file_path), f)},
        )
    status = "[attachment]" if r.ok else f"[attachment error {r.status_code}]"
    print(f"    {status} {os.path.basename(file_path)}")


# ── Path resolution (handles Notion-truncated names) ─────────────────────────

def resolve_path(abs_path: str) -> str:
    """
    Resolves paths where Notion has truncated folder/file names
    (trailing spaces, missing closing parentheses, etc.).
    Strategy: exact match → bidirectional prefix match → fallback.
    """
    abs_path = abs_path.strip()
    if os.path.exists(abs_path):
        return abs_path
    parts   = abs_path.replace('\\', '/').split('/')
    current = parts[0] + '\\'
    for part in parts[1:]:
        part = part.strip()
        if not os.path.isdir(current):
            return abs_path
        entries = os.listdir(current)
        # 1) exact match (ignoring trailing whitespace)
        exact = [c for c in entries if c.strip() == part]
        if exact:
            current = os.path.join(current, exact[0])
            continue
        # 2) bidirectional prefix: on-disk name starts with search term
        #    OR search term starts with on-disk name (truncated during extraction)
        prefix = [c for c in entries
                  if c.strip().startswith(part) or part.startswith(c.strip())]
        if prefix:
            best = min(prefix, key=len)
            current = os.path.join(current, best)
            continue
        # 3) no match — return as-is (will be reported as not found)
        return os.path.join(current, part)
    return current


# ── Image processing ──────────────────────────────────────────────────────────

def img_to_base64(abs_path: str) -> str | None:
    """
    Returns a base64 data URI for the image.
    GIFs are read as raw bytes to preserve animation.
    Other formats are resized with Pillow (max IMG_MAX_PX on the long side).
    """
    abs_path = resolve_path(abs_path)
    if not os.path.isfile(abs_path):
        return None
    if abs_path.lower().endswith('.gif'):
        with open(abs_path, 'rb') as f:
            data = base64.b64encode(f.read()).decode('ascii')
        return f"data:image/gif;base64,{data}"
    try:
        with Image.open(abs_path) as img:
            w, h = img.size
            if max(w, h) > IMG_MAX_PX:
                ratio = IMG_MAX_PX / max(w, h)
                img   = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGBA')
                img.save(buf, format='PNG', optimize=True)
                mime = 'image/png'
            else:
                img = img.convert('RGB')
                img.save(buf, format='JPEG', quality=IMG_QUALITY, optimize=True)
                mime = 'image/jpeg'
            data = base64.b64encode(buf.getvalue()).decode('ascii')
            return f"data:{mime};base64,{data}"
    except Exception as e:
        print(f"    [img error] {os.path.basename(abs_path)}: {e}")
        return None


def embed_images(content: str, md_dir: str) -> str:
    """Replaces local image paths in Markdown with inline base64 data URIs."""
    # Regex supports balanced parentheses in paths: e.g. (Folder Name)/image.png
    img_re = re.compile(r'!\[([^\]]*)\]\(((?:[^()\n]|\([^()\n]*\))*)\)')

    def replace(m):
        alt  = m.group(1)
        path = urllib.parse.unquote(m.group(2)).strip()
        if path.startswith('http://') or path.startswith('https://'):
            return m.group(0)
        resolved = resolve_path(os.path.join(md_dir, path))
        uri = img_to_base64(resolved)
        if uri:
            print(f"    [img ok] {os.path.basename(path)}")
            return f"![{alt}]({uri})"
        print(f"    [img not found] {path}")
        return m.group(0)

    return img_re.sub(replace, content)


# ── Notion → clean Markdown pipeline ─────────────────────────────────────────

MD_EXTENSIONS = ['tables', 'fenced_code', 'nl2br', 'sane_lists']

ASIDE_RE    = re.compile(r'<aside>(.*?)</aside>', re.DOTALL)
ASIDE_STYLE = (
    'background:#f0f4ff;border-left:4px solid #4a6fa5;'
    'border-radius:4px;padding:12px 16px;margin:12px 0;'
)

YT_RE = re.compile(
    r'(?:https?://)?(?:www\.)?'
    r'(?:youtube\.com/watch\?(?:[^&\s]*&)*v=|youtu\.be/)([A-Za-z0-9_-]{11})'
    r'([^\s]*)?'
)
YT_IFRAME = (
    '<div style="position:relative;padding-bottom:56.25%;height:0;'
    'overflow:hidden;margin:12px 0;">'
    '<iframe src="https://www.youtube.com/embed/{vid}" '
    'style="position:absolute;top:0;left:0;width:100%;height:100%;" '
    'frameborder="0" allowfullscreen loading="lazy"></iframe></div>'
)


def process_youtube(content: str) -> str:
    """
    Converts YouTube URLs to responsive iframes.
    Supports: youtube.com/watch?v=ID, youtu.be/ID, and markdown links.
    Requires ALLOWED_IFRAME_HOSTS=https://www.youtube.com in BookStack .env.
    """
    md_link_re = re.compile(
        r'\[([^\]]*)\]\((https?://(?:www\.)?'
        r'(?:youtube\.com/watch\?[^\s)]*|youtu\.be/[^\s)]+))\)'
    )
    def replace_md_link(m):
        vid_m = YT_RE.search(m.group(2))
        return YT_IFRAME.format(vid=vid_m.group(1)) if vid_m else m.group(0)
    content = md_link_re.sub(replace_md_link, content)

    def replace_bare(m):
        return YT_IFRAME.format(vid=m.group(1))
    content = re.sub(r'^' + YT_RE.pattern + r'\s*$', replace_bare,
                     content, flags=re.MULTILINE)
    return content


def process_asides(content: str) -> str:
    """Converts Notion <aside>…</aside> callouts to styled HTML divs."""
    def replace(m):
        inner_html = md_lib.markdown(m.group(1).strip(), extensions=MD_EXTENSIONS)
        return f'\n<div style="{ASIDE_STYLE}">\n{inner_html}\n</div>\n'
    return ASIDE_RE.sub(replace, content)


def process_checkboxes(content: str) -> str:
    """Converts Notion checkboxes to Unicode characters."""
    content = re.sub(r'^- \[ \] ', '- ☐ ', content, flags=re.MULTILINE)
    content = re.sub(r'^- \[x\] ', '- ☑ ', content,
                     flags=re.MULTILINE | re.IGNORECASE)
    return content


def notion_md_to_html(content: str) -> str:
    """Full pipeline: preprocess Notion Markdown → HTML."""
    content = process_checkboxes(content)
    content = process_youtube(content)   # before markdown (outputs raw HTML)
    content = process_asides(content)
    return md_lib.markdown(content, extensions=MD_EXTENSIONS)


# ── Page creation ─────────────────────────────────────────────────────────────

def create_page(book_id: int, chapter_id: int | None,
                md_path: str, md_dir: str) -> int | None:
    title = clean_title(os.path.basename(md_path))
    try:
        with open(md_path, encoding='utf-8') as f:
            raw = f.read()
    except OSError as e:
        print(f"    [skip, unreadable] {title}: {e}")
        return None

    html    = notion_md_to_html(embed_images(raw, md_dir))
    payload = {"name": title, "html": html}
    if chapter_id:
        payload["chapter_id"] = chapter_id
    else:
        payload["book_id"] = book_id

    page    = api_post("pages", payload)
    page_id = page["id"]
    print(f"    Page: {title} (id={page_id})")

    # Upload file attachments from the page's asset folder
    assets_dir = resolve_path(os.path.join(md_dir, title))
    if os.path.isdir(assets_dir):
        for fname in sorted(os.listdir(assets_dir)):
            fpath = os.path.join(assets_dir, fname)
            if os.path.splitext(fname)[1].lower() in ATTACH_EXTS and os.path.isfile(fpath):
                upload_attachment(page_id, fpath)

    return page_id


# ── Structure detection ───────────────────────────────────────────────────────

def collect_chapters(root: str) -> list[tuple[str, str, str | None]]:
    """
    Returns list of (chapter_title, chapter_dir, index_md_path|None).
    Flattens up to 2 levels: folders that contain only sub-folders (no .md files)
    have their sub-folders promoted to direct chapters.
    """
    chapters = []
    entries  = sorted(os.listdir(root))

    for entry in entries:
        full = os.path.join(root, entry)
        if not os.path.isdir(full):
            continue
        sub_mds  = [e for e in os.listdir(full)
                    if e.endswith('.md') and os.path.isfile(os.path.join(full, e))]
        sub_dirs = [e for e in os.listdir(full)
                    if os.path.isdir(os.path.join(full, e))]

        index_md = None
        for f in entries:
            if f.endswith('.md') and os.path.isfile(os.path.join(root, f)):
                if clean_title(f) == clean_title(entry + ".x"):
                    index_md = os.path.join(root, f)
                    break

        if sub_mds:
            chapters.append((entry, full, index_md))
        elif sub_dirs:
            for sub in sorted(sub_dirs):
                sub_full = os.path.join(full, sub)
                sub_mds2 = [e for e in os.listdir(sub_full)
                            if e.endswith('.md') and os.path.isfile(os.path.join(sub_full, e))]
                if sub_mds2:
                    idx2 = None
                    for f in os.listdir(full):
                        if f.endswith('.md') and os.path.isfile(os.path.join(full, f)):
                            if clean_title(f) == clean_title(sub + ".x"):
                                idx2 = os.path.join(full, f)
                                break
                    chapters.append((sub, sub_full, idx2))

    return chapters


# ── Migration entry point ─────────────────────────────────────────────────────

def migrate_one(export_root: str, book_name: str) -> None:
    """Migrates one Notion export directory → one BookStack Book."""
    print(f"\n{'='*60}")
    print(f"Creating book: {book_name}")
    book    = api_post("books", {"name": book_name, "description": "Imported from Notion"})
    book_id = book["id"]
    print(f"  Book created (id={book_id})\n")

    entries             = sorted(os.listdir(export_root))
    root_md_files       = [e for e in entries
                           if e.endswith('.md') and os.path.isfile(os.path.join(export_root, e))]
    chapters            = collect_chapters(export_root)
    chapter_index_paths = {idx for _, _, idx in chapters if idx}

    for md_file in root_md_files:
        full = os.path.join(export_root, md_file)
        if full not in chapter_index_paths:
            print(f"  Root page: {clean_title(md_file)}")
            create_page(book_id, None, full, export_root)

    for chapter_title, chapter_dir, index_md in chapters:
        title = clean_title(chapter_title + ".x")
        print(f"\nCreating chapter: {title}")
        chapter    = api_post("chapters", {"book_id": book_id, "name": title})
        chapter_id = chapter["id"]
        print(f"  Chapter created (id={chapter_id})")

        if index_md:
            print(f"  Index page:")
            create_page(book_id, chapter_id, index_md, os.path.dirname(index_md))

        for entry in sorted(os.listdir(chapter_dir)):
            if entry.endswith('.md') and os.path.isfile(os.path.join(chapter_dir, entry)):
                create_page(book_id, chapter_id,
                            os.path.join(chapter_dir, entry), chapter_dir)

    print(f"\n✓ Book '{book_name}' done.")


def main():
    print(f"Connecting to BookStack at {BOOKSTACK_URL}...")
    r = requests.get(f"{API}/books", headers=HEADERS)
    if not r.ok:
        print(f"Connection error: {r.status_code}")
        sys.exit(1)
    print("Connection OK")

    if BATCH:
        for export_root, book_name in BATCH:
            migrate_one(export_root, book_name)
    else:
        migrate_one(EXPORT_ROOT, BOOK_NAME)

    print("\n✓ All migrations completed.")


if __name__ == "__main__":
    main()
