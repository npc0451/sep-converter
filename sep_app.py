#!/usr/bin/env python3
"""
sep_app.py — Application orchestrator for SEP → EPUB/PDF conversion.

Orchestrates fetching, parsing, and generating output files.
Frontends (CLI, GUI) call convert(config) — this is the only entry point they need.
"""

import os
import sys
from html import escape as escape_html

from sep_common import (
    fetch_html, parse_entry, url_to_slug, slugify,
    build_entry_landing_html, build_chapter_html
)
from sep2epub import generate_epub
from sep2pdf import generate_pdf
from sep2txt import generate_txt


# ─── File naming ──────────────────────────────────────────────────

def _resolve_output_dir(config):
    """Return output directory, creating it if necessary."""
    out_dir = config.get('output_dir', '.')
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def _pick_filenames(entries, config):
    """
    Determine output file path(s) based on config.

    config keys used:
        output_mode — 'separate' (default) or 'merge'
        output_name — str or None (merge mode only; None → auto name)
        output_dir  — str, default '.'
        format      — 'epub' or 'pdf'

    Returns:
        separate mode → [(entry, path), ...]
        merge mode    → [path]  (single path, entries accessible globally)
    """
    ext = config['format']
    out_dir = _resolve_output_dir(config)
    mode = config.get('output_mode', 'separate')

    if mode == 'merge':
        name = config.get('output_name') or f'sep-{len(entries)}_entries'
        path = os.path.join(out_dir, f'{name}.{ext}')
        return [path]  # single output for all entries

    # separate: one file per entry
    paths, used = [], set()
    for entry in entries:
        title_slug = slugify(entry['title'], 50) or url_to_slug(entry['url'])
        path = os.path.join(out_dir, f'{title_slug}.{ext}')
        suffix = 2
        while path in used:
            path = os.path.join(out_dir, f'{title_slug}-{suffix}.{ext}')
            suffix += 1
        used.add(path)
        paths.append(path)
    return paths


# ─── Orchestration ────────────────────────────────────────────────

def convert(config):
    """
    Run the full conversion pipeline.

    config dict:
        urls         — list[str], required
        format       — 'epub' or 'pdf', required
        embed_images — bool, default True
        output_mode  — 'separate' or 'merge', default 'separate'
        output_name  — str or None (merge mode only)
        output_dir   — str, default '.'
        on_status    — callable(msg), optional progress callback

    Returns list of output file paths (one per generated file).
    """
    urls = list(dict.fromkeys(config['urls']))
    fmt = config['format']
    embed = config.get('embed_images', True)
    mode = config.get('output_mode', 'separate')
    on_status = config.get('on_status', lambda m: None)

    if not urls:
        raise ValueError('No URLs provided')
    if fmt not in ('epub', 'pdf', 'txt') or mode not in ('separate', 'merge'):
        raise ValueError('不支持的格式或输出模式')
    from sep_network import validate_url
    for url in urls:
        validate_url(url)
    if config.get('output_name') and os.path.basename(config['output_name']) != config['output_name']:
        raise ValueError('Filename must not contain a directory path')

    # 1. Fetch + parse all entries
    embed_mode = _resolve_embed_mode(fmt, embed)
    entries = []
    for idx, url in enumerate(urls):
        on_status(f'抓取网页：{url}  （{idx+1}/{len(urls)}）')
        try:
            html = fetch_html(url)
        except Exception as e:
            on_status(f'  抓取失败：{e}')
            continue

        try:
            entry = parse_entry(html, url, embed_mode=embed_mode, entry_index=idx)
        except ValueError as e:
            on_status(f'  解析失败：{e}')
            continue

        if not entry['title']:
            entry['title'] = url_to_slug(url).replace('-', ' ').title()

        img_n = len(entry.get('images', []))
        sec_n = len(entry['sections'])
        on_status(f'  标题：{entry["title"]}  （{sec_n} 个章节'
                  f'{f"，{img_n} 张图片" if img_n else ""}）')
        entries.append(entry)

    if not entries:
        raise RuntimeError('没有成功解析的词条，请检查链接和上方错误')

    # 2. Determine output paths
    filenames = _pick_filenames(entries, config)

    # 3. Generate
    if mode == 'merge':
        out_path = filenames[0]
        on_status(f'生成 {fmt.upper()}：{os.path.basename(out_path)} ...')
        if fmt == 'epub':
            generate_epub(entries, out_path)
        elif fmt == 'pdf':
            generate_pdf(entries, out_path)
        else:
            generate_txt(entries, out_path)
        on_status(f'完成：{out_path}')
        return [out_path]
    else:
        for entry, out_path in zip(entries, filenames):
            on_status(f'生成 {fmt.upper()}：{os.path.basename(out_path)} ...')
            if fmt == 'epub':
                generate_epub([entry], out_path)
            elif fmt == 'pdf':
                generate_pdf([entry], out_path)
            else:
                generate_txt([entry], out_path)
            on_status(f'完成：{out_path}')
        return filenames


def _resolve_embed_mode(fmt, embed):
    """Map (format, bool) to embed_mode string expected by parse_entry."""
    if not embed or fmt == 'txt':
        return None
    return 'data-uri' if fmt == 'pdf' else 'epub'
