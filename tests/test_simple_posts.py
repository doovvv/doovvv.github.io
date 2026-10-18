"""Loose Markdown notes use the same build and publishing data as folder posts."""
from datetime import datetime
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools import build, content

ROOT = Path(__file__).resolve().parents[1]


class SimplePostTests(unittest.TestCase):
    def setUp(self):
        (ROOT / '.qa').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / '.qa')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.posts = self.root / 'content/posts'
        self.posts.mkdir(parents=True)
        for name in ['site.json', 'ui.json']:
            shutil.copyfile(ROOT / 'content' / name, self.root / 'content' / name)

    def note(self, name='go map.md', text='# Go Map 实现详解\n\n## Hash buckets\n\nA technical note.'):
        path = self.posts / name
        path.write_text(text, encoding='utf8')
        return path

    def simple_post(self, site, slug='go-map'):
        matches = [post for post in site['posts'] if post['slug'] == slug]
        self.assertEqual(len(matches), 1, 'A plain Markdown file must become one article')
        return matches[0]

    def test_plain_file_uses_heading_filename_and_today_without_rewriting_during_preview(self):
        path = self.note()
        original = path.read_bytes()
        site = content.load_site(self.root)
        post = self.simple_post(site)
        today = datetime.now(content.ZONE).date().isoformat()
        self.assertEqual(post['title'], 'Go Map 实现详解')
        self.assertEqual(post['url'], '/' + today.replace('-', '/') + '/go-map/')
        self.assertEqual(post['tags'], [])
        self.assertNotIn('<h1', post['body'])
        self.assertIn('Hash buckets', post['toc'])
        self.assertEqual(path.read_bytes(), original)
        self.assertIn('content/posts/go map.md', site['_public_sources'])
        home = next(page for page in site['pages'] if page['url'] == '/')
        self.assertEqual(home['posts'][0], post['url'])

    def test_filename_supplies_a_title_when_there_is_no_heading(self):
        self.note('中文 笔记.md', 'An introduction without a heading.')
        post = self.simple_post(content.load_site(self.root), '中文-笔记')
        self.assertEqual(post['title'], '中文 笔记')

    def test_optional_metadata_keeps_explicit_values_and_fills_only_missing_fields(self):
        self.note(text='---\ntitle: My map note\ndate: 2025-02-03\nslug: custom-map\ntags: [Go]\n---\n\n# Go Map\n\nContent.')
        post = self.simple_post(content.load_site(self.root), 'custom-map')
        self.assertEqual(post['title'], 'My map note')
        self.assertEqual(post['url'], '/2025/02/03/custom-map/')
        self.assertEqual([tag['name'] for tag in post['tags']], ['Go'])

    def test_simple_draft_is_excluded_from_release_and_included_in_preview(self):
        self.note(text='---\ndraft: true\n---\n\n# Go Map\n\nUnpublished thought.')
        release = content.load_site(self.root)
        self.assertFalse(any(p['slug'] == 'go-map' for p in release['posts']))
        self.assertNotIn('content/posts/go map.md', release['_public_sources'])
        preview = content.load_site(self.root, include_drafts=True)
        self.simple_post(preview)

    def test_relative_images_and_automatic_cover_work_for_loose_files(self):
        images = self.posts / 'go map.assets'
        images.mkdir()
        (images / 'hash buckets.png').write_bytes(b'article image')
        self.note(text='# Go Map\n\n![Buckets](<go map.assets/hash buckets.png>)\n\nA note.')
        site = build.build_site(self.root)
        post = self.simple_post(site)
        image = self.root / post['url'].lstrip('/') / 'go map.assets/hash buckets.png'
        self.assertEqual(image.read_bytes(), b'article image')
        home = (self.root / 'index.html').read_text(encoding='utf8')
        self.assertIn('go%20map.assets/hash%20buckets.png', home)
        self.assertIn('content/posts/go map.assets/hash buckets.png', site['_public_sources'])
        self.assertIn(post['url'], [p['url'] for p in json.loads((self.root / 'assets/search.json').read_text(encoding='utf8'))])

    def test_incomplete_or_invalid_metadata_is_reported_instead_of_published_as_body(self):
        for raw in ['---\ntitle: Go Map\n', '---\ndate: invalid\n---\n\nBody', '---\ndraft: "false"\n---\n\nBody']:
            with self.subTest(raw=raw):
                self.note(text=raw)
                with self.assertRaisesRegex(ValueError, 'go map.md'):
                    content.load_site(self.root)

    def test_flat_file_cannot_silently_override_a_folder_article(self):
        today = datetime.now(content.ZONE).date().isoformat()
        self.note()
        folder = self.posts / 'go-map'
        folder.mkdir()
        (folder / 'index.md').write_text('---\ntitle: Original\ndate: ' + today + '\n---\n\nExisting article.', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'duplicate article URL'):
            content.load_site(self.root)

    def test_case_only_route_difference_cannot_overwrite_a_windows_output_file(self):
        today = datetime.now(content.ZONE).date().isoformat()
        self.note()
        folder = self.posts / 'Go-map'
        folder.mkdir()
        (folder / 'index.md').write_text('---\ntitle: Original\ndate: ' + today + '\n---\n\nExisting article.', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'duplicate article URL'):
            content.load_site(self.root)


if __name__ == '__main__':
    unittest.main()
