"""Build cached WebP variants while keeping original images as browser fallbacks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

RECIPE = 'webp-q82-v2'
SOURCES = {'hero': 'assets/images/mountain-day.jpg', 'avatar': 'assets/images/avatar.gif'}
WIDTHS = {'hero': (960, 1600, 2560), 'avatar': (340, 680)}
MANIFEST = 'assets/optimized/home-images.json'


def _manifest(root):
    try:
        value = json.loads((root / MANIFEST).read_text(encoding='utf8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _variant_path(root, value):
    if not isinstance(value, str) or not value.startswith('/assets/optimized/'):
        return None
    path = (root / value.lstrip('/')).resolve()
    directory = (root / 'assets/optimized').resolve()
    return path if path.parent == directory and path.suffix == '.webp' else None


def _current_entry(root, kind, manifest):
    source = root / SOURCES[kind]
    entry = manifest.get(kind)
    if not source.is_file() or not isinstance(entry, dict):
        return None
    if entry.get('recipe') != RECIPE or entry.get('source_hash') != hashlib.sha256(source.read_bytes()).hexdigest():
        return None
    if any(not isinstance(entry.get(key), int) or entry[key] <= 0 for key in ('width', 'height')):
        return None
    variants = entry.get('variants')
    if not isinstance(variants, list) or not variants:
        return None
    for variant in variants:
        if not isinstance(variant, dict):
            return None
        path = _variant_path(root, variant.get('path'))
        if path is None or not path.is_file() or path.stat().st_size == 0:
            return None
        if not isinstance(variant.get('width'), int) or variant['width'] <= 0:
            return None
    return entry


def image_variants(root, kind):
    root = Path(root)
    return _current_entry(root, kind, _manifest(root))


def favicon_url(root):
    root = Path(root)
    source = root / SOURCES['avatar']
    if not source.is_file():
        return '/' + SOURCES['avatar']
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    relative = f'assets/optimized/avatar-{digest}-icon-64.png'
    if (root / relative).is_file():
        return '/' + relative
    return '/' + SOURCES['avatar'] + '?v=' + digest


def optimize_favicon(root):
    root = Path(root)
    source = root / SOURCES['avatar']
    if not source.is_file():
        return set()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    relative = f'assets/optimized/avatar-{digest}-icon-64.png'
    target = root / relative
    if not target.is_file():
        try:
            from PIL import Image, ImageChops, ImageDraw, ImageOps
        except ImportError:
            return set()
        with Image.open(source) as opened:
            image = ImageOps.fit(ImageOps.exif_transpose(opened).convert('RGBA'), (256, 256))
        mask = Image.new('L', image.size, 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 255, 255), fill=255)
        image.putalpha(ImageChops.multiply(image.getchannel('A'), mask))
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix('.tmp')
        image.resize((64, 64), Image.Resampling.LANCZOS).save(temporary, format='PNG', optimize=True)
        temporary.replace(target)
    return {relative}


def optimize_home_images(root):
    root = Path(root)
    if not any((root / source).is_file() for source in SOURCES.values()):
        return set()
    previous = _manifest(root)
    current = {}
    codec = None
    for kind, relative in SOURCES.items():
        source = root / relative
        if not source.is_file():
            continue
        cached = _current_entry(root, kind, previous)
        if cached:
            current[kind] = cached
            continue
        if codec is None:
            try:
                from PIL import Image, ImageOps, ImageSequence, features
                codec = (Image, ImageOps, ImageSequence) if features.check('webp') else False
            except ImportError:
                codec = False
        if codec is False:
            print('图片优化需要 Pillow；本次保留原图。可运行 python -m pip install -r requirements-images.txt。')
            continue
        Image, ImageOps, ImageSequence = codec
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        with Image.open(source) as opened:
            loop = opened.info.get('loop', 1)
            frames, durations = [], []
            for frame in ImageSequence.Iterator(opened):
                durations.append(frame.info.get('duration', 100))
                frames.append(ImageOps.exif_transpose(frame).convert('RGBA'))
            width, height = frames[0].size
        entry = {'recipe': RECIPE, 'source_hash': digest, 'width': width, 'height': height, 'variants': []}
        for target_width in sorted({min(w, width) for w in WIDTHS[kind]}):
            size = target_width, max(1, round(height * target_width / width))
            resized = [frame.resize(size, Image.Resampling.LANCZOS) for frame in frames]
            relative_output = f'assets/optimized/{kind}-{digest[:12]}-{RECIPE}-{target_width}.webp'
            target = root / relative_output
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix('.tmp')
            options = {'quality': 82, 'method': 6}
            if len(resized) > 1:
                options.update(save_all=True, append_images=resized[1:], duration=durations, loop=loop)
            resized[0].save(temporary, format='WEBP', **options)
            temporary.replace(target)
            entry['variants'].append({'path': '/' + relative_output, 'width': size[0], 'height': size[1]})
        current[kind] = entry
    manifest = root / MANIFEST
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(current, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf8')
    return {MANIFEST} | {variant['path'].lstrip('/') for entry in current.values() for variant in entry['variants']}
