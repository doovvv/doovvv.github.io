"""Cover behavior for existing and future articles."""
from html.parser import HTMLParser
import unittest
from urllib.parse import unquote, urlparse

from tools import build


class CoverImages(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []

    def handle_starttag(self, tag, attrs):
        if tag == 'img':
            self.images.append(dict(attrs))


class CoverTests(unittest.TestCase):
    def card_image(self, post):
        parsed = CoverImages()
        parsed.feed(build.card(post, 0))
        self.assertEqual(len(parsed.images), 1)
        return parsed.images[0]

    def post(self, body, **changes):
        return {**build.SITE['posts'][0], 'body': body, **changes}

    def test_first_body_image_wins_over_later_images(self):
        post = self.post('<p><img src="/assets/images/mountain-day.jpg"></p><img src="/assets/images/forest.jpg">')
        self.assertEqual(self.card_image(post)['src'], '/assets/images/mountain-day.jpg')

    def test_new_articles_follow_the_same_rule_without_cover_metadata(self):
        post = self.post('<p>A new note</p><img src="/assets/images/forest.jpg">', slug='new-note', url='/2026/10/15/new-note/')
        self.assertEqual(self.card_image(post)['src'], '/assets/images/forest.jpg')

    def test_relative_image_paths_resolve_against_the_article(self):
        post = self.post('<img src="image-5.png?version=2&amp;size=large">')
        actual = urlparse(self.card_image(post)['src'])
        self.assertEqual(unquote(actual.path), post['url'] + 'image-5.png')
        self.assertEqual(actual.query, 'version=2&size=large')

    def test_external_images_keep_their_url(self):
        post = self.post('<img src="https://images.example.org/new-photo.jpg?size=large">')
        self.assertEqual(self.card_image(post)['src'], 'https://images.example.org/new-photo.jpg?size=large')

    def test_previously_downloaded_first_image_uses_its_local_copy(self):
        post = self.post('<img src="https://pic3.zhimg.com/v2-0a586723aa7eb9e4cdbd38d564ef0320_r.jpg">')
        self.assertEqual(self.card_image(post)['src'], '/assets/images/article-reference-1.jpg')

    def test_lazy_loaded_first_image_uses_the_actual_image_url(self):
        post = self.post('<img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==" data-src="/assets/images/forest.jpg">')
        self.assertEqual(self.card_image(post)['src'], '/assets/images/forest.jpg')

    def test_no_image_uses_the_existing_default_cover(self):
        post = self.post('<p>Text only.</p>')
        self.assertEqual(self.card_image(post)['src'], '/assets/covers/algorithms.svg')

    def test_missing_first_image_falls_back_without_selecting_the_second(self):
        post = self.post('<img src="/not-uploaded.png"><img src="/assets/images/forest.jpg">')
        self.assertEqual(self.card_image(post)['src'], '/assets/covers/algorithms.svg')

    def test_featured_notes_use_the_same_first_image_rule(self):
        parsed = CoverImages()
        parsed.feed(build.featured())
        self.assertEqual(parsed.images[0]['src'], '/2025/01/02/machine-learning-review/image-20250102224818608.png')


if __name__ == '__main__':
    unittest.main()
