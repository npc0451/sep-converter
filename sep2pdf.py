#!/usr/bin/env python3
"""
sep2pdf.py — Convert Stanford Encyclopedia of Philosophy entries to PDF.

Usage:
  python sep2pdf.py URL [URL ...] [-o OUTPUT] [--no-embed-images]

Examples:
  python sep2pdf.py https://plato.stanford.edu/entries/lacan/
  python sep2pdf.py URL1 URL2 -o combined.pdf
"""

import sys
import os
import argparse
import io
import tempfile
from bs4 import BeautifulSoup

from sep_common import (
    fetch_html, parse_entry, url_to_slug, slugify,
    build_entry_landing_html, build_chapter_html
)


# ─── PDF CSS (complete standalone stylesheet for readable layout) ─

PDF_CSS = '''
@page {
    size: A4;
    margin: 2.8cm 2.5cm;
}

body {
    font-family: Georgia, "Times New Roman", serif;
    font-size: 11pt;
    line-height: 2.1;
    text-align: justify;
    color: #333;
    widows: 3;
    orphans: 3;
}

h1, h2, h3, h4, h5, h6 {
    font-family: "Source Sans Pro", "Helvetica Neue", Arial, sans-serif;
    font-weight: 600;
    color: #8C1515;
    page-break-after: avoid;
}
h1 {
    font-size: 22pt;
    margin: 0 0 0.6em 0;
    border-bottom: 1px solid #ccc;
    padding-bottom: 0.3em;
    page-break-before: always;
}
h2 {
    font-size: 16pt;
    margin: 0.3em 0 0.5em 0;
    border-bottom: 1px solid #eee;
    padding-bottom: 0.2em;
    page-break-before: always;
}
h3 {
    font-size: 13pt;
    margin: 1.2em 0 0.5em 0;
    color: #555;
}
h4 {
    font-size: 11pt;
    margin: 1em 0 0.5em 0;
    color: #666;
    font-weight: 600;
}

p {
    margin: 0 0 0.4em 0;
    text-indent: 0;
}
em, i { font-style: italic; }
strong, b { font-weight: bold; }
a { color: #8C1515; text-decoration: none; }

blockquote {
    margin: 0.6em 1.5em;
    padding: 0.5em 1em;
    border-left: 3px solid #8C1515;
    color: #555;
    font-style: italic;
    font-size: 0.95em;
}

ul, ol { margin: 0.2em 0 0.5em 1.8em; padding: 0; }
li { margin-bottom: 0.2em; }

hr {
    border: none;
    border-top: 1px solid #ccc;
    margin: 1.5em 0;
}

table { border-collapse: collapse; margin: 0.8em 0; }
td, th {
    padding: 0.3em 0.6em;
    border: 1px solid #ccc;
    vertical-align: top;
}

.pubinfo { font-style: italic; color: #666; font-size: 0.9em; margin-bottom: 1.2em; }
.source-url { font-size: 0.85em; margin-bottom: 1.5em; word-break: break-all; }
.source-url a { color: #555; }
.entry-separator { border: none; border-top: 2px solid #8C1515; margin: 2em 0; }

.bibliography ul.hanging, ul.hanging {
    list-style: none; margin-left: 0; padding-left: 0;
}
.bibliography ul.hanging li, ul.hanging li {
    text-indent: -2em; padding-left: 4em; margin-bottom: 0.6em;
}
.suggestions { font-style: italic; color: #555; margin: 1em 0; }
.academic-tools table { border: none; }
.academic-tools td { border: none; padding: 0.3em 0.5em; }
.preamble { margin-bottom: 1.5em; }
img { max-width: 100%; height: auto; }
'''


# ─── Font / Resource directory resolution ─────────────────────────

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def _resolve_font_dir():
    candidates = [
        os.path.join(_SCRIPT_DIR, 'fonts'),
        os.path.join(os.getcwd(), 'fonts'),
    ]
    for d in candidates:
        if os.path.isdir(d):
            return d
    return candidates[0]


def _register_fonts(font_dir):
    """Register TTF fonts with ReportLab so xhtml2pdf's CSS font-family resolves."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if not font_dir or not os.path.isdir(font_dir):
        return 0

    variants = [
        ('SourceSansPro',         400, 'normal', 'normal-400'),
        ('SourceSansPro-Italic',  400, 'italic',  'italic-400'),
        ('SourceSansPro-Bold',    700, 'normal', 'normal-700'),
        ('SourceSansPro-BoldItalic', 700, 'italic', 'italic-700'),
        ('SourceSansPro-Light',   300, 'normal', 'normal-300'),
        ('SourceSansPro-LightItalic', 300, 'italic', 'italic-300'),
        ('SourceSansPro-Semibold',   600, 'normal', 'normal-600'),
        ('SourceSansPro-SemiboldItalic', 600, 'italic', 'italic-600'),
    ]

    n = 0
    for rl_name, weight, style, suffix in variants:
        fname = f'SourceSansPro-{suffix}.ttf'
        fpath = os.path.join(font_dir, fname)
        if os.path.exists(fpath):
            try:
                pdfmetrics.registerFont(TTFont(rl_name, fpath))
                n += 1
            except Exception:
                pass

    return n


# ─── PDF Generation ───────────────────────────────────────────────

def build_pdf_html(entries):
    """Build a single HTML document string for all entries."""
    css_text = PDF_CSS

    parts = []
    parts.append('''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>''' + _get_title(entries) + '''</title>
<style>
''' + css_text + '''
</style>
</head>
<body>
''')

    for ei, entry in enumerate(entries):
        if ei > 0:
            parts.append('<hr class="entry-separator" />\n')
        parts.append(build_entry_landing_html(entry))
        parts.append('\n')
        for section in entry['sections']:
            parts.append(build_chapter_html(section))
            parts.append('\n')

    parts.append('</body>\n</html>')
    return '\n'.join(parts)


def _get_title(entries):
    if len(entries) == 1:
        return entries[0]['title']
    return f'Stanford Encyclopedia of Philosophy ({len(entries)} entries)'


def generate_pdf(entries, output_path, font_dir=None):
    """Generate a PDF file from parsed entries using xhtml2pdf."""
    from xhtml2pdf import pisa

    fd = font_dir or _resolve_font_dir()
    if os.path.isdir(fd):
        registered = _register_fonts(fd)
        if registered:
            print(f'  Registered {registered} font variants', file=sys.stderr)

    html_str = build_pdf_html(entries)
    soup = BeautifulSoup(html_str, 'lxml')
    for image in soup.select('img'):
        if not image.get('src', '').startswith('data:'):
            replacement = soup.new_tag('p')
            replacement.string = '[Image not embedded: ' + image.get('alt', image.get('src', 'unavailable')) + ']'
            image.replace_with(replacement)
    html_str = str(soup)

    def local_resource(uri, relative):
        if not uri.startswith('data:'):
            raise ValueError('PDF rendering cannot fetch external resources: ' + uri)
        return uri

    result = io.BytesIO()
    pdf = pisa.CreatePDF(
        io.BytesIO(html_str.encode('utf-8')),
        dest=result,
        encoding='utf-8',
        link_callback=local_resource,
    )

    if pdf.err:
        msg = f'PDF generation had errors (err={pdf.err})'
        if hasattr(pdf, 'error') and pdf.error:
            msg += f': {pdf.error}'
        raise RuntimeError(msg)

    directory = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.sep-pdf-', suffix='.part', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(result.getvalue())
        os.replace(temporary, output_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

    return output_path


# ─── CLI ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Convert Stanford Encyclopedia of Philosophy entries to PDF.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('urls', nargs='+', help='SEP entry URL(s)')
    parser.add_argument('-o', '--output', help='Output PDF file path')
    parser.add_argument('--no-embed-images', action='store_true',
                        help='Skip downloading and embedding images')

    args = parser.parse_args()

    # PDF always uses data-uri embedding by default
    embed_mode = None if args.no_embed_images else 'data-uri'

    entries = []
    for url in args.urls:
        print(f'Fetching: {url} ...', file=sys.stderr)
        try:
            html = fetch_html(url)
        except Exception as e:
            print(f'  ERROR fetching {url}: {e}', file=sys.stderr)
            continue

        label = 'data-uri' if embed_mode == 'data-uri' else 'no'
        print(f'  Parsing (embed={label})...', file=sys.stderr)
        try:
            entry = parse_entry(html, url, embed_mode=embed_mode, entry_index=len(entries))
        except ValueError as e:
            print(f'  ERROR parsing {url}: {e}', file=sys.stderr)
            continue

        if not entry['title']:
            entry['title'] = url_to_slug(url).replace('-', ' ').title()

        print(f'  Title: {entry["title"]}', file=sys.stderr)
        sec_count = len(entry['sections'])
        sub_count = sum(len(s['subsections']) for s in entry['sections'])
        print(f'  Sections: {sec_count} (+ {sub_count} subsections)', file=sys.stderr)
        entries.append(entry)

    if not entries:
        print('No entries successfully parsed. Exiting.', file=sys.stderr)
        sys.exit(1)

    if args.output:
        output = args.output
    elif len(entries) == 1:
        output = f'{url_to_slug(entries[0]["url"])}.pdf'
    else:
        output = 'sep-multiple.pdf'

    print(f'Generating PDF: {output} ...', file=sys.stderr)

    font_dir = _resolve_font_dir()
    if os.path.isdir(font_dir):
        ttf_count = sum(1 for f in os.listdir(font_dir) if f.endswith('.ttf'))
        print(f'  Fonts available: {ttf_count} TTF files', file=sys.stderr)

    try:
        result = generate_pdf(entries, output, font_dir=font_dir)
        print(f'Done: {result}', file=sys.stderr)
        print(result)
    except Exception as e:
        print(f'ERROR generating PDF: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
