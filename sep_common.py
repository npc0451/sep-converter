#!/usr/bin/env python3
"""
sep_common.py — Shared functions for SEP → EPUB/PDF conversion.
"""

import re
import os
import base64
from urllib.parse import urlparse, urljoin

import requests
from sep_network import fetch
from bs4 import BeautifulSoup, Tag, NavigableString
from html import escape as escape_html


# ─── User Agent ───────────────────────────────────────────────────

UA = 'sep2epub/1.0 (EPUB/PDF generator)'


# ─── CSS ──────────────────────────────────────────────────────────

def make_css(for_epub=True, font_dir='fonts'):
    """Generate the CSS stylesheet. for_epub includes EPUB-specific namespace."""

    # Build @font-face declarations for Source Sans Pro (EPUB only)
    font_faces = ''
    if for_epub and font_dir and os.path.isdir(font_dir):
        weights = [(200, '200'), (300, '300'), (400, '400'), (600, '600'), (700, '700'), (900, '900')]
        for wnum, wstr in weights:
            normal_path = os.path.join(font_dir, f'SourceSansPro-normal-{wstr}.ttf')
            italic_path = os.path.join(font_dir, f'SourceSansPro-italic-{wstr}.ttf')
            if os.path.exists(normal_path):
                font_faces += f'''@font-face {{
    font-family: "Source Sans Pro";
    font-style: normal;
    font-weight: {wnum};
    src: url("{normal_path}") format("truetype");
}}
'''
            if os.path.exists(italic_path):
                font_faces += f'''@font-face {{
    font-family: "Source Sans Pro";
    font-style: italic;
    font-weight: {wnum};
    src: url("{italic_path}") format("truetype");
}}
'''

    epub_ns = '@namespace epub "http://www.idpf.org/2007/ops";\n' if for_epub else ''
    pdf_page = '''@page {
    size: A4;
    margin: 2.5cm 2cm;
}
''' if not for_epub else ''

    return f'''{font_faces}
{epub_ns}{pdf_page}
body {{
    font-family: Georgia, "Times New Roman", serif;
    line-height: 1.6;
    color: #333;
    margin: 0;
    padding: 0;
}}

h1, h2, h3, h4, h5, h6 {{
    font-family: "Source Sans Pro", "Helvetica Neue", Arial, sans-serif;
    font-weight: 600;
    color: #8C1515;
    margin: 1.2em 0 0.5em 0;
    page-break-after: avoid;
}}

h1 {{
    font-size: 1.8em;
    border-bottom: 1px solid #ccc;
    padding-bottom: 0.3em;
}}

h2 {{
    font-size: 1.5em;
    border-bottom: 1px solid #eee;
    padding-bottom: 0.2em;
    {"page-break-before: always;" if not for_epub else ""}
}}

h3 {{
    font-size: 1.25em;
    color: #555;
}}

h4 {{
    font-size: 1.05em;
    color: #666;
    font-weight: 600;
}}

p {{
    margin: 0 0 0.8em 0;
    text-indent: 0;
}}

em, i {{
    font-style: italic;
}}

strong, b {{
    font-weight: bold;
}}

a {{
    color: #8C1515;
    text-decoration: none;
}}

a:hover {{
    text-decoration: underline;
}}

blockquote {{
    margin: 0.8em 1em;
    padding: 0.5em 1em;
    border-left: 3px solid #8C1515;
    color: #555;
    font-style: italic;
}}

ul, ol {{
    margin: 0.5em 0 0.8em 1.5em;
    padding: 0;
}}

li {{
    margin-bottom: 0.3em;
}}

hr {{
    border: none;
    border-top: 1px solid #ccc;
    margin: 1.5em 0;
}}

table {{
    border-collapse: collapse;
    margin: 0.8em 0;
}}

td, th {{
    padding: 0.3em 0.6em;
    border: 1px solid #ccc;
    vertical-align: top;
}}

.pubinfo {{
    font-style: italic;
    color: #666;
    font-size: 0.9em;
    margin-bottom: 1.2em;
}}

.source-url {{
    font-size: 0.85em;
    margin-bottom: 1.5em;
    word-break: break-all;
}}
.source-url a {{
    color: #555;
}}

.entry-separator {{
    border: none;
    border-top: 2px solid #8C1515;
    margin: 2em 0;
}}

.bibliography ul.hanging,
ul.hanging {{
    list-style: none;
    margin-left: 0;
    padding-left: 0;
}}
.bibliography ul.hanging li,
ul.hanging li {{
    text-indent: -2em;
    padding-left: 4em;
    margin-bottom: 0.6em;
}}

.suggestions {{
    font-style: italic;
    color: #555;
    margin: 1em 0;
}}

.academic-tools table {{
    border: none;
}}
.academic-tools td {{
    border: none;
    padding: 0.3em 0.5em;
}}

.preamble {{
    margin-bottom: 1.5em;
}}

nav#toc ol {{
    list-style: none;
    margin-left: 0;
    padding-left: 0;
}}
nav#toc ol li {{
    margin-bottom: 0.4em;
}}
nav#toc ol li ol {{
    margin-left: 1.5em;
}}
nav#toc a {{
    text-decoration: none;
}}
img {{
    max-width: 100%;
    height: auto;
}}
'''


# ─── Helpers ──────────────────────────────────────────────────────

def slugify(text, maxlen=60):
    """Create a safe filename slug from text."""
    s = text.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[-\s]+', '-', s)
    return s[:maxlen].rstrip('-')


def url_to_slug(url):
    """Extract a slug from a SEP URL like 'https://.../entries/lacan/' -> 'lacan'."""
    path = urlparse(url).path.rstrip('/')
    parts = [p for p in path.split('/') if p]
    if 'entries' in parts:
        idx = parts.index('entries')
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return parts[-1] if parts else 'entry'


def fetch_html(url, timeout=60):
    """Fetch HTML from a URL with a polite User-Agent."""
    resp = fetch(url, timeout=timeout)
    try:
        content = resp.content.decode('utf-8')
    except UnicodeDecodeError:
        content = resp.content.decode(resp.encoding or 'utf-8', errors='replace')
    return content


def fetch_image(url, timeout=30):
    """Download an image and return (data_bytes, mime_type)."""
    resp = fetch(url, timeout=timeout)
    ctype = resp.headers.get('Content-Type', 'image/png')
    return resp.content, ctype


def embed_images_in_html(html_str, base_url):
    """Find all <img> tags in HTML, download their src, replace with data URIs.

    Works on raw HTML string. Returns the HTML with embedded images.
    Skips images that fail to download — the original src is kept.
    """
    if '<img' not in html_str:
        return html_str

    # Ensure base URL ends with / so urljoin works correctly for relative paths
    if base_url and not base_url.endswith('/'):
        base_url += '/'

    def _replace_img(m):
        src = m.group(1)
        if not src or src.startswith('data:'):
            return m.group(0)
        abs_url = urljoin(base_url, src)
        try:
            data, ctype = fetch_image(abs_url, timeout=15)
            b64 = base64.b64encode(data).decode('ascii')
            data_uri = f'data:{ctype};base64,{b64}'
            return re.sub(r'\bsrc="[^"]*"', lambda _: 'src="' + data_uri + '"', m.group(0), count=1)
        except Exception as exc:
            import sys
            print(f'WARNING: image unavailable: {abs_url}: {exc}', file=sys.stderr)
            return re.sub(r'\bsrc="[^"]*"', 'data-image-missing="true"', m.group(0), count=1)

    # Match src attribute in any position within <img> tag
    return re.sub(r'<img[^>]*src="([^"]*)"', _replace_img, html_str)


def embed_images_epub(html_str, base_url, prefix='img', start_counter=0):
    """
    Find <img> tags, download images, assign EpubItem filenames.

    start_counter — starting index for filename numbering (use a running
                    counter across calls to avoid collisions).

    Returns (updated_html, image_list) where image_list contains dicts:
        {'filename': 'images/e0_0.jpg', 'data': bytes, 'media_type': 'image/jpeg'}
    """
    if '<img' not in html_str:
        return html_str, []

    if base_url and not base_url.endswith('/'):
        base_url += '/'

    counter = [start_counter]
    images = []

    def _replace_img(m):
        full_tag = m.group(0)
        src = m.group(1)
        if not src or src.startswith('data:') or src.startswith('images/'):
            return full_tag
        abs_url = urljoin(base_url, src)
        try:
            data, ctype = fetch_image(abs_url, timeout=15)
            ext = _mime_to_ext(ctype)
            filename = f'images/{prefix}_{counter[0]}{ext}'
            counter[0] += 1
            images.append({
                'filename': filename,
                'data': data,
                'media_type': ctype,
            })
            return re.sub(r'\bsrc="[^"]*"', lambda _: 'src="' + filename + '"', full_tag, count=1)
        except Exception as exc:
            import sys
            print(f'WARNING: image unavailable: {abs_url}: {exc}', file=sys.stderr)
            return re.sub(r'\bsrc="[^"]*"', 'data-image-missing="true"', full_tag, count=1)

    updated = re.sub(r'<img[^>]*src="([^"]*)"', _replace_img, html_str)
    return updated, images


def _mime_to_ext(mime):
    """Convert MIME type to file extension."""
    mapping = {
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/gif': '.gif',
        'image/svg+xml': '.svg',
        'image/webp': '.webp',
        'image/tiff': '.tiff',
    }
    return mapping.get(mime, '.bin')


# ─── Heading / Text Helpers ───────────────────────────────────────

def get_heading_id(heading_tag):
    """Extract the anchor id from a heading element or its child <a>."""
    if heading_tag.get('id'):
        return heading_tag['id']
    a = heading_tag.find('a')
    if a and a.get('id'):
        return a['id']
    return ''


def clean_heading_text(heading_tag):
    """Get clean text from a heading, stripping inner anchor markup."""
    a = heading_tag.find('a')
    text = a.get_text() if a else heading_tag.get_text()
    return ' '.join(text.split())


def tag_to_html(tag, outer=True):
    """Convert a Tag to HTML string.

    If outer=True (default), includes the tag wrapper (e.g. <p>text</p>).
    If outer=False, returns only inner content (e.g. text).
    """
    if isinstance(tag, Tag):
        html = str(tag) if outer else tag.decode_contents().strip()
    else:
        html = str(tag).strip() if tag else ''
    html = html.replace('\u2014', '&mdash;')
    html = html.replace('\u2013', '&ndash;')
    html = html.replace('\u2018', '&lsquo;')
    html = html.replace('\u2019', '&rsquo;')
    html = html.replace('\u201c', '&ldquo;')
    html = html.replace('\u201d', '&rdquo;')
    html = html.replace('\u2026', '&hellip;')
    return html


def wrap_html(body_html, title='', extra_head='', css_path='sep-style.css'):
    """Wrap body HTML in a full XHTML document."""
    return f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{escape_html(title) if title else ''}</title>
<link rel="stylesheet" type="text/css" href="{css_path}" />
{extra_head}
</head>
<body>
{body_html}
</body>
</html>'''


def make_heading_html(level, text, anchor_id=''):
    """Generate HTML for a heading with optional id anchor."""
    id_attr = f' id="{anchor_id}"' if anchor_id else ''
    return f'<h{level}{id_attr}>{escape_html(text)}</h{level}>'


# ─── Content Building ────────────────────────────────────────────

def build_chapter_html(section):
    """Build the HTML body content for a single h2 section."""
    parts = []
    parts.append(make_heading_html(2, section['heading'], section['id']))
    if section['content_html']:
        parts.append(section['content_html'])
    for sub in section['subsections']:
        parts.append(make_heading_html(sub['level'], sub['heading'], sub['id']))
        if sub['content_html']:
            parts.append(sub['content_html'])
    return '\n'.join(parts)


def build_entry_landing_html(entry):
    """Build the entry landing page HTML (title + source URL + pubinfo + preamble)."""
    parts = []
    parts.append(f'<h1>{escape_html(entry["title"])}</h1>')
    parts.append(
        f'<p class="source-url">Source: <a href="{entry["url"]}">{escape_html(entry["url"])}</a></p>'
    )
    if entry['pubinfo']:
        parts.append(f'<div class="pubinfo">{entry["pubinfo"]}</div>')
    if entry['preamble_html']:
        parts.append(f'<div class="preamble">{entry["preamble_html"]}</div>')
    return '\n'.join(parts)


# ─── Parsing ──────────────────────────────────────────────────────

def parse_entry(html_text, url, embed_mode=None, entry_index=0):
    """
    Parse a SEP entry's HTML into structured data.

    embed_mode controls image embedding:
        None       — leave <img> src as-is
        'data-uri' — replace src with base64 data URIs (for PDF)
        'epub'     — assign EpubItem filenames, returns image list (for EPUB)

    entry_index is used as prefix for EpubItem filenames to avoid collisions
    when multiple entries share the same EPUB.

    Returns a dict with keys:
        title, url, pubinfo, preamble_html, sections, images
    where each section has: heading, id, level, content_html, subsections
    """
    soup = BeautifulSoup(html_text, 'lxml')
    aueditable = soup.select_one('#aueditable')
    if not aueditable:
        raise ValueError('Could not find #aueditable div in the page; is this a valid SEP entry?')
    copyright_block = soup.select_one('#article-copyright')
    if copyright_block and not aueditable.select_one('#article-copyright'):
        aueditable.append(copyright_block.extract())
    for node in aueditable.select('script[type^="math/tex"]'):
        opening, closing = ('\\[', '\\]') if 'mode=display' in node.get('type', '') else ('\\(', '\\)')
        node.replace_with(NavigableString(opening + node.get_text() + closing))
    for node in aueditable.select('script,style,form'):
        node.decompose()

    result = {
        'title': '',
        'url': url,
        'pubinfo': '',
        'preamble_html': '',
        'sections': [],
        'images': [],
    }

    # Remove TOC from the DOM
    toc_div = aueditable.select_one('#toc')
    if toc_div:
        toc_div.decompose()

    # Extract title
    h1 = aueditable.find('h1')
    if h1:
        result['title'] = h1.get_text(strip=True)

    # Extract pubinfo
    pubinfo = aueditable.select_one('#pubinfo')
    if pubinfo:
        result['pubinfo'] = tag_to_html(pubinfo, outer=False)

    # Flatten content
    flat = _flatten_content(aueditable)

    # Group into sections
    preamble_blocks = []
    current_section = None
    current_sub = None
    in_preamble = True

    for el in flat:
        tag = el.name

        if tag == 'h1':
            continue

        if tag == 'h2':
            in_preamble = False
            current_section = {
                'heading': clean_heading_text(el),
                'id': get_heading_id(el),
                'level': 2,
                'content_html': '',
                'subsections': [],
            }
            result['sections'].append(current_section)
            current_sub = None
            continue

        if in_preamble:
            preamble_blocks.append(el)
            continue

        if tag in ('h3', 'h4', 'h5', 'h6'):
            current_sub = {
                'heading': clean_heading_text(el),
                'id': get_heading_id(el),
                'level': int(tag[1]),
                'content_html': '',
            }
            if current_section is not None:
                current_section['subsections'].append(current_sub)
            continue

        # Regular content block → convert to HTML
        html = tag_to_html(el)
        if current_sub is not None:
            current_sub['content_html'] += html + '\n'
        elif current_section is not None:
            current_section['content_html'] += html + '\n'
        else:
            preamble_blocks.append(el)

    preamble_html = '\n'.join(tag_to_html(b) for b in preamble_blocks)
    result['preamble_html'] = preamble_html

    # Optionally embed images
    if embed_mode:
        all_images = []
        img_counter = [0]

        def _process_html(html_str):
            nonlocal all_images, img_counter
            if embed_mode == 'data-uri':
                return embed_images_in_html(html_str, url)
            elif embed_mode == 'epub':
                prefix = f'e{entry_index}'
                updated, imgs = embed_images_epub(
                    html_str, url, prefix=prefix, start_counter=img_counter[0]
                )
                img_counter[0] += len(imgs)
                all_images.extend(imgs)
                return updated
            return html_str

        result['preamble_html'] = _process_html(result['preamble_html'])
        result['pubinfo'] = _process_html(result['pubinfo'])
        for sec in result['sections']:
            sec['content_html'] = _process_html(sec['content_html'])
            for sub in sec['subsections']:
                sub['content_html'] = _process_html(sub['content_html'])

        if embed_mode == 'epub':
            result['images'] = all_images

    return result


def _flatten_content(root):
    """
    Recursively walk through #aueditable children, flattening container
    divs into a single ordered list of block-level elements.
    """
    result = []
    for child in root.children:
        if not isinstance(child, Tag):
            continue
        tag = child.name
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol',
                   'blockquote', 'hr', 'table', 'pre', 'dl', 'img', 'figure'):
            result.append(child)
        elif tag in ('div', 'section', 'article'):
            result.extend(_flatten_content(child))
    return result
