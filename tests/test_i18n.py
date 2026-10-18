"""The public interface defaults to English while articles retain their text."""
import json
from html.parser import HTMLParser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SITE = json.loads((ROOT / 'content/site.json').read_text(encoding='utf8'))


class Interface(HTMLParser):
    def __init__(self):
        super().__init__()
        self.language = None
        self.language_button = False
        self.in_navigation = False
        self.navigation = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'html':
            self.language = attrs.get('lang')
        if tag == 'button' and 'language-toggle' in attrs.get('class', '').split():
            self.language_button = True
        if tag == 'nav' and attrs.get('id') == 'site-nav':
            self.in_navigation = True
        if tag == 'script' and attrs.get('src'):
            self.scripts.append(attrs['src'])

    def handle_endtag(self, tag):
        if tag == 'nav':
            self.in_navigation = False

    def handle_data(self, data):
        if self.in_navigation and data.strip():
            self.navigation.append(data.strip())


class InterfaceLanguageTests(unittest.TestCase):
    def parse(self, filename):
        result = Interface()
        result.feed((ROOT / filename).read_text(encoding='utf8'))
        return result

    def test_first_visit_has_english_navigation(self):
        interface = self.parse('index.html')
        self.assertEqual(interface.language, 'en')
        self.assertEqual(interface.navigation, ['Home', 'Archive', 'Tags', 'About'])

    def test_language_switch_is_available_on_every_public_page(self):
        for filename in [p['file'] for p in SITE['pages']] + ['about/index.html']:
            interface = self.parse(filename)
            self.assertTrue(interface.language_button, filename)

    def test_dynamic_controls_load_after_the_translation_runtime(self):
        scripts = self.parse('index.html').scripts
        self.assertIn('/assets/ui-messages.js', scripts)
        self.assertIn('/assets/i18n.js', scripts)
        self.assertLess(scripts.index('/assets/ui-messages.js'), scripts.index('/assets/i18n.js'))
        self.assertLess(scripts.index('/assets/i18n.js'), scripts.index('/assets/site.js'))


if __name__ == '__main__':
    unittest.main()
