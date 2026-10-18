"""Exercise the writing workflow against disposable copies of the recovered site."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools import build
try:
    from tools import content
except ImportError:
    content = None

ROOT = Path(__file__).resolve().parents[1]


class MarkdownContentTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(content, 'The Markdown article reader must exist')
        (ROOT / '.qa').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / '.qa')
        self.root = Path(self.temp.name)
        self.assertTrue(self.root.resolve().is_relative_to((ROOT / '.qa').resolve()))
        self.addCleanup(self.temp.cleanup)
        (self.root / 'content/posts').mkdir(parents=True)
        for name in ['site.json', 'ui.json']:
            shutil.copyfile(ROOT / 'content' / name, self.root / 'content' / name)
        self.legacy_count = len(json.loads((self.root / 'content/site.json').read_text(encoding='utf8'))['posts'])

    def article(self, folder='test-note', metadata='', text=None):
        directory = self.root / 'content/posts' / folder
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'images').mkdir(exist_ok=True)
        (directory / 'images/first.png').write_bytes(b'example image')
        body = text if text is not None else 'An introduction.\n\n![First](images/first.png)\n\n## 中文标题\n\n```python\nprint("hello")\n```\n\n| A | B |\n| - | - |\n| 1 | 2 |\n\nMath: $x^2$.\n'
        path = directory / 'index.md'
        path.write_text('---\ntitle: 新文章\ndate: 2026-10-17\ntags: [AI, 新标签]\ndraft: false\n' + metadata + '---\n\n' + body, encoding='utf8')
        return path

    def test_markdown_renders_images_code_tables_math_and_unicode_toc(self):
        self.article()
        site = content.load_site(self.root)
        post = next(p for p in site['posts'] if p['slug'] == 'test-note')
        self.assertEqual(post['url'], '/2026/10/17/test-note/')
        self.assertIn('/2026/10/17/test-note/images/first.png', post['body'])
        self.assertIn('language-python', post['body'])
        self.assertIn('<table>', post['body'])
        self.assertIn('arithmatex', post['body'])
        self.assertIn('中文标题', post['toc'])
        self.assertIn('中文标题', post['text'])
        self.assertNotIn('class=', post['excerpt'])
        self.assertGreater(post['minutes'], 0)

    def test_new_article_automatically_enters_all_indexes_and_neighbors(self):
        self.article()
        site = content.load_site(self.root)
        self.assertEqual(len(site['posts']), self.legacy_count + 1)
        by_url = {p['url']: p for p in site['pages']}
        url = '/2026/10/17/test-note/'
        for route in ['/', '/archives/', '/archives/2026/', '/archives/2026/10/', '/tags/ai/', '/tags/新标签/']:
            self.assertIn(url, by_url[route]['posts'], route)
        new = next(p for p in site['posts'] if p['url'] == url)
        self.assertEqual(new['prev']['title'], 'machine learning review')
        self.assertIsNone(new['next'])

    def test_drafts_are_previewable_and_absent_from_publish_data(self):
        path = self.article()
        path.write_text(path.read_text(encoding='utf8').replace('draft: false', 'draft: true'), encoding='utf8')
        self.assertEqual(len(content.load_site(self.root)['posts']), self.legacy_count)
        self.assertEqual(len(content.load_site(self.root, include_drafts=True)['posts']), self.legacy_count + 1)

    def test_unfinished_draft_image_does_not_block_other_articles(self):
        path = self.article(text='![Not uploaded yet](images/later.png)')
        path.write_text(path.read_text(encoding='utf8').replace('draft: false', 'draft: true'), encoding='utf8')
        self.assertEqual(len(content.load_site(self.root)['posts']), self.legacy_count)

    def test_root_image_is_included_in_the_public_asset_list(self):
        image = self.root / 'assets/uploads/photo.png'
        image.parent.mkdir(parents=True)
        image.write_bytes(b'image')
        self.article(text='![Root image](/assets/uploads/photo.png)')
        site = content.load_site(self.root)
        self.assertIn('assets/uploads/photo.png', site['_public_assets'])

    def test_invalid_metadata_and_local_image_paths_stop_with_a_useful_error(self):
        for field, value in [('date', 'not-a-date'), ('draft', '"false"'), ('tags', '123'), ('title', '""'), ('slug', '../escape')]:
            with self.subTest(field=field):
                path = self.article()
                original = path.read_text(encoding='utf8')
                import re
                if field == 'slug':
                    original = original.replace('draft: false', 'draft: false\nslug: ' + value)
                else:
                    original = re.sub(r'^' + field + r':.*$', field + ': ' + value, original, flags=re.M)
                path.write_text(original, encoding='utf8')
                with self.assertRaisesRegex(ValueError, 'index.md'):
                    content.load_site(self.root)
        for image in ['images/missing.png', '../private.png', 'file:///C:/private.png']:
            with self.subTest(image=image):
                self.article(text='![image](' + image + ')')
                with self.assertRaisesRegex(ValueError, 'index.md'):
                    content.load_site(self.root)

    def test_duplicate_article_urls_are_rejected(self):
        self.article('one', 'slug: same\n')
        self.article('two', 'slug: same\n')
        with self.assertRaisesRegex(ValueError, 'same'):
            content.load_site(self.root)

    def test_legacy_bodies_and_routes_remain_available(self):
        self.article()
        legacy = json.loads((self.root / 'content/site.json').read_text(encoding='utf8'))
        site = content.load_site(self.root)
        bodies = {p['url']: p['body'] for p in site['posts']}
        for post in legacy['posts']:
            self.assertEqual(bodies[post['url']], post['body'])
        self.assertTrue({p['file'] for p in legacy['pages']}.issubset({p['file'] for p in site['pages']}))

    def test_explicit_legacy_override_retains_the_old_route(self):
        self.article(metadata='legacy_url: /2025/01/02/machine-learning-review/\n')
        site = content.load_site(self.root)
        self.assertEqual(len(site['posts']), self.legacy_count)
        post = next(p for p in site['posts'] if p['url'] == '/2025/01/02/machine-learning-review/')
        self.assertEqual(post['title'], '新文章')

    def test_pagination_grows_without_manual_lists(self):
        for i in range(31 - self.legacy_count):
            self.article('note-' + str(i))
        site = content.load_site(self.root)
        pages = {p['url']: p for p in site['pages']}
        self.assertEqual(len(pages['/page/4/']['posts']), 1)
        self.assertEqual(len(pages['/archives/page/4/']['posts']), 1)
        home_posts = [url for p in site['pages'] if p['kind'] == 'home' for url in p['posts']]
        self.assertEqual(len(home_posts), len(set(home_posts)))
        self.assertEqual(len(home_posts), 31)

    def test_build_copies_first_image_and_updates_counts_and_search(self):
        self.article()
        self.assertTrue(callable(getattr(build, 'build_site', None)), 'The builder must accept a test workspace')
        site = build.build_site(self.root)
        image = self.root / '2026/10/17/test-note/images/first.png'
        self.assertTrue(image.is_file())
        home = (self.root / 'index.html').read_text(encoding='utf8')
        self.assertIn('first.png', home)
        self.assertIn(str(self.legacy_count + 1), home)
        self.assertEqual(len(json.loads((self.root / 'assets/search.json').read_text(encoding='utf8'))), self.legacy_count + 1)
        self.assertEqual(len(site['posts']), self.legacy_count + 1)

    def test_draft_or_deleted_article_removes_only_its_generated_files(self):
        path = self.article()
        build.build_site(self.root)
        output = self.root / '2026/10/17/test-note/index.html'
        unrelated = output.parent / 'keep.txt'
        unrelated.write_text('user file', encoding='utf8')
        path.write_text(path.read_text(encoding='utf8').replace('draft: false', 'draft: true'), encoding='utf8')
        build.build_site(self.root)
        self.assertFalse(output.exists())
        self.assertFalse((output.parent / 'images/first.png').exists())
        self.assertTrue(unrelated.exists())

    def test_image_reused_by_another_public_article_survives_original_withdrawal(self):
        first = self.article('first')
        build.build_site(self.root)
        self.article('second', text='![Shared](/2026/10/17/first/images/first.png)')
        build.build_site(self.root)
        first.write_text(first.read_text(encoding='utf8').replace('draft: false', 'draft: true'), encoding='utf8')
        build.build_site(self.root)
        self.assertTrue((self.root / '2026/10/17/first/images/first.png').exists())
        self.assertFalse((self.root / '2026/10/17/first/index.html').exists())


if __name__ == '__main__':
    unittest.main()
