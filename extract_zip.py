#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Helper script to extract Notion export ZIP files on Windows.

Handles:
  - UTF-8 filename decoding (cp437 → utf-8)
  - Windows-invalid characters replaced with _
  - Long folder names truncated to MAX_DIR chars
  - Optional prefix stripping (e.g. "Privado y compartido/")

Usage:
    python extract_zip.py <zip_file> <output_dir> [--prefix "Privado y compartido/"] [--max-dir 40]
"""

import argparse
import os
import sys
import zipfile

MAX_DIR_DEFAULT = 40
INVALID_CHARS   = '<>:"|?*'


def extract(zip_path: str, out_dir: str, prefix: str, max_dir: int) -> None:
    os.makedirs(out_dir, exist_ok=True)
    errors = 0

    with zipfile.ZipFile(zip_path, 'r') as z:
        for member in z.infolist():
            try:
                name = member.filename.encode('cp437').decode('utf-8')
            except Exception:
                name = member.filename

            if prefix and name.startswith(prefix):
                name = name[len(prefix):]

            parts  = name.rstrip('/').split('/')
            is_dir = member.is_dir()
            short  = []
            for i, p in enumerate(parts):
                is_file_part = (i == len(parts) - 1) and not is_dir
                for ch in INVALID_CHARS:
                    p = p.replace(ch, '_')
                short.append(p if is_file_part or len(p) <= max_dir else p[:max_dir].rstrip())

            dest = os.path.join(out_dir, *short)

            if is_dir:
                os.makedirs(dest, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                try:
                    with z.open(member) as src, open(dest, 'wb') as dst:
                        dst.write(src.read())
                except Exception as e:
                    print(f"  [skip] {name[-70:]}: {e}", file=sys.stderr)
                    errors += 1

    print(f"Done. Errors: {errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract Notion ZIP with UTF-8 filenames")
    parser.add_argument("zip_file",   help="Path to the ZIP file")
    parser.add_argument("output_dir", help="Destination directory")
    parser.add_argument("--prefix",   default="Privado y compartido/",
                        help="Path prefix to strip from entries (default: 'Privado y compartido/')")
    parser.add_argument("--max-dir",  type=int, default=MAX_DIR_DEFAULT,
                        help=f"Max chars per folder name component (default: {MAX_DIR_DEFAULT})")
    args = parser.parse_args()
    extract(args.zip_file, args.output_dir, args.prefix, args.max_dir)
