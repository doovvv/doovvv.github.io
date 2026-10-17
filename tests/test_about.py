"""The public profile uses verified resume facts and keeps working section links."""
from html.parser import HTMLParser
import re
import unittest

from tools import build


class ProfileMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.sections = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.ids.add(attrs['id'])
        if tag == 'section':
            self.sections.append(attrs.get('id'))
        if tag == 'a':
            self.links.append(attrs.get('href', ''))


class AboutTests(unittest.TestCase):
    def test_resume_institutions_companies_and_dates_are_present(self):
        html = build.about()
        for name in ['Chao', 'Zhang', 'Tencent', 'ByteDance', 'Nanjing University', 'Sun Yat-sen University']:
            self.assertIn(name, html)
        for year in ['2025', '2026', '2029']:
            self.assertIn(year, html)
        self.assertIn('expected', html.lower())

    def test_profile_directory_links_to_existing_sections(self):
        parsed = ProfileMarkup()
        html = build.about()
        parsed.feed(html)
        self.assertIn('profile-nav', html)
        for section in ['overview', 'experience', 'education', 'skills', 'writing']:
            self.assertIn(section, parsed.sections)
            self.assertIn('#' + section, parsed.links)
        self.assertTrue({url[1:] for url in parsed.links if url.startswith('#')}.issubset(parsed.ids))

    def test_selected_impact_and_recognition_are_grounded_in_resume(self):
        html = re.sub(r'<[^>]+>', '', build.about())
        for fact in ['80%', '16s', '8s', '5+', 'AI Technology Application Award']:
            self.assertIn(fact, html)
        self.assertNotIn('GPA', html)

    def test_public_profile_uses_github_and_does_not_embed_the_private_resume(self):
        html = build.about()
        self.assertIn('https://github.com/doovvv', html)
        self.assertNotIn('resume-full.pdf', html)
        self.assertNotRegex(html, r'\b1[3-9]\d[ -]?\d{4}[ -]?\d{4}\b')
        self.assertNotIn('@', html)
        self.assertNotIn('mailto:', html)

    def test_every_profile_translation_has_english_and_chinese(self):
        keys = set(re.findall(r'data-i18n(?:-[a-z-]+)?="(profile\.[^"]+)"', build.about()))
        self.assertGreater(len(keys), 35)
        for key in keys:
            self.assertTrue(build.MESSAGES[key]['en'], key)
            self.assertTrue(build.MESSAGES[key]['zh-CN'], key)


if __name__ == '__main__':
    unittest.main()
