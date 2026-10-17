"""Read local Markdown sources and regenerate the blog's content indexes."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timezone, timedelta
from html import escape
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import quote, unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent / '_vendor'))
import markdown
from markdown.extensions.toc import slugify_unicode
import yaml

ZONE = timezone(timedelta(hours=8))
PAGE_SIZE = 10


class UniqueLoader(yaml.SafeLoader):
    """A typo must not silently overwrite an earlier metadata field."""


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise ValueError(f'Duplicate or invalid metadata key: {key}')
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def timestamp(value, field):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value)
    else:
        raise ValueError(f'{field} must be a date, for example 2026-10-17')
    return (parsed.replace(tzinfo=ZONE) if parsed.tzinfo is None else parsed.astimezone(ZONE)).isoformat()


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, text):
        self.parts.append(text)


def plain_text(html):
    parser = PlainText()
    parser.feed(html)
    return re.sub(r'\s+', ' ', ' '.join(parser.parts)).strip()


class ArticleAssets(HTMLParser):
    """Resolve local links without copying unrelated files or draft sources."""
    def __init__(self, root, directory, url):
        super().__init__(convert_charrefs=False)
        self.root, self.directory, self.url = root.resolve(), directory.resolve(), url
        self.output, self.assets, self.public_assets = [], {}, set()

    def link(self, value, image=False):
        parts = urlsplit(value)
        if parts.scheme in ('http', 'https', 'data', 'mailto', 'tel') or parts.netloc or not parts.path:
            return value
        if parts.scheme or '\\' in value:
            raise ValueError(f'Use an image inside the article folder instead of a local computer path: {value}')
        if parts.path.startswith('/'):
            source = (self.root / unquote(parts.path).lstrip('/')).resolve()
            if not source.is_relative_to(self.root):
                raise ValueError(f'Image path leaves the blog folder: {value}')
            if image and not source.is_file():
                raise ValueError(f'Image not found: {value}')
            if source.is_file():
                relative = source.relative_to(self.root).as_posix()
                if relative.startswith(('content/', 'tools/', 'tests/', '.')):
                    raise ValueError(f'Keep public attachments in assets or the article folder: {value}')
                self.public_assets.add(relative)
            return value
        source = (self.directory / unquote(parts.path)).resolve()
        if not source.is_relative_to(self.directory):
            raise ValueError(f'Keep attachments inside the article folder: {value}')
        if not source.is_file():
            raise ValueError(f'Image or attachment not found: {value}')
        if source.suffix.lower() in ('.md', '.markdown') or source.name.startswith('.'):
            raise ValueError(f'Link to a published article URL instead of a source file: {value}')
        relative = source.relative_to(self.directory).as_posix()
        destination = unquote(self.url).lstrip('/') + relative
        self.assets[destination] = str(source)
        suffix = ('?' + parts.query if parts.query else '') + ('#' + parts.fragment if parts.fragment else '')
        return quote('/' + destination, safe='/-._~') + suffix

    def tag(self, tag, attrs, closed=False):
        rebuilt = []
        for key, value in attrs:
            if value is not None and ((tag == 'img' and key in ('src', 'data-src', 'data-original')) or (tag == 'a' and key == 'href')):
                value = self.link(value, image=tag == 'img')
            rebuilt.append(key if value is None else f'{key}="{escape(value, quote=True)}"')
        self.output.append('<' + tag + (' ' + ' '.join(rebuilt) if rebuilt else '') + (' />' if closed else '>'))

    def handle_starttag(self, tag, attrs): self.tag(tag, attrs)
    def handle_startendtag(self, tag, attrs): self.tag(tag, attrs, True)
    def handle_endtag(self, tag): self.output.append('</' + tag + '>')
    def handle_data(self, text): self.output.append(text)
    def handle_entityref(self, name): self.output.append('&' + name + ';')
    def handle_charref(self, name): self.output.append('&#' + name + ';')
    def handle_comment(self, text): self.output.append('<!--' + text + '-->')


def read_article(path, root, include_drafts=False):
    try:
        raw = path.read_text(encoding='utf-8-sig').replace('\r\n', '\n')
        match = re.match(r'\A---\n(.*?)\n---[ \t]*(?:\n|$)(.*)\Z', raw, re.S)
        if not match:
            raise ValueError('Start the article with --- metadata ---')
        meta = yaml.load(match[1], Loader=UniqueLoader)
        if not isinstance(meta, dict):
            raise ValueError('Article metadata must contain title and date')
        allowed = {'title', 'date', 'updated', 'tags', 'draft', 'slug', 'excerpt', 'pinned', 'legacy_url'}
        unknown = set(meta) - allowed
        if unknown:
            raise ValueError('Unknown metadata: ' + ', '.join(sorted(unknown)))
        if not isinstance(meta.get('title'), str) or not meta['title'].strip():
            raise ValueError('title must be a nonempty string')
        for key in ('draft', 'pinned'):
            if key in meta and not isinstance(meta[key], bool):
                raise ValueError(key + ' must be true or false, without quotes')
        tags = meta.get('tags', [])
        if not isinstance(tags, list) or any(not isinstance(t, str) or not t.strip() for t in tags):
            raise ValueError('tags must be a list, for example [AI, 学习笔记]')
        slug = meta.get('slug', path.parent.name)
        if not isinstance(slug, str) or not re.fullmatch(r'[\w-]+', slug) or slug in ('.', '..'):
            raise ValueError('slug/folder name may contain letters, numbers, Chinese, hyphens and underscores')
        published = timestamp(meta.get('date'), 'date')
        updated = timestamp(meta.get('updated', meta['date']), 'updated')
        url = '/' + published[:10].replace('-', '/') + '/' + slug + '/'
        if 'legacy_url' in meta:
            url = unquote(meta['legacy_url'])
            if not re.fullmatch(r'/\d{4}/\d{2}/\d{2}/[\w-]+/', url):
                raise ValueError('legacy_url must be an existing article URL')
        if meta.get('draft') and not include_drafts:
            return {'url': url, '_draft': True, '_legacy_url': meta.get('legacy_url')}
        renderer = markdown.Markdown(extensions=['markdown.extensions.extra', 'markdown.extensions.toc', 'pymdownx.arithmatex'],
            extension_configs={'markdown.extensions.toc': {'slugify': slugify_unicode}, 'pymdownx.arithmatex': {'generic': True}})
        html = renderer.convert(match[2])
        assets = ArticleAssets(root, path.parent, url)
        assets.feed(html)
        html = ''.join(assets.output)
        text = plain_text(html)
        if not text and '<img' not in html:
            raise ValueError('Article body is empty')
        excerpt = meta.get('excerpt')
        if excerpt is not None and not isinstance(excerpt, str):
            raise ValueError('excerpt must be text')
        # Keep the original HTML source file outside public output; only referenced
        # attachments are copied. A draft's assets are never copied for release.
        source_files = [path.relative_to(root).as_posix()] + [Path(p).relative_to(root).as_posix() for p in assets.assets.values()]
        return {'url': url, 'file': unquote(url).lstrip('/') + 'index.html', 'slug': slug, 'title': meta['title'].strip(),
            'date': published, 'updated': updated, 'tags': list(dict.fromkeys(t.strip() for t in tags)),
            'excerpt': excerpt or text[:150] + ('…' if len(text) > 150 else ''), 'text': text,
            'body': '<div class="post-body markdown-body">' + html + '</div>',
            'toc': renderer.toc.replace('class="toc"', 'class="post-toc"') if renderer.toc_tokens else '',
            'minutes': max(1, math.ceil(len(text) / 500)), 'prev': None, 'next': None,
            '_draft': meta.get('draft', False), '_pinned': meta.get('pinned', False), '_legacy_url': meta.get('legacy_url'),
            '_assets': assets.assets, '_public_assets': assets.public_assets, '_sources': source_files}
    except (ValueError, TypeError, KeyError, yaml.YAMLError) as error:
        raise ValueError(f'{path.relative_to(root)}: {error}') from error


def pagination(base, number, total):
    if total <= 1:
        return []
    url = lambda n: base if n == 1 else base + f'page/{n}/'
    items = []
    if number > 1:
        items.append({'href': url(number - 1), 'label': '上一页', 'current': False})
    items += [{'href': None if n == number else url(n), 'label': str(n), 'current': n == number} for n in range(1, total + 1)]
    if number < total:
        items.append({'href': url(number + 1), 'label': '下一页', 'current': False})
    return items


def load_site(root, include_drafts=False):
    root = Path(root).resolve()
    site = json.loads((root / 'content/site.json').read_text(encoding='utf8'))
    original_pages = site['pages']
    posts = {unquote(p['url']): deepcopy(p) for p in site['posts']}
    legacy_urls = set(posts)
    source_urls = set()
    public_sources, public_assets, assets = set(), set(), {}
    source_root = root / 'content/posts'
    for path in sorted(source_root.glob('*/index.md')):
        if not path.resolve().is_relative_to(source_root.resolve()):
            raise ValueError(f'Article source leaves content/posts: {path}')
        article = read_article(path, root, include_drafts=include_drafts)
        key = unquote(article['url'])
        if key in source_urls or (key in legacy_urls and not article['_legacy_url']):
            raise ValueError(f'{path}: duplicate article URL {key}; use legacy_url only for a deliberate migration')
        if article['_legacy_url'] and key not in legacy_urls:
            raise ValueError(f'{path}: legacy_url does not match a recovered article')
        source_urls.add(key)
        if article['_draft'] and not include_drafts:
            continue
        assets.update(article['_assets'])
        if not article['_draft']:
            public_sources.update(article['_sources'])
            public_assets.update(article['_public_assets'])
        posts[key] = article
    sorted_posts = sorted(posts.values(), key=lambda p: timestamp(p['date'], 'date'), reverse=True)
    # Reuse every old tag URL, including historical spelling variants.
    names = {unquote(url): name for url, name in site['tag_names'].items()}
    tag_urls = {name.casefold(): url for url, name in names.items()}
    for post in sorted_posts:
        tags = []
        for tag in post['tags']:
            if isinstance(tag, dict):
                tags.append(tag)
                continue
            key = tag.casefold()
            if key not in tag_urls:
                slug = re.sub(r'\s+', '-', tag.strip().lower())
                if not re.fullmatch(r'[\w-]+', slug):
                    slug = 'tag-' + __import__('hashlib').sha256(tag.encode()).hexdigest()[:10]
                url = '/tags/' + slug + '/'
                if url in names and names[url] != tag:
                    raise ValueError('Tag URL collision: ' + tag)
                names[url], tag_urls[key] = tag, url
            tags.append({'name': tag, 'url': tag_urls[key]})
        post['tags'] = tags
    chronological = list(reversed(sorted_posts))
    for i, post in enumerate(chronological):
        neighbor = lambda p: {'url': p['url'], 'title': p['title']}
        post['prev'] = neighbor(chronological[i - 1]) if i else None
        post['next'] = neighbor(chronological[i + 1]) if i + 1 < len(chronological) else None
    pages = {}
    def page(url, kind, entries, controls=None):
        pages[url] = {'url': url, 'file': unquote(url).lstrip('/') + 'index.html', 'kind': kind,
            'posts': [p['url'] for p in entries], 'pagination': controls or []}
    def series(base, kind, entries):
        total = max(1, math.ceil(len(entries) / PAGE_SIZE))
        for n in range(1, total + 1):
            page(base if n == 1 else base + f'page/{n}/', kind, entries[(n-1)*PAGE_SIZE:n*PAGE_SIZE], pagination(base, n, total))
    for post in sorted_posts:
        page(post['url'], 'post', [post])
    original_home = next((p for p in original_pages if p['url'] == '/'), {})
    pinned = [p for p in sorted_posts if p.get('_pinned')]
    # The recovered homepage pins its resource index; preserve that existing choice.
    if original_home.get('posts') and original_home['posts'][0] != sorted_posts[0]['url']:
        first = posts.get(unquote(original_home['posts'][0]))
        if first and not first.get('_sources') and first not in pinned:
            pinned.append(first)
    series('/', 'home', pinned + [p for p in sorted_posts if p not in pinned])
    series('/archives/', 'archive', sorted_posts)
    periods = defaultdict(list)
    for post in sorted_posts:
        periods[post['date'][:4]].append(post)
        periods[post['date'][:7].replace('-', '/')].append(post)
    for period, entries in periods.items():
        series('/archives/' + period + '/', 'archive', entries)
    page('/tags/', 'tags', [])
    for url in names:
        page(url, 'tag', [p for p in sorted_posts if any(unquote(t['url']) == url for t in p['tags'])])
    for old in original_pages:
        if unquote(old['url']) not in pages:
            if old['kind'] in ('archive', 'home', 'tag'):
                page(unquote(old['url']), old['kind'], [])
            elif old['kind'] != 'post':
                pages[unquote(old['url'])] = old
    site.update(posts=sorted_posts, pages=list(pages.values()), tag_names=names,
        _assets=assets, _public_sources=sorted(public_sources), _public_assets=sorted(public_assets))
    return site
