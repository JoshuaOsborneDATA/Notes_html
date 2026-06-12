#!/usr/bin/env python3
"""General build script for statistics-all-in-one notes.

Usage: python3 _build/build.py [vault_or_file] [notes_out]
  vault_or_file - path to the vault directory OR a single .md file
  notes_out     - output directory (default: current directory)

Directory mode: builds every note in the vault that has a sidecar .yaml,
mirroring the vault folder structure inside notes_out.

  python3 _build/build.py /workspace/statistics-all-in-one /workspace/portfolio/notes

Single-file mode: builds one note and places it flat into notes_out.
The output filename comes from the slug field in the sidecar yaml, or the
slugified .md filename if no slug is set.

  python3 _build/build.py \\
      "/workspace/statistics-all-in-one/hypothesis testing/AB-testing/multi-arm bandit/Thompson sampling.md" \\
      /workspace/portfolio/notes/hypothesis-testing/ab-testing/multi-arm-bandit

Discovers every .md file in the vault that has a matching <stem>.yaml sidecar,
then builds it to an HTML page mirroring the vault folder structure.

Each published note needs a sidecar YAML file with the same stem as the .md:

  My Note.md  ->  My Note.yaml

---- note with only a next page ----
title: My Note
description: "One-line description for the card."
next: hypothesis-testing/ab-testing/my-next-note.html
nexttitle: My Next Note

---- note with both prev and next ----
title: My Note
description: "One-line description for the card."
prev: hypothesis-testing/ab-testing/my-prev-note.html
prevtitle: My Previous Note
next: hypothesis-testing/ab-testing/my-next-note.html
nexttitle: My Next Note

---- standalone note with no neighbours ----
title: My Note
description: "One-line description for the card."

---- slug needed (filename alone gives the wrong URL) ----
title: Epsilon-Greedy Algorithm
description: "One-line description for the card."
slug: epsilon-greedy
prev: hypothesis-testing/ab-testing/multi-arm-bandit/multi-arm-bandit.html
prevtitle: Multi-Arm Bandit

Omitting prev/next (or leaving them blank) produces a page with no nav arrows.
"""
import os
import re
import subprocess
import sys

PANDOC     = '/tmp/pandoc-3.6.4/bin/pandoc'
VAULT      = sys.argv[1] if len(sys.argv) > 1 else '/workspace/statistics-all-in-one'
NOTES_OUT  = sys.argv[2] if len(sys.argv) > 2 else '.'
TEMPLATE   = '_build/template.html'
PRE        = '_build/preprocess.py'

# Notes root is the top-level notes/ folder — depth is always measured from here.
# In directory mode NOTES_OUT IS the notes root; in single-file mode it's the cwd.
NOTES_ROOT = NOTES_OUT if os.path.isdir(VAULT) else '.'


def convert_gifs(images_dir):
    """Convert every GIF in images_dir to WebM + MP4, skipping files already up to date."""
    try:
        import imageio_ffmpeg
    except ImportError:
        print('imageio-ffmpeg not installed — skipping GIF conversion.')
        return
    if not os.path.isdir(images_dir):
        return
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    for fname in sorted(os.listdir(images_dir)):
        if not fname.lower().endswith('.gif'):
            continue
        gif   = os.path.join(images_dir, fname)
        stem  = fname[:-4]
        webm  = os.path.join(images_dir, stem + '.webm')
        mtime = os.path.getmtime(gif)
        if not os.path.exists(webm) or os.path.getmtime(webm) < mtime:
            subprocess.run(
                [ffmpeg, '-y', '-i', gif,
                 '-c:v', 'libvpx-vp9', '-crf', '15', '-b:v', '0', '-an', webm],
                check=True, capture_output=True
            )
            print(f'Converted: {fname} -> {stem}.webm')


def slugify(s):
    return s.lower().replace(' ', '-')


def output_path(md_path, slug=None):
    """Mirror vault path into notes/, slugified. slug overrides the filename part."""
    rel   = os.path.relpath(md_path, VAULT)
    parts = rel.replace('\\', '/').split('/')
    parts = [slugify(p) for p in parts]
    parts[-1] = (slug or parts[-1][:-3]) + '.html'
    return '/'.join(parts)


def notesroot_for(out_path):
    """Return '../' * depth based on how many folders deep the output file sits."""
    return '../' * out_path.count('/')


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


def folder_display(vault_dir_name):
    """Convert a vault directory name to a readable display name.
    Splits on spaces only; hyphens within words are preserved.
    All-uppercase segments (e.g. AB) are kept as-is.
    """
    return ' '.join(
        '-'.join(seg if seg.isupper() else seg.title() for seg in word.split('-'))
        for word in vault_dir_name.split(' ')
    )


def collect_published_notes():
    """Scan the vault for all notes that have a sidecar yaml and a built HTML file."""
    found = []
    for dirpath, dirnames, filenames in os.walk(VAULT):
        if dirpath == VAULT:
            continue
        for md_file in filenames:
            if not md_file.endswith('.md'):
                continue
            stem = md_file[:-3]
            if (stem + '.yaml') not in filenames:
                continue
            md_path   = os.path.join(dirpath, md_file)
            yaml_path = os.path.join(dirpath, stem + '.yaml')
            meta      = load_meta(yaml_path)
            slug      = meta.get('slug', '') or None
            title     = meta.get('title', stem)
            out       = output_path(md_path, slug)
            if os.path.exists(os.path.join(NOTES_ROOT, out)):
                vault_rel = os.path.relpath(md_path, VAULT).replace('\\', '/').split('/')
                found.append((out, title, vault_rel))
    return found


def build_tree(notes):
    """Build a nested dict representing the folder/file tree."""
    tree = {}
    for out, title, vault_rel in sorted(notes, key=lambda x: x[0]):
        parts = out.replace('\\', '/').split('/')
        node  = tree
        for i, slug_part in enumerate(parts[:-1]):
            if slug_part not in node:
                vault_dir = vault_rel[i] if i < len(vault_rel) - 1 else slug_part
                node[slug_part] = {'_display': folder_display(vault_dir), '_notes': [], '_order': len(node)}
            node = node[slug_part]
        node['_notes'].append((out, title))
    return tree


def render_tree_html(node, indent=4):
    pad   = ' ' * indent
    lines = []
    children = sorted(
        [(k, v) for k, v in node.items() if k not in ('_display', '_notes', '_order')],
        key=lambda x: x[1].get('_order', 0)
    )
    for key, val in children:
        display = val.get('_display', key.title())
        lines += [
            f'{pad}<li>',
            f'{pad}  <details open>',
            f'{pad}    <summary>',
            f'{pad}      <span class="folder-icon">📂</span>',
            f'{pad}      <span class="folder-name">{display}</span>',
            f'{pad}      <span class="chevron">&#9654;</span>',
            f'{pad}    </summary>',
            f'{pad}    <ul>',
        ]
        lines += render_tree_html(val, indent + 4)
        for href, title in val.get('_notes', []):
            lines.append(
                f'{pad}      <li><a class="tree-file" href="{href}">'
                f'<span class="file-icon">📄</span> {title}</a></li>'
            )
        lines += [f'{pad}    </ul>', f'{pad}  </details>', f'{pad}</li>']
    return lines


def update_index():
    """Regenerate the notes tree section inside index.html."""
    index_path = os.path.join(NOTES_ROOT, 'index.html')
    if not os.path.exists(index_path):
        print(f'Warning: {index_path} not found, skipping index update.')
        return
    with open(index_path, encoding='utf-8') as f:
        content = f.read()
    notes     = collect_published_notes()
    tree      = build_tree(notes)
    tree_html = '\n'.join(['    <ul class="tree">'] + render_tree_html(tree) + ['    </ul>'])
    content   = re.sub(
        r'<!-- NOTES_TREE_START -->.*?<!-- NOTES_TREE_END -->',
        f'<!-- NOTES_TREE_START -->\n{tree_html}\n  <!-- NOTES_TREE_END -->',
        content,
        flags=re.DOTALL
    )
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('Updated: index.html')


def build(md_path, yaml_path, out):
    """Preprocess and compile one note to HTML."""
    stem      = os.path.basename(md_path)[:-3]
    meta      = load_meta(yaml_path)
    title     = meta.get('title', stem)
    desc      = meta.get('description', '')
    author    = meta.get('author', '')
    prev      = meta.get('prev', '')
    prevtitle = meta.get('prevtitle', '')
    nxt       = meta.get('next', '')
    nexttitle = meta.get('nexttitle', '')
    rel_out   = os.path.relpath(out, NOTES_ROOT).replace('\\', '/')
    nr        = notesroot_for(rel_out)
    root      = nr + '../'

    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)

    cmd_meta = [
        '-M', f'title={title}',
        '-M', f'root={root}',
        '-M', f'notesroot={nr}',
    ]
    if desc:      cmd_meta += ['-M', f'description={desc}']
    if author:    cmd_meta += ['-M', f'author={author}']
    if prev:      cmd_meta += ['-M', f'prev={prev}', '-M', f'prevtitle={prevtitle}']
    if nxt:       cmd_meta += ['-M', f'next={nxt}',  '-M', f'nexttitle={nexttitle}']

    vault_root = VAULT if os.path.isdir(VAULT) else os.path.dirname(md_path)
    pre = subprocess.run(
        [sys.executable, PRE, md_path, nr, vault_root],
        capture_output=True, text=True, check=True
    )

    subprocess.run(
        [PANDOC,
         '--from', 'markdown', '--to', 'html5',
         '--mathjax', '--toc', '--toc-depth=2', '--section-divs',
         '--template', TEMPLATE,
         ] + cmd_meta + ['-o', out],
        input=pre.stdout, text=True, check=True
    )
    print(f'Built: {out}')


convert_gifs(os.path.join(NOTES_ROOT, 'images'))

if os.path.isfile(VAULT):
    # Single-file mode: first arg is a .md file, output flat into NOTES_OUT
    md_path   = VAULT
    stem      = os.path.basename(md_path)[:-3]
    yaml_path = os.path.join(os.path.dirname(md_path), stem + '.yaml')
    if not os.path.exists(yaml_path):
        sys.exit(f'Error: no sidecar yaml found at {yaml_path}')
    meta      = load_meta(yaml_path)
    slug      = meta.get('slug', '') or slugify(stem)
    out       = os.path.join(NOTES_OUT, slug + '.html')
    build(md_path, yaml_path, out)

else:
    # Directory mode: walk vault, mirror structure into NOTES_OUT
    for dirpath, dirnames, filenames in os.walk(VAULT):
        if dirpath == VAULT:
            continue
        for md_file in filenames:
            if not md_file.endswith('.md'):
                continue
            stem      = md_file[:-3]
            yaml_file = stem + '.yaml'
            if yaml_file not in filenames:
                continue
            md_path   = os.path.join(dirpath, md_file)
            yaml_path = os.path.join(dirpath, yaml_file)
            slug      = (load_meta(yaml_path).get('slug', '') or None)
            out       = os.path.join(NOTES_OUT, output_path(md_path, slug))
            build(md_path, yaml_path, out)
    update_index()
