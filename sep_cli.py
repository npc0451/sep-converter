#!/usr/bin/env python3
"""
sep_cli.py — Interactive CLI for SEP → EPUB/PDF conversion.
"""

import sys
import os

from sep_app import convert


def run_cli():
    """Run the interactive CLI wizard."""
    _print_banner()

    # ── Collect URLs ──
    urls = []
    print('Enter entry URLs (one per line, empty line to finish):')
    while True:
        try:
            line = input(f'  {len(urls)+1}> ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            break
        urls.append(line)

    if not urls:
        print('No URLs entered. Exiting.')
        return

    # ── Format ──
    fmt = _prompt_choice('Format', ['epub', 'pdf', 'txt'], default='pdf')

    # ── Embed images ──
    embed = False if fmt == 'txt' else _prompt_yesno('Embed images', default=True)

    # ── Output mode ──
    mode_opts = ['separate', 'merge']
    mode = _prompt_choice('Output mode', mode_opts, default='separate',
                          labels=['one file per entry', 'merge all into one'])

    # ── Output dir ──
    out_dir = input(f'Output directory [.] ').strip() or '.'

    # ── Filename (merge only) ──
    output_name = None
    if mode == 'merge':
        name_raw = input('Filename (blank for auto): ').strip()
        output_name = name_raw if name_raw else None

    # ── Summary ──
    print()
    _print_sep()
    print(f'  URLs:     {len(urls)}')
    print(f'  Format:   {fmt.upper()}{" (images embedded)" if embed else ""}')
    if mode == 'merge':
        name_display = output_name or '(auto)'
        print(f'  Mode:     merge → {os.path.join(out_dir, name_display)}.{fmt}')
    else:
        print(f'  Mode:     separate → {out_dir}/')
    _print_sep()
    proceed = _prompt_yesno('Proceed', default=True)
    if not proceed:
        print('Cancelled.')
        return

    # ── Run ──
    config = {
        'urls': urls,
        'format': fmt,
        'embed_images': embed,
        'output_mode': mode,
        'output_name': output_name,
        'output_dir': out_dir,
        'on_status': lambda m: print(f'  {m}'),
    }
    try:
        paths = convert(config)
        print(f'\nSuccessfully generated {len(paths)} file(s):')
        for p in paths:
            sz = os.path.getsize(p)
            print(f'  {p}  ({sz/1024:.1f} KB)')
    except Exception as e:
        print(f'\nERROR: {e}')
        sys.exit(1)


# ─── Helpers ──────────────────────────────────────────────────────

def _print_banner():
    print()
    print('=' * 48)
    print('  Stanford Encyclopedia → EPUB / PDF Converter')
    print('=' * 48)
    print()


def _print_sep():
    print('─' * 48)


def _prompt_choice(label, options, default=None, labels=None):
    """Prompt user to pick from a numbered list."""
    print(f'\n{label}:')
    for i, opt in enumerate(options, 1):
        lbl = labels[i-1] if labels else opt
        marker = ' (default)' if opt == default else ''
        print(f'  [{i}] {lbl}{marker}')
    while True:
        raw = input(f'Choice (1-{len(options)}) [{options.index(default)+1 if default else 1}]: ').strip()
        if not raw and default is not None:
            return default
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            pass
        print(f'  Please enter a number 1-{len(options)}.')


def _prompt_yesno(label, default=True):
    """Prompt yes/no."""
    hint = 'Y/n' if default else 'y/N'
    raw = input(f'{label}? ({hint}) ').strip().lower()
    if not raw:
        return default
    return raw[0] == 'y'


if __name__ == '__main__':
    run_cli()
