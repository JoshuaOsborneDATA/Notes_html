#!/usr/bin/env python3
"""Copy image files from one directory to another, skipping up-to-date files.

Usage:
  python3 _build/copy_images.py <src> <dst>

Example:
  python3 _build/copy_images.py "/workspace/statistics-all-in-one/Machine Learning/figs" images
"""
import os
import sys
import shutil

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'}

if len(sys.argv) != 3:
    sys.exit('Usage: copy_images.py <src> <dst>')

src, dst = sys.argv[1], sys.argv[2]

if not os.path.isdir(src):
    sys.exit(f'Error: source directory not found: {src}')

os.makedirs(dst, exist_ok=True)

copied = 0
for fname in sorted(os.listdir(src)):
    if os.path.splitext(fname)[1].lower() not in IMAGE_EXTS:
        continue
    s = os.path.join(src, fname)
    d = os.path.join(dst, fname)
    if not os.path.exists(d) or os.path.getmtime(s) > os.path.getmtime(d):
        shutil.copy2(s, d)
        print(f'Copied: {fname}')
        copied += 1

print(f'{copied} file(s) copied.')
