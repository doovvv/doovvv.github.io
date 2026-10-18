"""The optimized first-screen images follow source changes and preserve content."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

try:
    from PIL import Image
except ImportError:
    Image = None
from tools import images


@unittest.skipIf(Image is None, 'Install requirements-images.txt to test image generation')
class HomeImageTests(unittest.TestCase):
    def setUp(self):
        directory = Path(__file__).resolve().parents[1] / '.qa'
        directory.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=directory)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assertTrue(self.root.resolve().is_relative_to(directory.resolve()))
        (self.root / 'assets/images').mkdir(parents=True)

    def source(self, color='blue', size=(90, 60)):
        Image.new('RGB', size, color).save(self.root / 'assets/images/mountain-day.jpg')

    def test_variants_do_not_upscale_and_are_real_webp(self):
        self.source()
        outputs = images.optimize_home_images(self.root)
        entry = images.image_variants(self.root, 'hero')
        self.assertEqual(len(entry['variants']), 1)
        path = self.root / entry['variants'][0]['path'].lstrip('/')
        self.assertIn(path.relative_to(self.root).as_posix(), outputs)
        with Image.open(path) as result:
            self.assertEqual(result.format, 'WEBP')
            self.assertEqual(result.size, (90, 60))

    def test_replacing_the_source_never_uses_old_variants(self):
        self.source()
        images.optimize_home_images(self.root)
        old = images.image_variants(self.root, 'hero')['variants'][0]['path']
        self.source('red')
        self.assertIsNone(images.image_variants(self.root, 'hero'))
        images.optimize_home_images(self.root)
        self.assertNotEqual(images.image_variants(self.root, 'hero')['variants'][0]['path'], old)

    def test_existing_outputs_work_without_codec_and_new_sources_fall_back(self):
        self.source()
        images.optimize_home_images(self.root)
        with patch.dict(sys.modules, {'PIL': None}):
            images.optimize_home_images(self.root)
            self.assertIsNotNone(images.image_variants(self.root, 'hero'))
        self.source('red')
        with patch.dict(sys.modules, {'PIL': None}):
            images.optimize_home_images(self.root)
            self.assertIsNone(images.image_variants(self.root, 'hero'))

    def test_animated_avatar_keeps_frames_and_loop(self):
        frames = [Image.new('RGB', (20, 20), c) for c in ['blue', 'red']]
        frames[0].save(self.root / 'assets/images/avatar.gif', save_all=True,
                       append_images=frames[1:], duration=[40, 80], loop=2)
        images.optimize_home_images(self.root)
        entry = images.image_variants(self.root, 'avatar')
        with Image.open(self.root / entry['variants'][0]['path'].lstrip('/')) as result:
            self.assertEqual(result.n_frames, 2)
            self.assertEqual(result.info['loop'], 2)
            durations = []
            for index in range(2):
                result.seek(index)
                result.load()
                durations.append(result.info['duration'])
            self.assertEqual(durations, [40, 80])

    def test_gif_without_loop_metadata_still_plays_once(self):
        frames = [Image.new('RGB', (20, 20), c) for c in ['blue', 'red']]
        frames[0].save(self.root / 'assets/images/avatar.gif', save_all=True,
                       append_images=frames[1:], duration=[40, 80])
        images.optimize_home_images(self.root)
        entry = images.image_variants(self.root, 'avatar')
        with Image.open(self.root / entry['variants'][0]['path'].lstrip('/')) as result:
            self.assertEqual(result.info['loop'], 1)
