import base64
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from pypdf import PdfReader
import requests

import sep_network
from sep_app import convert, _pick_filenames
from sep_common import parse_entry, embed_images_in_html
from sep2epub import generate_epub
from sep2pdf import generate_pdf

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
URL = 'https://plato.stanford.edu/entries/test/'
HTML = '''<!doctype html><html><head><meta charset="utf-8"></head><body>
<div id="aueditable"><h1>Example Philosophy</h1><div id="pubinfo">Published 2026</div>
<div id="preamble"><p>Introduction with Unicode: café, 孔子, α.</p></div>
<div id="main-text"><h2 id="first">Test section</h2><p>Body text for testing.</p>
<img alt="Test diagram" width="80" height="80" src="diagram.png"/>
<table><tr><th>Concept</th><th>Value</th></tr><tr><td>Knowledge</td><td>True</td></tr></table>
</div></div></body></html>'''


def response(url, data=b'', status=200, headers=None):
    r = requests.Response()
    r.url, r.status_code, r._content = url, status, data
    r.headers.update(headers or {})
    return r


class ConverterTests(unittest.TestCase):
    def test_pdf_and_epub_embed_images_tables_and_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            for fmt in ('pdf', 'epub'):
                events = []
                with patch('sep_app.fetch_html', return_value=HTML), patch('sep_common.fetch_image', return_value=(PNG, 'image/png')), patch('requests.get', side_effect=AssertionError('rendering must not fetch')):
                    paths = convert({'urls': [URL, URL + 'second/'], 'format': fmt, 'output_mode': 'merge', 'output_name': 'combined', 'output_dir': directory, 'on_status': events.append})
                self.assertEqual(len(paths), 1)
                path = Path(paths[0])
                if fmt == 'pdf':
                    reader = PdfReader(path)
                    text = '\n'.join(page.extract_text() for page in reader.pages)
                    self.assertEqual(text.count('Example Philosophy'), 2)
                    self.assertIn('Knowledge', text)
                    self.assertTrue(any(len(page.images) for page in reader.pages))
                else:
                    with zipfile.ZipFile(path) as archive:
                        names = archive.namelist()
                        self.assertEqual(len(names), len(set(names)))
                        self.assertEqual(len([n for n in names if n.endswith('.png')]), 2)
                        chapters = b' '.join(archive.read(n) for n in names if n.endswith('.xhtml'))
                        self.assertIn(b'<table', chapters)
                        self.assertIn('孔子'.encode(), chapters)
                self.assertTrue(any('生成' in m for m in events))

    def test_txt_unicode_tables_math_sources_and_no_image_download(self):
        html = HTML.replace('</div></div>', r'<p>Inline formula: <script type="math/tex">a^2+b^2=c^2</script></p><p>Display: \[x=y\]</p></div></div>')
        with tempfile.TemporaryDirectory() as directory, patch('sep_app.fetch_html', return_value=html), patch('sep_common.fetch_image', side_effect=AssertionError('TXT must not download images')):
            for mode in ('merge', 'separate'):
                paths = convert({'urls': [URL, URL + 'second/'], 'format': 'txt', 'embed_images': True, 'output_mode': mode, 'output_dir': directory})
                self.assertEqual(len(paths), 1 if mode == 'merge' else 2)
                for path in paths:
                    text = Path(path).read_text(encoding='utf-8')
                    for expected in ['孔子', 'α', 'Test section', 'Knowledge\tTrue', '[图片：Test diagram', '来源：', r'\(a^2+b^2=c^2\)', r'\[x=y\]']:
                        self.assertIn(expected, text)
                    self.assertNotIn('<table', text)

    def test_pdf_error_does_not_overwrite_previous_output(self):
        entry = parse_entry(HTML, URL)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'previous.pdf'
            path.write_bytes(b'previous successful file')
            with patch('xhtml2pdf.pisa.CreatePDF', return_value=SimpleNamespace(err=1, error='failed')):
                with self.assertRaises(RuntimeError):
                    generate_pdf([entry], path)
            self.assertEqual(path.read_bytes(), b'previous successful file')

    def test_no_embed_pdf_does_not_fetch_images(self):
        entry = parse_entry(HTML, URL)
        with tempfile.TemporaryDirectory() as directory, patch('requests.get', side_effect=AssertionError('network forbidden')):
            path = Path(directory) / 'no-images.pdf'
            generate_pdf([entry], path)
            text = '\n'.join(p.extract_text() for p in PdfReader(path).pages)
            self.assertIn('Image not embedded', text)

    def test_image_attributes_and_missing_images(self):
        with patch('sep_common.fetch_image', return_value=(PNG, 'image/png')):
            html = embed_images_in_html('<img alt="Keep this description" width="80" src="x.png"/>', URL)
        self.assertIn('alt="Keep this description"', html)
        self.assertIn('width="80"', html)
        self.assertIn('data:image/png;base64,', html)
        with patch('sep_common.fetch_image', side_effect=ValueError('blocked')):
            html = embed_images_in_html('<img src="x.png" alt="diagram"/>', URL)
        self.assertNotIn('src=', html)
        self.assertIn('data-image-missing', html)

    def test_bad_configuration_and_filename_collisions(self):
        with self.assertRaises(ValueError):
            convert({'urls': [URL], 'format': 'invalid'})
        with self.assertRaises(ValueError):
            convert({'urls': ['https://example.com/'], 'format': 'pdf'})
        with self.assertRaises(ValueError):
            convert({'urls': [URL], 'format': 'pdf', 'output_name': '../escape'})
        with tempfile.TemporaryDirectory() as directory:
            entries = [{'title': 'Same', 'url': URL}, {'title': 'Same-2', 'url': URL}, {'title': 'Same', 'url': URL}]
            paths = _pick_filenames(entries, {'format': 'pdf', 'output_dir': directory})
            self.assertEqual(len(set(paths)), 3)

    def test_network_gate_robots_and_redirect_scope(self):
        clock = [0.0]
        starts = []

        def sleep(seconds):
            clock[0] += seconds

        def get(url, **kwargs):
            starts.append(clock[0])
            self.assertFalse(kwargs['allow_redirects'])
            if url.endswith('robots.txt'):
                return response(url, b'crawl-delay: 7\nUser-agent: *\nDisallow: /blocked/')
            if url.endswith('/redirect'):
                return response(url, status=302, headers={'Location': 'https://example.com/'})
            return response(url, b'content')

        with patch.multiple(sep_network, _last=-float('inf'), _cooldown=0, _interval=5, _robot=None, _blocked=False), patch('sep_network.time.monotonic', side_effect=lambda: clock[0]), patch('sep_network.time.sleep', side_effect=sleep), patch('sep_network.requests.get', side_effect=get):
            sep_network.fetch(URL)
            sep_network.fetch(URL + 'image.png')
            self.assertEqual(starts, [0, 7, 14])
            with self.assertRaisesRegex(RuntimeError, 'robots.txt'):
                sep_network.fetch('https://plato.stanford.edu/blocked/x')
            with self.assertRaises(ValueError):
                sep_network.fetch('https://plato.stanford.edu/redirect')
            self.assertEqual(len(starts), 4)

    def test_rate_limit_cooldown_and_403_block(self):
        robot = sep_network.RobotFileParser()
        robot.parse(['User-agent: *', 'Allow: /'])
        clock = [0.0]
        with patch.multiple(sep_network, _last=-float('inf'), _cooldown=0, _interval=5, _robot=robot, _blocked=False), patch('sep_network.time.monotonic', side_effect=lambda: clock[0]), patch('sep_network.time.sleep', side_effect=lambda seconds: clock.__setitem__(0, clock[0]+seconds)), patch('sep_network.requests.get', side_effect=[response(URL, status=429, headers={'Retry-After': '45'}), response(URL, b'OK'), response(URL, status=403)]) as get:
            with self.assertRaises(requests.HTTPError):
                sep_network.fetch(URL)
            sep_network.fetch(URL)
            self.assertGreaterEqual(clock[0], 45)
            with self.assertRaises(requests.HTTPError):
                sep_network.fetch(URL)
            with self.assertRaisesRegex(RuntimeError, '403'):
                sep_network.fetch(URL)
            self.assertEqual(get.call_count, 3)


if __name__ == '__main__':
    unittest.main()
