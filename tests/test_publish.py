"""Use a local bare remote: these tests never publish to the real website."""
import json
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch

try:
    from tools import blog
except ImportError:
    blog = None

ROOT = Path(__file__).resolve().parents[1]


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(blog, 'The local writing and publishing tool must exist')
        (ROOT / '.qa').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / '.qa')
        self.base = Path(self.temp.name).resolve()
        self.assertTrue(self.base.is_relative_to((ROOT / '.qa').resolve()))
        self.addCleanup(self.temp.cleanup)
        self.root = self.base / 'blog'
        self.root.mkdir()
        (self.root / 'content/posts').mkdir(parents=True)
        for filename in ['site.json', 'ui.json']:
            shutil.copyfile(ROOT / 'content' / filename, self.root / 'content' / filename)
        (self.root / 'CNAME').write_text('doovvv.cn\n', encoding='utf8')
        (self.root / '.gitignore').write_text('content/posts/\n.backups/\n', encoding='utf8')
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Blog Test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('add', '.')
        self.git('commit', '-m', 'Initial')
        self.remote = self.base / 'remote.git'
        self.git('init', '--bare', str(self.remote))
        self.git('remote', 'add', 'origin', str(self.remote))
        self.git('push', '-u', 'origin', 'main')

    def git(self, *args):
        result = subprocess.run(['git', *args], cwd=self.root, capture_output=True, text=True, encoding='utf8')
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def article(self, draft=False):
        path = self.root / 'content/posts/new-note/index.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('---\ntitle: A new note\ndate: 2026-10-17\ntags: [AI]\ndraft: ' + str(draft).lower() + '\n---\n\n## Hello\n\nNew content.', encoding='utf8')
        return path

    def test_publish_builds_pushes_and_backs_up_published_sources(self):
        self.article()
        blog.publish(self.root)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.git('rev-parse', 'origin/main'))
        self.assertEqual(self.git('show', 'HEAD:CNAME'), 'doovvv.cn')
        self.assertIn('A new note', self.git('show', 'HEAD:content/posts/new-note/index.md'))
        self.assertIn('New content.', self.git('show', 'HEAD:2026/10/17/new-note/index.html'))
        legacy_count = len(json.loads((self.root / 'content/site.json').read_text(encoding='utf8'))['posts'])
        self.assertEqual(len(json.loads(self.git('show', 'HEAD:assets/search.json'))), legacy_count + 1)
        self.assertTrue(list((self.root / '.backups').glob('*.zip')))

    def test_drafts_are_not_in_the_remote_tree_even_after_preview(self):
        path = self.article(draft=True)
        from tools.build import build_site
        build_site(self.root, include_drafts=True)
        blog.publish(self.root)
        tracked = self.git('ls-tree', '-r', '--name-only', 'HEAD')
        self.assertNotIn('content/posts/new-note/', tracked)
        self.assertNotIn('2026/10/17/new-note/', tracked)
        self.assertTrue(path.exists())

    def test_previously_published_note_can_be_returned_to_a_local_draft(self):
        path = self.article()
        blog.publish(self.root)
        path.write_text(path.read_text(encoding='utf8').replace('draft: false', 'draft: true'), encoding='utf8')
        blog.publish(self.root)
        tracked = self.git('ls-tree', '-r', '--name-only', 'HEAD')
        self.assertNotIn('content/posts/new-note/', tracked)
        self.assertNotIn('2026/10/17/new-note/', tracked)
        self.assertTrue(path.exists())

    def test_invalid_content_does_not_create_or_push_a_commit(self):
        path = self.article()
        path.write_text('broken front matter', encoding='utf8')
        before = self.git('rev-parse', 'HEAD')
        with self.assertRaises(ValueError):
            blog.publish(self.root)
        self.assertEqual(before, self.git('rev-parse', 'HEAD'))
        self.assertEqual(before, self.git('rev-parse', 'origin/main'))

    def test_staged_changes_are_not_silently_committed(self):
        (self.root / 'user.txt').write_text('unrelated', encoding='utf8')
        self.git('add', 'user.txt')
        with self.assertRaisesRegex(ValueError, '暂存|staged'):
            blog.publish(self.root)

    def test_a_new_remote_commit_blocks_publishing_without_overwriting_it(self):
        other = self.base / 'other'
        self.git('clone', '-b', 'main', str(self.remote), str(other))
        subprocess.run(['git', '-C', str(other), 'config', 'user.name', 'Other'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(other), 'config', 'user.email', 'other@example.invalid'], check=True, capture_output=True)
        (other / 'remote.txt').write_text('remote update', encoding='utf8')
        for args in [('add', '.'), ('commit', '-m', 'Remote update'), ('push', 'origin', 'main')]:
            subprocess.run(['git', '-C', str(other), *args], check=True, capture_output=True)
        before = self.git('rev-parse', 'HEAD')
        self.article()
        with self.assertRaisesRegex(ValueError, '远端|remote'):
            blog.publish(self.root)
        self.assertEqual(before, self.git('rev-parse', 'HEAD'))

    def test_new_article_is_a_draft_and_does_not_replace_existing_work(self):
        path = blog.new_article(self.root, '我的新文章', 'my-note')
        self.assertIn('draft: true', path.read_text(encoding='utf8'))
        self.assertTrue((path.parent / 'images').is_dir())
        with self.assertRaises(FileExistsError):
            blog.new_article(self.root, 'Again', 'my-note')

    def test_a_failed_push_keeps_the_local_commit_and_can_be_retried(self):
        self.article()
        hook = self.remote / 'hooks/pre-receive'
        hook.write_text('#!/bin/sh\nexit 1\n', encoding='utf8')
        with self.assertRaises(ValueError):
            blog.publish(self.root)
        saved = self.git('rev-parse', 'HEAD')
        self.assertNotEqual(saved, self.git('rev-parse', 'origin/main'))
        hook.unlink()
        blog.publish(self.root)
        self.assertEqual(saved, self.git('rev-parse', 'HEAD'))
        self.assertEqual(saved, self.git('rev-parse', 'origin/main'))

    def test_brackets_in_a_referenced_image_name_do_not_publish_other_files(self):
        path = self.article()
        images = path.parent / 'images'
        images.mkdir()
        (images / '[draft].png').write_bytes(b'public image')
        (images / 'd.png').write_bytes(b'unreferenced private image')
        path.write_text(path.read_text(encoding='utf8') + '\n![Image](images/[draft].png)\n', encoding='utf8')
        blog.publish(self.root)
        tracked = self.git('ls-tree', '-r', '--name-only', 'HEAD')
        self.assertIn('content/posts/new-note/images/[draft].png', tracked)
        self.assertNotIn('content/posts/new-note/images/d.png', tracked)

    def test_loose_markdown_publishes_directly_and_repeated_edits_keep_the_original_url(self):
        path = self.root / 'content/posts/go map.md'
        original = '# Go Map 实现详解\n\nA map implementation note.\n'
        path.write_text(original, encoding='utf8')
        original_bytes = path.read_bytes()
        draft = self.root / 'content/posts/private.md'
        draft.write_text('---\ndraft: true\n---\n\nPrivate idea.', encoding='utf8')
        blog.publish(self.root)
        search = json.loads(self.git('show', 'HEAD:assets/search.json'))
        note = [p for p in search if p['title'] == 'Go Map 实现详解']
        self.assertEqual(len(note), 1, 'Publishing must include a loose Markdown note')
        url = note[0]['url']
        self.assertTrue(url.endswith('/go-map/'))
        source = path.read_text(encoding='utf8')
        self.assertIn('slug: go-map', source)
        self.assertIn('date:', source)
        self.assertTrue(source.endswith(original))
        self.assertEqual(self.git('show', 'HEAD:content/posts/go map.md'), source.strip())
        self.assertNotIn('content/posts/private.md', self.git('ls-tree', '-r', '--name-only', 'HEAD'))
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.git('rev-parse', 'origin/main'))
        with zipfile.ZipFile(next((self.root / '.backups').glob('*.zip'))) as backup:
            self.assertEqual(backup.read('content/posts/go map.md'), original_bytes)
        path.write_text(source + '\nEdited after publication.\n', encoding='utf8')
        class LaterDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2030, 4, 5, tzinfo=tz)
        with patch('tools.content.datetime', LaterDateTime):
            blog.publish(self.root)
        second_search = json.loads(self.git('show', 'HEAD:assets/search.json'))
        note = next(p for p in second_search if p['title'] == 'Go Map 实现详解')
        self.assertEqual(note['url'], url)
        self.assertIn('Edited after publication.', self.git('show', 'HEAD:' + url.lstrip('/') + 'index.html'))
        self.assertEqual(self.git('show', 'HEAD:content/posts/go map.md').split('---', 2)[1], source.split('---', 2)[1])

    def test_broken_loose_article_does_not_rewrite_sources_or_create_a_commit(self):
        path = self.root / 'content/posts/go map.md'
        original = '# Go Map\n\n![Missing](images/not-uploaded.png)'
        path.write_text(original, encoding='utf8')
        before = self.git('rev-parse', 'HEAD')
        with self.assertRaisesRegex(ValueError, 'not-uploaded.png'):
            blog.publish(self.root)
        self.assertEqual(path.read_text(encoding='utf8'), original)
        self.assertEqual(before, self.git('rev-parse', 'HEAD'))
        self.assertEqual(before, self.git('rev-parse', 'origin/main'))


if __name__ == '__main__':
    unittest.main()
