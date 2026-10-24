"""Extract parsed SEP articles into UTF-8 text without downloading images."""
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString
from sep_common import build_chapter_html


def html_to_text(fragment, source_url):
    soup = BeautifulSoup(fragment, 'lxml')
    for node in soup.select('script,style'):
        node.decompose()
    for node in list(soup.find_all(string=True)):
        if not node.find_parent('pre'):
            node.replace_with(re.sub(r'\s+', ' ', str(node)))
    for image in soup.select('img'):
        source = image.get('src', '')
        image.replace_with('\n[图片：' + image.get('alt', '无说明') + ('；来源：' + urljoin(source_url, source) if source else '') + ']\n')
    for table in soup.select('table'):
        rows = ['\t'.join(cell.get_text(' ', strip=True) for cell in row.find_all(['td', 'th'], recursive=False)) for row in table.select('tr')]
        table.replace_with('\n' + '\n'.join(rows) + '\n')
    for br in soup.select('br'):
        br.replace_with('\n')
    for block in soup.select('p,div,h1,h2,h3,h4,h5,h6,blockquote,pre,li,dt,dd,figure'):
        block.insert_before(NavigableString('\n'))
        block.insert_after(NavigableString('\n'))
    text = '\n'.join(line.strip(' ') for line in soup.get_text().splitlines())
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def generate_txt(entries, output_path):
    blocks = []
    for entry in entries:
        source = entry['url']
        blocks += [entry['title'], '=' * 60, '来源：' + source]
        for fragment in [entry['pubinfo'], entry['preamble_html'], *(build_chapter_html(s) for s in entry['sections'])]:
            text = html_to_text(fragment, source)
            if text:
                blocks.append(text)
        blocks.append('-' * 60)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.sep-txt-', suffix='.part', dir=output_path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write('\n\n'.join(blocks) + '\n')
        os.replace(temporary, output_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return str(output_path)


def main():
    import argparse
    from sep_app import convert
    parser = argparse.ArgumentParser(description='从 SEP 文章提取 UTF-8 TXT，可合并多篇，不下载图片')
    parser.add_argument('urls', nargs='+')
    parser.add_argument('-o', '--output', default='sep-output.txt')
    args = parser.parse_args()
    output = Path(args.output)
    paths = convert({'urls': args.urls, 'format': 'txt', 'embed_images': False, 'output_mode': 'merge', 'output_name': output.stem, 'output_dir': str(output.parent), 'on_status': print})
    print(paths[0])


if __name__ == '__main__':
    main()
