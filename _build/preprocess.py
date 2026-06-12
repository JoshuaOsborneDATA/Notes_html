#!/usr/bin/env python3
"""Preprocess Obsidian markdown -> standard markdown for pandoc.

Usage: python3 preprocess.py <src> <notesroot> <vault_root>
  src        - path to the source .md file
  notesroot  - relative path from the output HTML file back to notes/
  vault_root - path to the statistics-all-in-one vault root

This script is normally called by build.py, not directly. Example of what
build.py passes for a note three folders deep inside notes/:

  python3 _buildTest/preprocess.py \\
      "/workspace/statistics-all-in-one/hypothesis testing/AB-testing/multi-arm bandit/Thompson sampling.md" \\
      "../../../" \\
      "/workspace/statistics-all-in-one"

Transforms applied:
  - Obsidian image embeds   ![[fig.gif]]      -> standard markdown image
  - Obsidian wikilinks      [[Page|alias]]    -> <a> if published, <span> if not
  - h1 headings normalised to h2 so the TOC stays flat
  - Blank lines injected before headings and list items where pandoc needs them
  - **NOTE:** paragraphs wrapped in <p class="note-callout">
"""
import sys
import re
import os

src        = sys.argv[1]
notesroot  = sys.argv[2] if len(sys.argv) > 2 else ""
vault_root = sys.argv[3] if len(sys.argv) > 3 else ""


def slugify(s):
    return s.lower().replace(' ', '-')


def load_meta(yaml_path):
    meta = {}
    with open(yaml_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if ':' in line:
                key, _, val = line.partition(':')
                val = val.strip()
                if len(val) >= 2 and val[0] in ('"', "'") and val[-1] == val[0]:
                    val = val[1:-1]
                meta[key.strip()] = val
    return meta


def md_to_output_path(md_path, slug=None):
    rel   = os.path.relpath(md_path, vault_root)
    parts = rel.replace('\\', '/').split('/')
    parts = [slugify(p) for p in parts]
    parts[-1] = (slug or parts[-1][:-3]) + '.html'
    return '/'.join(parts)


# Build KNOWN_PAGES by scanning vault for sidecar .yaml files
KNOWN_PAGES = {}
if vault_root:
    for dirpath, dirnames, filenames in os.walk(vault_root):
        for md_file in filenames:
            if not md_file.endswith('.md'):
                continue
            stem      = md_file[:-3]
            yaml_fname = stem + '.yaml'
            if yaml_fname in filenames:
                yaml_path = os.path.join(dirpath, yaml_fname)
                meta      = load_meta(yaml_path)
                slug      = meta.get('slug', '') or None
                md_path   = os.path.join(dirpath, md_file)
                KNOWN_PAGES[stem] = md_to_output_path(md_path, slug)


with open(src, encoding='utf-8') as f:
    text = f.read()

# 1. Obsidian image embeds: ![[file.png]] -> ![](notesroot + images/file.png)
text = re.sub(
    r'!\[\[([^\]]+)\]\]',
    lambda m: f'![]({notesroot}images/{m.group(1)})',
    text
)

# 2. Obsidian wikilinks: [[Page|alias]] or [[Page]] -> link or styled span
def wikilink(m):
    inner = m.group(1)
    if '|' in inner:
        target, label = inner.split('|', 1)
    else:
        target = label = inner
    target = target.strip()
    label  = label.strip()
    page   = KNOWN_PAGES.get(target)
    if page:
        return f'<a href="{notesroot}{page}">{label}</a>'
    return f'<span class="wikilink" title="See: {target}">{label}</span>'

text = re.sub(r'\[\[([^\]]+)\]\]', wikilink, text)

# 3. Normalise h1 -> h2 so TOC stays flat
text = re.sub(r'^# (?!#)', '## ', text, flags=re.MULTILINE)

# 4. Blank line before list items that follow a paragraph ending with ':'
text = re.sub(r'(:[^\n]*)\n(-)', r'\1\n\n\2', text)

# 4b. Blank line before any heading that directly follows a non-blank line
text = re.sub(r'([^\n])\n(#{1,6} )', r'\1\n\n\2', text)

# 5. NOTE: callout paragraphs — use pandoc fenced div so math/markdown inside is processed
text = re.sub(
    r'^(\*\*NOTE:\*\*.*?)$',
    lambda m: f'::: {{.note-callout}}\n{m.group(1)}\n:::',
    text,
    flags=re.MULTILINE
)

print(text)
