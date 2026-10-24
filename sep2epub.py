#!/usr/bin/env python3
"""
sep2epub.py — Convert Stanford Encyclopedia of Philosophy entries to EPUB.

Usage:
  python sep2epub.py URL [URL ...] [-o OUTPUT] [--embed-images]

Examples:
  python sep2epub.py https://plato.stanford.edu/entries/lacan/
  python sep2epub.py --embed-images https://plato.stanford.edu/entries/descartes/
  python sep2epub.py URL1 URL2 -o combined.epub
"""

import sys
import os
import argparse
import tempfile

from ebooklib import epub

from sep_common import (
    fetch_html, parse_entry, url_to_slug, slugify,
    make_css, wrap_html, build_entry_landing_html, build_chapter_html
)


# ─── EPUB Generation ──────────────────────────────────────────────

def generate_epub(entries, output_path):
    """Generate an EPUB file from a list of parsed entries."""
    book = epub.EpubBook()

    # Metadata
    if len(entries) == 1:
        title = entries[0]['title']
        book.set_identifier(f'sep-{slugify(entries[0]["title"])}')
    else:
        title = f'Stanford Encyclopedia of Philosophy ({len(entries)} entries)'
        book.set_identifier(f'sep-multiple-{os.urandom(4).hex()}')

    book.set_title(title)
    book.set_language('en')

    # Add CSS
    css_text = make_css(for_epub=True, font_dir=None)
    style_item = epub.EpubItem(
        uid='sep-style',
        file_name='sep-style.css',
        media_type='text/css',
        content=css_text
    )
    book.add_item(style_item)

    # Add images (EpubItems) before chapters
    for ei, entry in enumerate(entries):
        for img in entry.get('images', []):
            img_item = epub.EpubItem(
                uid=f'img_{ei}_{os.path.basename(img["filename"])}',
                file_name=img['filename'],
                media_type=img['media_type'],
                content=img['data'],
            )
            book.add_item(img_item)

    # Build chapters for each entry
    all_chapters = []
    all_chapter_data = []

    total_entries = len(entries)
    for ei, entry in enumerate(entries):
        entry_chapters = _build_entry_chapters(entry, ei, total_entries)
        all_chapter_data.extend(entry_chapters)

        for filename, chap_title, body in entry_chapters:
            full_html = wrap_html(body, title=chap_title)
            chap = epub.EpubHtml(
                title=chap_title,
                file_name=filename,
                lang='en'
            )
            chap.content = full_html.encode('utf-8')
            chap.add_item(style_item)
            book.add_item(chap)
            all_chapters.append(chap)

    # Build TOC
    toc = []
    chapter_offset = 0
    for ei, entry in enumerate(entries):
        entry_chs = all_chapter_data[chapter_offset:chapter_offset + len(_build_entry_chapters(entry, ei, total_entries))]
        chapter_offset += len(entry_chs)

        links = []
        for idx, (fname, ctitle, _) in enumerate(entry_chs[1:], 1):
            links.append(epub.Link(fname, ctitle, f'e{ei:02d}s{idx:02d}'))

        landing_filename = entry_chs[0][0]
        entry_section = epub.Section(entry['title'], href=landing_filename)
        if links:
            toc.append((entry_section, links))
        else:
            toc.append(entry_section)

    book.toc = toc

    # Navigation
    book.add_item(epub.EpubNav())
    book.add_item(epub.EpubNcx())

    # Spine
    book.spine = ['nav'] + all_chapters

    directory = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.sep-epub-', suffix='.part', dir=directory)
    os.close(fd)
    try:
        epub.write_epub(temporary, book, {})
        os.replace(temporary, output_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return output_path


def _build_entry_chapters(entry, entry_index, total_entries):
    """
    Build all chapter content for a single entry.

    Returns a list of (filename, title, html_body) tuples.
    First item is the entry landing page.
    """
    slug = slugify(entry['title'], 40) or f'entry-{entry_index:02d}'
    if total_entries > 1:
        slug = f'e{entry_index:03d}-' + slug
    chapters = []

    landing_html = build_entry_landing_html(entry)
    landing_filename = f'{slug}_index.xhtml'
    chapters.append((landing_filename, entry['title'], landing_html))

    for sec_idx, section in enumerate(entry['sections']):
        sec_slug = slugify(section['heading'], 40)
        filename = f'{slug}_{sec_idx:02d}_{sec_slug}.xhtml'
        body = build_chapter_html(section)
        chapters.append((filename, section['heading'], body))

    return chapters


# ─── CLI ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Convert Stanford Encyclopedia of Philosophy entries to EPUB.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('urls', nargs='+', help='SEP entry URL(s)')
    parser.add_argument('-o', '--output', help='Output EPUB file path')
    parser.add_argument('--embed-images', action='store_true',
                        help='Download and embed images in the EPUB')
    parser.add_argument('--no-embed-images', action='store_true',
                        help='Explicitly skip image embedding')

    args = parser.parse_args()

    # Determine embed mode: prefer --embed-images, fall back to --no-embed-images
    embed_mode = None
    if args.embed_images:
        embed_mode = 'epub'
    elif args.no_embed_images:
        embed_mode = None
    # Default: no embedding (preserve existing behavior)

    entries = _fetch_all(args.urls, embed_mode=embed_mode)
    if not entries:
        sys.exit(1)

    if args.output:
        output = args.output
    elif len(entries) == 1:
        output = f'{url_to_slug(entries[0]["url"])}.epub'
    else:
        output = 'sep-multiple.epub'

    print(f'Generating EPUB: {output} ...', file=sys.stderr)
    result = generate_epub(entries, output)
    print(f'Done: {result}', file=sys.stderr)
    print(result)


def _fetch_all(urls, embed_mode=None):
    """Fetch and parse multiple URLs, returning list of entry dicts."""
    entries = []
    for idx, url in enumerate(urls):
        print(f'Fetching: {url} ...', file=sys.stderr)
        try:
            html = fetch_html(url)
        except Exception as e:
            print(f'  ERROR fetching {url}: {e}', file=sys.stderr)
            continue

        label = 'epub' if embed_mode == 'epub' else ('data-uri' if embed_mode else 'no')
        print(f'  Parsing (embed={label})...', file=sys.stderr)
        try:
            entry = parse_entry(html, url, embed_mode=embed_mode, entry_index=idx)
        except ValueError as e:
            print(f'  ERROR parsing {url}: {e}', file=sys.stderr)
            continue

        if not entry['title']:
            entry['title'] = url_to_slug(url).replace('-', ' ').title()

        img_count = len(entry.get('images', []))
        print(f'  Title: {entry["title"]}', file=sys.stderr)
        print(f'  Sections: {len(entry["sections"])}', file=sys.stderr)
        if img_count:
            print(f'  Images embedded: {img_count}', file=sys.stderr)
        entries.append(entry)

    if not entries:
        print('No entries successfully parsed. Exiting.', file=sys.stderr)
    return entries


if __name__ == '__main__':
    main()
