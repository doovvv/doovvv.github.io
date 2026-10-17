"""Content and navigation regression checks for the static redesign."""
import json
from html.parser import HTMLParser
from pathlib import Path
import unittest
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / 'content/site.json').read_text(encoding='utf8'))


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])


class LinkNames(HTMLParser):
    def __init__(self):
        super().__init__()
        self.current = None
        self.unnamed = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            self.current = {'url': attrs.get('href'), 'name': attrs.get('aria-label', '')}
        elif tag == 'img' and self.current:
            self.current['name'] += attrs.get('alt', '')

    def handle_data(self, data):
        if self.current:
            self.current['name'] += data.strip()

    def handle_endtag(self, tag):
        if tag == 'a' and self.current:
            if not self.current['name'].strip():
                self.unnamed.append(self.current['url'])
            self.current = None


class SiteTests(unittest.TestCase):
    def test_all_existing_routes_use_new_theme(self):
        for page in DATA['pages']:
            with self.subTest(route=page['file']):
                output = (ROOT / page['file']).read_text(encoding='utf8')
                self.assertIn('/assets/site.css', output)
                self.assertIn('/assets/site.js', output)
                self.assertIn('lang="zh-CN"', output)
                self.assertIn('id="site-nav"', output)

    def test_every_article_preserves_its_complete_published_body(self):
        self.assertEqual(len(DATA['posts']), 20)
        for post in DATA['posts']:
            with self.subTest(article=post['title']):
                self.assertIn(post['body'], (ROOT / post['file']).read_text(encoding='utf8'))

    def test_search_includes_full_text_of_all_articles(self):
        search = json.loads((ROOT / 'assets/search.json').read_text(encoding='utf8'))
        self.assertEqual({p['url'] for p in search}, {p['url'] for p in DATA['posts']})
        learning = next(p for p in search if p['title'] == 'machine learning review')
        self.assertIn('梯度', learning['text'])

    def test_homepage_has_real_articles_and_working_navigation(self):
        source = (ROOT / 'index.html').read_text(encoding='utf8')
        parsed = Links()
        parsed.feed(source)
        self.assertIn('article-grid', parsed.ids)
        self.assertIn('search-dialog', parsed.ids)
        self.assertIn('/archives/', parsed.links)
        self.assertIn('/tags/', parsed.links)
        for link in parsed.links:
            url = urlparse(link)
            if url.scheme or url.netloc or not url.path:
                continue
            path = ROOT / unquote(url.path).lstrip('/')
            if url.path.endswith('/'):
                path = path / 'index.html'
            self.assertTrue(path.is_file(), f'Broken homepage link: {link}')

    def test_tags_index_contains_every_existing_tag_route(self):
        output = (ROOT / 'tags/index.html').read_text(encoding='utf8')
        parsed = Links()
        parsed.feed(output)
        links = {unquote(x) for x in parsed.links}
        self.assertTrue(set(DATA['tag_names']).issubset(links))

    def test_homepage_links_have_an_accessible_name(self):
        parsed = LinkNames()
        parsed.feed((ROOT / 'index.html').read_text(encoding='utf8'))
        self.assertEqual(parsed.unnamed, [], 'Every link, including image links, needs a readable name')


if __name__ == '__main__':
    unittest.main()
