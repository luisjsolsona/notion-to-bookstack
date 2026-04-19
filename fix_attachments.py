#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Post-migration helper: fixes broken relative file links in BookStack pages.

After migration, pages may contain HTML like:
  <a href="folder/document.pdf">document.pdf</a>

This script fetches all attachments from BookStack, finds pages where the
href points to a local relative path matching an uploaded attachment, and
replaces the href with the real BookStack attachment URL.

Usage:
    python fix_attachments.py
"""

import io, re, sys
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BOOKSTACK_URL = "http://your-bookstack-host:port"
TOKEN_ID      = "YOUR_TOKEN_ID"
TOKEN_SECRET  = "YOUR_TOKEN_SECRET"

API     = f"{BOOKSTACK_URL}/api"
HEADERS = {"Authorization": f"Token {TOKEN_ID}:{TOKEN_SECRET}"}

ATTACH_EXTS = {
    'pdf','doc','docx','xls','xlsx','ppt','pptx',
    'odt','ods','odp','csv','txt','zip','yaml','yml',
}


def all_attachments() -> list[dict]:
    r = requests.get(f"{API}/attachments", headers=HEADERS, params={"count": 500})
    r.raise_for_status()
    return r.json().get("data", [])


def main():
    print("Fetching attachments...")
    attachments = all_attachments()
    by_page: dict[int, list[dict]] = {}
    for a in attachments:
        by_page.setdefault(a["uploaded_to"], []).append(a)

    updated = 0
    for page_id, atts in by_page.items():
        resp = requests.get(f"{API}/pages/{page_id}", headers=HEADERS)
        if not resp.ok:
            continue
        html     = resp.json().get("html", "")
        new_html = html
        changed  = False

        for att in atts:
            ext = att["name"].rsplit(".", 1)[-1].lower()
            if ext not in ATTACH_EXTS:
                continue
            att_url = f"{BOOKSTACK_URL}/attachments/{att['id']}"
            pattern = re.compile(r'href="[^"]*' + re.escape(att["name"]) + r'"',
                                 re.IGNORECASE)
            new_html, n = pattern.subn(f'href="{att_url}"', new_html)
            if n:
                changed = True

        if changed:
            upd = requests.put(f"{API}/pages/{page_id}",
                               json={"html": new_html}, headers=HEADERS)
            if upd.ok:
                updated += 1
                print(f"  [✓] page {page_id}")
            else:
                print(f"  [✗ {upd.status_code}] page {page_id}")

    print(f"\n✓ Pages updated: {updated}")


if __name__ == "__main__":
    main()
