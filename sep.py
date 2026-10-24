#!/usr/bin/env python3
"""
sep.py — Unified entry point for SEP → EPUB/PDF conversion.

Usage:
  python sep.py                          # Launch GUI (fallback to interactive CLI)
  python sep.py --cli                    # Force interactive CLI
  python sep.py URL [URL ...] [options]  # Direct conversion (argparse mode)

Options (argparse mode):
  -f, --format FORMAT       epub | pdf | txt (default: pdf)
  -o, --output PATH         Output file path (merge mode) or directory
  --embed-images            Embed images in EPUB
  --no-embed-images         Skip image embedding
  -m, --mode MODE           separate | merge (default: separate)
  --name NAME               Custom filename (merge mode only)
"""

import sys
import os
import argparse


def _run_gui():
    """Try to start the GUI; returns True on success."""
    try:
        from sep_gui import run_gui
        run_gui()
        return True
    except Exception as e:
        print(f'无法启动图形界面：{e}', file=sys.stderr)
        return False


def _run_cli_interactive():
    """Start the interactive CLI wizard."""
    from sep_cli import run_cli
    run_cli()


def _run_argparse():
    """Parse command-line arguments and run conversion directly."""
    parser = argparse.ArgumentParser(
        description='Convert Stanford Encyclopedia of Philosophy entries.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('urls', nargs='+', help='SEP entry URL(s)')
    parser.add_argument('-f', '--format', choices=['epub', 'pdf', 'txt'],
                        default='pdf', help='Output format (default: pdf)')
    parser.add_argument('-o', '--output', help='Output path or directory')
    parser.add_argument('--embed-images', action='store_true',
                        help='Embed images in output')
    parser.add_argument('--no-embed-images', action='store_true',
                        help='Skip image embedding')
    parser.add_argument('-m', '--mode', choices=['separate', 'merge'],
                        default='separate',
                        help='Output mode (default: separate)')
    parser.add_argument('--name', help='Custom filename (merge mode only)')

    args = parser.parse_args()

    # Resolve embed_images (--embed-images wins, else --no-embed-images, else default)
    embed = not args.no_embed_images
    if args.embed_images:
        embed = True

    # Build config
    config = {
        'urls': args.urls,
        'format': args.format,
        'embed_images': embed,
        'output_mode': args.mode,
        'output_name': args.name if args.mode == 'merge' else None,
        'output_dir': args.output or '.',
        'on_status': lambda m: print(f'  {m}'),
    }

    from sep_app import convert
    try:
        paths = convert(config)
        print(f'\nDone: {len(paths)} file(s) generated')
        for p in paths:
            sz = os.path.getsize(p)
            print(f'  {p}  ({sz/1024:.1f} KB)')
    except Exception as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)


def main():
    # No arguments → interactive mode (GUI preferred, CLI fallback)
    if len(sys.argv) == 1:
        if not _run_gui():
            _run_cli_interactive()
        return

    # --cli flag → force interactive CLI
    if '--cli' in sys.argv:
        sys.argv.remove('--cli')
        _run_cli_interactive()
        return

    # --gui flag → force GUI
    if '--gui' in sys.argv:
        sys.argv.remove('--gui')
        if not _run_gui():
            print('GUI not available, falling back to CLI.', file=sys.stderr)
            _run_cli_interactive()
        return

    # Has arguments → argparse mode
    _run_argparse()


if __name__ == '__main__':
    main()
