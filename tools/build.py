"""Build static blog pages with optional image optimization."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from html import escape
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import shutil
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

try:
    from .content import load_site
    from .images import favicon_url, image_variants, optimize_favicon, optimize_home_images
    from .locking import workflow_lock
except ImportError:
    from content import load_site
    from images import favicon_url, image_variants, optimize_favicon, optimize_home_images
    from locking import workflow_lock

ROOT = Path(__file__).resolve().parents[1]
SITE = json.loads((ROOT / 'content/site.json').read_text(encoding='utf8'))
MESSAGES = json.loads((ROOT / 'content/ui.json').read_text(encoding='utf8'))
POSTS = {unquote(p['url']): p for p in SITE['posts']}


def message(key, **params):
    return MESSAGES[key]['en'].format(**params)


def ui(key, **params):
    values = escape(json.dumps(params, ensure_ascii=False), quote=True)
    return f'<span data-i18n="{key}" data-i18n-params="{values}">{escape(message(key, **params))}</span>'


def ui_attr(attribute, key, **params):
    values = escape(json.dumps(params, ensure_ascii=False), quote=True)
    return f'{attribute}="{escape(message(key, **params), quote=True)}" data-i18n-{attribute}="{key}" data-i18n-{attribute}-params="{values}"'


def topic_label(post):
    return ui('topic.' + topic(post)[1])

ICONS = {
    'arrow': '<path d="M5 12h14m-6-6 6 6-6 6"/>',
    'up-right': '<path d="M7 17 17 7M7 7h10v10"/>',
    'down': '<path d="M12 4v16m-6-6 6 6 6-6"/>',
    'chevrons-down': '<path d="m6 5 6 6 6-6M6 13l6 6 6-6"/>',
    'search': '<circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 4.5 4.5"/>',
    'sun': '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
    'moon': '<path d="M20.2 14A8.5 8.5 0 0 1 10 3.8 8.5 8.5 0 1 0 20.2 14Z"/>',
    'menu': '<path d="M4 7h16M4 12h16M4 17h16"/>',
    'close': '<path d="m6 6 12 12M6 18 18 6"/>',
    'github': '<path d="M9 19c-4.3 1.3-4.3-2.3-6-2.8M15 22v-3.5c0-1 .1-1.5-.5-2 3.3-.4 6.7-1.6 6.7-7.4a5.6 5.6 0 0 0-1.5-3.9A5.3 5.3 0 0 0 19.5 1S18.3.6 15 2.5a13.4 13.4 0 0 0-6 0C5.7.6 4.5 1 4.5 1a5.3 5.3 0 0 0-.2 4.2 5.6 5.6 0 0 0-1.5 3.9c0 5.8 3.4 7 6.7 7.4-.5.5-.6 1.2-.5 2V22"/>',
    'clock': '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.5 2"/>',
    'grid': '<rect x="3" y="3" width="6.5" height="6.5" rx="1"/><rect x="14.5" y="3" width="6.5" height="6.5" rx="1"/><rect x="3" y="14.5" width="6.5" height="6.5" rx="1"/><rect x="14.5" y="14.5" width="6.5" height="6.5" rx="1"/>',
    'archive': '<rect x="3" y="3" width="18" height="5" rx="1"/><path d="M5 8v12h14V8M10 12h4"/>',
    'tag': '<path d="m20 13-7 7a2 2 0 0 1-2.8 0L3 12.8V3h9.8l7.2 7.2a2 2 0 0 1 0 2.8Z"/><circle cx="7.5" cy="7.5" r=".8"/>',
    'book': '<path d="M12 5c-3-2-7-2-10 0v15c3-2 7-2 10 0 3-2 7-2 10 0V5c-3-2-7-2-10 0Zm0 0v15"/>',
    'code': '<path d="m8 7-5 5 5 5m8-10 5 5-5 5M14 4l-4 16"/>',
}


def icon(name, cls=''):
    return f'<svg class="icon {cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>'


def topic(post):
    slug = post['slug']
    if any(s in slug for s in ['machine-learning', 'Moe', '人工智能']):
        return '人工智能', 'intelligence', '01'
    if any(s in slug for s in ['分布式', '数据库', 'Linux', '计算机网络']):
        return '计算机系统', 'systems', '02'
    if any(s in slug for s in ['算法', 'LeetCode', '背包', '单调', '二叉', '最短']):
        return '算法与数据结构', 'algorithms', '03'
    if '图形' in slug:
        return '计算机图形学', 'graphics', '04'
    if 'C-Notes' in slug:
        return '编程语言', 'code', '05'
    if 'writeup' in slug:
        return '安全与实践', 'security', '06'
    return '阅读与记录', 'notes', '07'


def post_for(url):
    return POSTS[unquote(url)]


class FirstArticleImage(HTMLParser):
    """Read the first actual image, including common lazy-loading markup."""
    def __init__(self):
        super().__init__()
        self.source = None

    def handle_starttag(self, tag, attrs):
        if tag != 'img' or self.source is not None:
            return
        attrs = dict(attrs)
        self.source = (attrs.get('data-src') or attrs.get('data-original') or attrs.get('src') or '').strip() or None


def article_cover(post):
    """Derive covers on every build; no per-article cover field is required."""
    fallback = f'/assets/covers/{topic(post)[1]}.svg'
    parser = FirstArticleImage()
    parser.feed(post.get('body') or '')
    source = parser.source
    if not source:
        return {'src': fallback, 'fallback': fallback, 'article_image': False}
    aliases = SITE.get('image_aliases', {})
    source = aliases.get(source) or aliases.get(source.rsplit('/', 1)[-1]) or source
    parsed = urlsplit(urljoin(SITE['url'] + post['url'], source))
    if parsed.scheme == 'data' and source.lower().startswith('data:image/'):
        return {'src': source, 'fallback': fallback, 'article_image': True}
    if parsed.scheme not in ('http', 'https'):
        return {'src': fallback, 'fallback': fallback, 'article_image': False}
    if parsed.netloc.lower() == urlsplit(SITE['url']).netloc.lower():
        path = (ROOT / unquote(parsed.path).lstrip('/')).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            # A missing first image must not silently select a different image.
            return {'src': fallback, 'fallback': fallback, 'article_image': False}
        parsed = parsed._replace(scheme='', netloc='')
    source = urlunsplit(parsed._replace(path=quote(parsed.path, safe="/%:@!$&'()*+,;=-._~")))
    return {'src': source, 'fallback': fallback, 'article_image': True}


def navigation(active):
    links = [('/', 'nav.home', 'home'), ('/archives/', 'nav.archive', 'archive'), ('/tags/', 'nav.tags', 'tags'), ('/about/', 'nav.about', 'about')]
    nav = ''.join(f'<a href="{url}" class="nav-link{" is-active" if key == active else ""}"{chr(32) + "aria-current=page" if key == active else ""}>{ui(label)}</a>' for url, label, key in links)
    return f'''<a class="skip-link" href="#main-content">{ui('nav.skip')}</a>
    <header class="site-header"><div class="header-inner">
    <a class="brand" href="/" {ui_attr('aria-label', 'nav.brand')}><span class="brand-symbol" aria-hidden="true">&lt;/&gt;</span><span>doovvv<span class="brand-dot">_</span></span></a>
    <nav id="site-nav" class="site-nav" {ui_attr('aria-label', 'nav.label')}>{nav}</nav>
    <div class="header-actions"><button class="icon-button search-toggle" {ui_attr('aria-label', 'search.open')} {ui_attr('title', 'search.hint')}>{icon('search')}</button>
    <button class="language-toggle" type="button" aria-label="Switch to Chinese" title="Switch to Chinese">中文</button>
    <span class="header-divider"></span><button class="icon-button theme-toggle" {ui_attr('aria-label', 'theme.dark')} {ui_attr('title', 'theme.dark')}>{icon('sun', 'sun-icon')}{icon('moon', 'moon-icon')}</button>
    <a class="github-link icon-button" href="https://github.com/doovvv" target="_blank" rel="noopener noreferrer" aria-label="GitHub">{icon('github')}</a>
    <button class="icon-button menu-toggle" {ui_attr('aria-label', 'menu.open')} aria-expanded="false" aria-controls="site-nav">{icon('menu')}</button></div></div></header>'''


def footer():
    return f'''<footer class="site-footer"><div class="footer-main"><a class="brand" href="/">doovvv<span class="brand-dot">.</span></a>
    <p>{ui('footer.tagline')}</p><a href="https://github.com/doovvv" target="_blank" rel="noopener noreferrer">{ui('footer.github')} {icon('up-right')}</a></div>
    <div class="footer-bottom">{ui('footer.copyright', year=datetime.now().year)}<a href="#top">{ui('footer.top')}</a></div></footer>'''


def search_dialog():
    return f'''<dialog id="search-dialog" class="search-dialog" aria-labelledby="search-title"><div class="search-heading"><h2 id="search-title">{ui('search.title')}</h2><button class="icon-button search-close" {ui_attr('aria-label', 'search.close')}>{icon('close')}</button></div>
    <form class="search-form" role="search"><label class="sr-only" for="search-input">{ui('search.label')}</label>{icon('search')}<input id="search-input" type="search" {ui_attr('placeholder', 'search.placeholder')} autocomplete="off"><kbd>ESC</kbd></form>
    <div id="search-status" class="search-status" role="status" aria-live="polite" data-i18n="search.initial" data-i18n-params='{{"count":{len(SITE['posts'])}}}'>{message('search.initial', count=len(SITE['posts']))}</div><div id="search-results" class="search-results"></div></dialog>'''


def optimized_options(kind, sizes=None):
    entry = image_variants(ROOT, kind)
    if not entry:
        return None
    srcset = ', '.join(f'{item["path"]} {item["width"]}w' for item in entry['variants'])
    if sizes is None:
        ratio = entry['width'] / entry['height']
        sizes = f'max(100vw, {650 * ratio:.2f}px, {100 * ratio:.2f}vh)'
    return srcset, sizes


def optimized_source(kind, sizes=None):
    options = optimized_options(kind, sizes)
    if not options:
        return ''
    srcset, sizes = options
    return f'<source type="image/webp" srcset="{escape(srcset, quote=True)}" sizes="{escape(sizes, quote=True)}">'


def hero_preload():
    options = optimized_options('hero')
    if not options:
        return ''
    srcset, sizes = options
    first = image_variants(ROOT, 'hero')['variants'][0]['path']
    return f'<link rel="preload" as="image" type="image/webp" href="{first}" imagesrcset="{escape(srcset, quote=True)}" imagesizes="{escape(sizes, quote=True)}" fetchpriority="high">'


def layout(title, description, url, content, active='home', kind='page', extra=''):
    canonical = SITE['url'] + quote(unquote(url), safe='/')
    favicon = favicon_url(ROOT)
    favicon_type = ' type="image/png" sizes="64x64"' if favicon.endswith('.png') else ''
    extra = '<script>window.BLOG_IMAGE_ALIASES=' + json.dumps(SITE.get('image_aliases', {}), ensure_ascii=True) + ';</script>' + extra
    title_key = {'home':'page.home', 'archive':'page.archive', 'tags':'page.tags', 'about':'page.about'}.get(kind)
    if kind == 'tag' and '选修' in unquote(url):
        title_key = 'page.electives'
    title_text = message(title_key) if title_key else title + ' | doovvv'
    title_marker = f' data-i18n="{title_key}"' if title_key else ''
    description_key = 'profile.meta' if kind == 'about' else 'page.description'
    description_text = description if kind == 'post' else message(description_key)
    description_marker = '' if kind == 'post' else f' data-i18n-content="{description_key}"'
    return f'''<!doctype html>
<html lang="en" data-language="en" data-theme="light"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light dark"><meta name="theme-color" content="#ffffff">
<title{title_marker}>{escape(title_text)}</title><meta name="description" content="{escape(description_text, quote=True)}"{description_marker}><link rel="canonical" href="{canonical}"><meta property="og:title" content="{escape(title_text, quote=True)}"{f' data-i18n-content="{title_key}"' if title_key else ''}><meta property="og:description" content="{escape(description_text, quote=True)}"{description_marker}><meta property="og:type" content="{'article' if kind == 'post' else 'website'}"><meta property="og:url" content="{canonical}"><meta property="og:image" content="{SITE['url']}/assets/social-card.jpg"><meta property="og:image:type" content="image/jpeg"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
{hero_preload() if kind == 'home' and url == '/' else ''}<link rel="icon"{favicon_type} href="{escape(favicon, quote=True)}"><link rel="preload" href="/assets/fonts/ibm-plex-mono-bold.ttf" as="font" type="font/ttf" crossorigin><script>try{{const t=localStorage.getItem('doovvv-theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t;const l=localStorage.getItem('doovvv-language');if(l==='en'||l==='zh-CN'){{document.documentElement.lang=l;document.documentElement.dataset.language=l}}}}catch(e){{}}</script><link rel="stylesheet" href="/assets/site.css"><script src="/assets/ui-messages.js" defer></script><script src="/assets/i18n.js" defer></script><script src="/assets/site.js" defer></script>{extra}</head>
<body class="page-{kind}" id="top">{navigation(active)}<main id="main-content">{content}</main>{footer()}{search_dialog()}<button class="back-top icon-button" {ui_attr('aria-label', 'back.top')}>{icon('arrow')}</button></body></html>'''


def card(post, index):
    label, category, number = topic(post)
    cover = article_cover(post)
    cover_class = ' article-cover' if cover['article_image'] else ''
    cover_kind = 'article' if cover['article_image'] else 'default'
    read_label = ui_attr('aria-label', 'cover.read', title=post['title'])
    return f'''<article class="article-card"><a class="card-cover cover-{category}{cover_class}" data-cover-kind="{cover_kind}" href="{post['url']}" {read_label}><img src="{escape(cover['src'], quote=True)}" data-cover-fallback="{cover['fallback']}" alt="" loading="lazy" width="720" height="420"><span class="cover-category">{topic_label(post)}</span><span class="cover-open">{icon('up-right')}</span></a>
    <div class="card-content"><div class="card-meta">{topic_label(post)}<time datetime="{post['date'][:10]}">{post['date'][:10].replace('-', '.')}</time></div>
    <h3><a href="{post['url']}">{escape(post['title'])}</a></h3><p lang="zh-CN">{escape(post['excerpt'])}</p><div class="card-bottom"><span>{icon('clock')}{ui('note.minutes', count=post['minutes'])}</span><a href="{post['url']}" {read_label}>{ui('note.read')} {icon('arrow')}</a></div></div></article>'''


def pagination(page):
    if not page.get('pagination'):
        return ''
    parts = []
    for item in page['pagination']:
        label = item['label']
        displayed = ui('pagination.next') if label == '下一页' else ui('pagination.previous') if label == '上一页' else escape(label)
        if item['href']:
            accessible = ui_attr('aria-label', 'pagination.next' if label == '下一页' else 'pagination.previous') if label in ('下一页', '上一页') else ui_attr('aria-label', 'pagination.page', page=label)
            parts.append(f'<a href="{item["href"]}" {accessible}>{displayed}</a>')
        else:
            parts.append(f'<span class="{"current" if item["current"] else "gap"}" {"aria-current=page" if item["current"] else ""}>{displayed}</span>')
    return '<nav class="pagination" ' + ui_attr('aria-label', 'pagination.label') + '>' + ''.join(parts) + '</nav>'


def hero():
    background = ROOT / 'assets/images/mountain-day.jpg'
    version = '?v=' + hashlib.sha256(background.read_bytes()).hexdigest()[:12] if background.is_file() else ''
    return f'''<section class="hero" aria-labelledby="hero-title"><picture class="hero-backdrop">{optimized_source('hero')}<img class="hero-background" src="/assets/images/mountain-day.jpg{version}" alt="" width="2200" height="1468" fetchpriority="high" decoding="async"></picture>
    <div class="hero-inner"><div class="hero-intro"><p class="hero-greeting">{ui('hero.greeting')}</p><h1 id="hero-title">{ui('hero.im')} <strong class="hero-name">doovvv</strong></h1><p class="hero-subtitle">{ui('hero.subtitle')}</p>
    <div class="hero-socials"><a href="https://github.com/doovvv" target="_blank" rel="noopener noreferrer" {ui_attr('aria-label', 'social.github')}>{icon('github')}</a><a href="/archives/" {ui_attr('aria-label', 'social.notes')}>{icon('book')}</a><a href="/about/" {ui_attr('aria-label', 'social.about')}>{icon('code')}</a></div></div>
    <a class="hero-portrait" href="/about/" {ui_attr('aria-label', 'social.about')}><picture>{optimized_source('avatar', '(max-width:600px) 160px, (max-width:800px) 220px, (max-width:1100px) 280px, 340px')}<img src="/assets/images/avatar.gif" {ui_attr('alt', 'hero.avatar')} width="940" height="940" decoding="async"></picture></a></div>
    <a class="hero-bottom" href="#notes" {ui_attr('aria-label', 'hero.scroll')}>{ui('hero.caption')}{icon('chevrons-down')}</a></section>'''


def featured():
    selected = [next((p for p in SITE['posts'] if key in p['url']), SITE['posts'][0]) for key in ['machine-learning', '分布式', '算法模板']]
    slides = []
    for i, post in enumerate(selected):
        cover = article_cover(post)
        cover_class = ' article-cover' if cover['article_image'] else ''
        cover_kind = 'article' if cover['article_image'] else 'default'
        slides.append(f'''<article class="featured-slide" {'hidden' if i else ''} data-slide="{i}"><a class="featured-image{cover_class}" data-cover-kind="{cover_kind}" href="{post['url']}" {ui_attr('aria-label', 'cover.read', title=post['title'])} tabindex="{'-1' if i else '0'}"><img src="{escape(cover['src'], quote=True)}" data-cover-fallback="{cover['fallback']}" alt="" loading="lazy" width="1100" height="800"></a><div class="featured-content"><div class="eyebrow">{ui('featured.note')}<span class="slide-number">0{i+1} / 03</span></div><span class="featured-category">{topic_label(post)}</span><h3><a href="{post['url']}">{escape(post['title'])}</a></h3><p lang="zh-CN">{escape(post['excerpt'])}</p><a class="text-link" href="{post['url']}">{ui('note.continue')} {icon('up-right')}</a></div></article>''')
    controls = ''.join(f'<button class="slide-dot{" active" if i == 0 else ""}" {ui_attr("aria-label", "featured.select", count=i+1)} aria-pressed="{"true" if i == 0 else "false"}" data-slide-to="{i}"><span>0{i+1}</span></button>' for i in range(3))
    return '<section class="featured-section" aria-labelledby="featured-title"><div class="section-label"><p class="eyebrow">' + ui('featured.eyebrow') + '</p><h2 id="featured-title">' + ui('featured.title') + '</h2><span class="section-rule"></span><p>' + ui('featured.description') + '</p></div><div class="featured">' + ''.join(slides) + '<div class="featured-controls">' + controls + '</div></div></section>'


def home(page):
    is_root = page['file'] == 'index.html'
    body = hero() if is_root else page_heading('notes.notebook', 'notes.moreTitle', 'notes.moreDescription')
    body += '<div class="page-container home-content" id="notes">'
    if is_root:
        body += featured()
    body += f'''<section class="notes-section"><div class="section-heading"><div><div class="eyebrow">{ui('notes.eyebrow')}<span class="small-count">{len(SITE['posts'])}</span></div><h2>{ui('notes.title')}<span class="heading-dot">.</span></h2><span class="section-rule"></span></div><a class="text-link" href="/archives/">{ui('notes.archive')} {icon('up-right')}</a></div>
    <div class="notes-toolbar"><span>{icon('grid')}{ui('notes.tagline')}</span><span class="toolbar-order">{ui('notes.order')} {icon('down')}</span></div><div class="article-grid" id="article-grid">'''
    body += ''.join(card(post_for(url), i) for i, url in enumerate(page['posts'])) + '</div>' + pagination(page) + '</section>'
    body += f'''<section class="about-strip"><div class="section-label"><div class="eyebrow">{ui('about.eyebrow')}</div><h2>{ui('about.here')}</h2><span class="section-rule"></span></div><div><h3>{ui('about.quote')}</h3><p>{ui('about.description')}</p><div class="topic-chips">{ui('interest.cs')}{ui('interest.algorithms')}{ui('interest.systems')}</div><a class="text-link" href="/about/">{ui('about.meet')} {icon('up-right')}</a></div></section></div>'''
    return body


def page_heading(eyebrow, title, description, title_params=None, description_params=None, raw_title=None):
    heading = escape(raw_title) if raw_title is not None else ui(title, **(title_params or {}))
    return f'<section class="page-heading page-container"><div class="eyebrow">{ui(eyebrow)}</div><h1>{heading}<span class="heading-dot">.</span></h1><span class="section-rule"></span><p>{ui(description, **(description_params or {}))}</p></section>'


def archive(page):
    parts = page['file'].split('/')
    period = ' / '.join(p for p in parts[1:] if p.isdigit() and len(p) in (2, 4))
    result = page_heading('archive.eyebrow', 'archive.period' if period else 'archive.title', 'archive.description', title_params={'period': period} if period else None)
    years = sorted({p['date'][:4] for p in SITE['posts']}, reverse=True)
    filters = '<a href="/archives/">' + ui('archive.all') + '</a>' + ''.join(f'<a href="/archives/{year}/">{year}</a>' for year in years)
    result += f'<div class="page-container archive-layout"><aside class="archive-summary"><span class="big-number">{len(SITE["posts"])}<span>{ui("archive.count")}</span></span><p>{ui("archive.since")}</p><nav class="year-filters" {ui_attr("aria-label", "archive.years")}>{filters}</nav><div class="archive-note">{ui("archive.note")}</div></aside><div class="timeline">'
    year = None
    for url in page['posts']:
        post = post_for(url)
        if post['date'][:4] != year:
            year = post['date'][:4]
            result += f'<h2 class="timeline-year">{year}<span>{ui("archive.year")}</span></h2>'
        result += f'<a class="timeline-entry" href="{post["url"]}"><time datetime="{post["date"][:10]}">{post["date"][5:10].replace("-", ".")}</time><div>{topic_label(post)}<h3>{escape(post["title"])}</h3></div>{icon("up-right")}</a>'
    return result + pagination(page) + '</div></div>'


def tag_page(page):
    if page['kind'] == 'tags':
        result = page_heading('tags.index', 'tags.title', 'tags.description') + '<div class="page-container tag-grid">'
        for i, (url, name) in enumerate(SITE['tag_names'].items()):
            count = sum(any(unquote(t['url']) == url for t in p['tags']) for p in SITE['posts'])
            label = ui('tags.electives') if name == '选修' else escape(name)
            result += f'<a class="tag-card" href="{quote(url, safe="/")}"><span class="tag-number">0{i+1}</span>{icon("tag")}<h2>{label}</h2><div>{ui("tags.count", count=f"{count:02d}")}{icon("up-right")}</div></a>'
        return result + '</div>'
    name = SITE['tag_names'].get(unquote(page['url']), page['url'].split('/')[-2])
    result = page_heading('tags.index', 'tags.electives' if name == '选修' else None, 'tags.topicDescription', raw_title=None if name == '选修' else name, description_params={'count':len(page['posts'])})
    return result + '<div class="page-container"><a class="back-link" href="/tags/">' + ui('tags.all') + '</a><div class="article-grid" id="article-grid">' + ''.join(card(post_for(url), i) for i, url in enumerate(page['posts'])) + '</div></div>'


def post_page(post):
    date = post['date'][:10].replace('-', '.')
    tags = ''.join(f'<a href="{t["url"]}">#{ui("tags.electives") if t["name"] == "选修" else escape(t["name"])}</a>' for t in post['tags'])
    toc = post['toc'] or '<p class="toc-empty">' + ui('article.tocEmpty') + '</p>'
    result = f'''<section class="article-heading page-container"><a class="back-link" href="/archives/">{ui('article.back')}</a><div class="eyebrow">{topic_label(post)} / {ui('notes.notebook')}</div><h1 lang="zh-CN">{escape(post['title'])}</h1><div class="article-meta"><a href="/about/" class="author-meta"><span class="author-initial">d.</span>doovvv</a><span class="meta-divider"></span><time datetime="{post['date'][:10]}">{date}</time><span>{icon('clock')}{ui('note.minutes', count=post['minutes'])}</span></div><div class="article-tags">{tags}</div></section>
    <div class="reading-layout page-container"><article class="reading-article" {ui_attr('aria-label', 'article.body')}><div class="article-original" lang="zh-CN">{post['body']}</div><div class="article-end">{ui('article.end')}<i></i>{icon('code')}</div><div class="article-license">{ui('article.updated', date=post['updated'][:10])}<span>{ui('article.licenseBefore')} <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/" target="_blank" rel="noopener noreferrer">CC BY-NC-SA 4.0</a> {ui('article.licenseAfter')}</span></div>'''
    result += '<nav class="article-neighbors" ' + ui_attr('aria-label', 'article.neighbors') + '>'
    for direction, title in [('prev', 'article.previous'), ('next', 'article.next')]:
        neighbor = post[direction]
        result += f'<a href="{neighbor["url"]}">{ui(title)}<strong>{escape(neighbor["title"])}</strong>{icon("arrow")}</a>' if neighbor else '<span></span>'
    result += f'''</nav><section class="comments-section" aria-labelledby="comments-heading"><div class="section-heading"><h2 id="comments-heading">{ui('article.comments')}<span class="heading-dot">.</span></h2></div><button class="button button-outline load-comments">{ui('article.loadComments')} {icon('arrow')}</button><p class="comment-status" role="status"></p><div id="valine-comments"></div></section></article><aside class="reading-sidebar"><div class="toc-heading">{ui('article.toc')}{icon('book')}</div><div lang="zh-CN">{toc}</div><div class="reading-progress"><div>{ui('article.progress')}<span id="reading-percent">0%</span></div><div class="progress-track"><span id="reading-progress-bar"></span></div></div></aside></div>'''
    return result


def about():
    sections = [('overview', '01'), ('experience', '02'), ('education', '03'), ('skills', '04'), ('writing', '05')]
    menu = ''.join(f'<a href="#{name}" class="profile-nav-link{" is-active" if i == 0 else ""}"{" aria-current=location" if i == 0 else ""}><span class="profile-nav-number" aria-hidden="true">{number}</span>{ui("profile.nav." + name)}</a>' for i, (name, number) in enumerate(sections))
    result = f'''<div class="profile-shell"><aside class="profile-rail"><a class="profile-identity" href="#overview"><img class="profile-identity-avatar" src="{escape(favicon_url(ROOT), quote=True)}" alt="" aria-hidden="true" width="43" height="43" decoding="async"><span><strong>doovvv</strong><small>{ui('profile.rail.label')}</small></span></a><nav class="profile-nav" {ui_attr('aria-label', 'profile.nav.label')}>{menu}</nav><a class="profile-rail-link" href="https://github.com/doovvv" target="_blank" rel="noopener noreferrer">{icon('github')} GitHub {icon('up-right')}</a></aside>
    <div class="profile-main"><section class="profile-section profile-overview" id="overview" aria-labelledby="profile-name"><div class="profile-hero"><div class="profile-intro"><p class="eyebrow">{ui('profile.eyebrow')}</p><h1 id="profile-name">{ui('profile.name.first')}<strong>{ui('profile.name.last')}</strong></h1><div class="profile-name-note">{ui('profile.name.note')}</div><p class="profile-role">{ui('profile.role')}</p><p class="profile-bio">{ui('profile.bio')}</p><div class="profile-actions"><a class="button button-primary" href="#experience">{ui('profile.explore')} {icon('down')}</a><a class="profile-social" href="https://github.com/doovvv" target="_blank" rel="noopener noreferrer">{icon('github')} GitHub {icon('up-right')}</a></div></div><div class="profile-portrait"><picture>{optimized_source('avatar', '(max-width:600px) 64px, (max-width:1100px) 160px, 220px')}<img src="/assets/images/avatar.gif" {ui_attr('alt','hero.avatar')} width="940" height="940" decoding="async"></picture><span class="profile-portrait-caption">doovvv / {ui('profile.portrait')}</span></div></div>
    </section>'''

    def heading(number, name, description):
        return f'<div class="profile-section-heading"><p class="eyebrow">{number} / {ui("profile.nav." + name)}</p><h2 id="profile-' + name + '-title">' + ui('profile.' + name + '.title') + '</h2><p>' + ui(description) + '</p></div>'

    result += '<section class="profile-section" id="experience" aria-labelledby="profile-experience-title">' + heading('02', 'experience', 'profile.experience.intro') + '<div class="profile-timeline">'
    for key in ['tencent', 'bytedance']:
        prefix = 'profile.' + key
        bullets = ''.join('<li>' + ui(prefix + '.point' + str(i)) + '</li>' for i in range(1, 4))
        tags = {'tencent': ['Python', 'LangGraph', 'MCP', 'RAG', 'SSE'], 'bytedance': ['Flink CDC', 'MySQL', 'StarRocks', 'CI/CD']}[key]
        chips = ''.join('<span>' + escape(tag) + '</span>' for tag in tags)
        extension = 'png' if key == 'tencent' else 'svg'
        result += f'<article class="profile-job"><div class="profile-company-mark {key}" aria-hidden="true"><img src="/assets/brands/{key}.{extension}" alt="" width="44" height="44" loading="lazy"></div><div class="profile-job-main"><div class="profile-job-header"><div><h3>{ui(prefix + ".company")}</h3><p class="profile-job-role">{ui(prefix + ".role")}</p></div><span class="profile-period">{ui(prefix + ".period")}</span></div><p class="profile-job-context">{ui(prefix + ".team")}</p><ul class="profile-job-points">{bullets}</ul><div class="profile-tech">{chips}</div>'
        if key == 'tencent':
            result += '<div class="profile-recognition">' + icon('up-right') + ui('profile.tencent.award') + '</div>'
        result += '</div></article>'
    result += '</div></section>'

    result += '<section class="profile-section" id="education" aria-labelledby="profile-education-title">' + heading('03', 'education', 'profile.education.intro') + '<div class="profile-education-grid">'
    for key in ['nju', 'sysu']:
        prefix = 'profile.' + key
        extension = 'svg' if key == 'nju' else 'png'
        result += f'<article class="profile-school"><div class="profile-school-top"><span class="profile-school-mark" aria-hidden="true"><img src="/assets/brands/{key}.{extension}" alt="" width="80" height="80" loading="lazy"></span><span class="profile-period">{ui(prefix + ".period")}</span></div><h3>{ui(prefix + ".name")}</h3><p class="profile-degree">{ui(prefix + ".degree")}</p><p class="profile-school-detail">{ui(prefix + ".school")}</p></article>'
    result += '</div></section>'

    result += '<section class="profile-section" id="skills" aria-labelledby="profile-skills-title">' + heading('04', 'skills', 'profile.skills.intro') + '<div class="profile-tool-list">'
    for symbol, label in [('go', 'Go'), ('python', 'Python'), ('mysql', 'MySQL'), ('redis', 'Redis'), ('apachekafka', 'Kafka'), ('git', 'Git'), ('linux', 'Linux'), ('docker', 'Docker')]:
        result += f'<figure class="profile-tool"><img src="/assets/brands/{symbol}.svg" alt="" width="48" height="48" loading="lazy"><figcaption>{label}</figcaption></figure>'
    result += '</div><div class="profile-skills-grid">'
    groups = [('languages', 'code', ['Go', 'Python', 'SQL']), ('ai', 'grid', ['LangGraph', 'LangChain', 'MCP', 'RAG']), ('data', 'archive', ['MySQL', 'Redis', 'Kafka', 'Flink CDC', 'StarRocks']), ('engineering', 'book', ['Git', 'Linux', 'Docker', 'RPC', 'CI/CD'])]
    for key, symbol, items in groups:
        prefix = 'profile.skills.' + key
        result += '<article class="profile-skill"><div class="profile-skill-title">' + icon(symbol) + '<h3>' + ui(prefix + '.title') + '</h3></div><p>' + ui(prefix + '.description') + '</p><div class="profile-tech">' + ''.join('<span>' + escape(item) + '</span>' for item in items) + '</div></article>'
    result += '</div></section>'

    result += '<section class="profile-section profile-writing" id="writing" aria-labelledby="profile-writing-title">' + heading('05', 'writing', 'profile.writing.intro') + '<div class="profile-note-list">'
    for i, key in enumerate(['machine-learning', '分布式', '算法模板'], 1):
        post = next((p for p in SITE['posts'] if key in unquote(p['url'])), None)
        if post:
            result += f'<a href="{post["url"]}" class="profile-note"><span class="profile-note-index">0{i}</span><div><span class="profile-note-topic">{topic_label(post)}</span><h3>{escape(post["title"])}</h3></div>{icon("up-right")}</a>'
    result += '</div><a href="/archives/" class="text-link">' + ui('profile.writing.all') + ' ' + icon('arrow') + '</a></section></div></div>'
    return result


def write_covers():
    directory = ROOT / 'assets/covers'
    directory.mkdir(parents=True, exist_ok=True)
    variants = {
        'intelligence': ('NEURAL / SYSTEMS', 'f(x)', '<g stroke="#7099e8" opacity=".75">' + ''.join(f'<path d="M{x} {y} L{xx} {yy}"/>' for x, y in [(130, 90), (130, 210), (130, 330)] for xx, yy in [(320, 120), (320, 300)]) + ''.join(f'<path d="M320 {y} L510 210"/>' for y in [120, 300]) + '</g>' + ''.join(f'<circle cx="{x}" cy="{y}" r="11" fill="#eff4ff" stroke="#1d4ed8" stroke-width="2"/>' for x, y in [(130, 90), (130, 210), (130, 330), (320, 120), (320, 300), (510, 210)])),
        'systems': ('DISTRIBUTED / SYSTEMS', '{ }', '<g fill="#f5f8ff" stroke="#5080dc" stroke-width="1.5"><path d="m230 110 130-70 130 70-130 70Zm0 65 130 70 130-70M230 240l130 70 130-70M230 305l130 70 130-70"/><path d="M230 110v195m130-125v195m130-265v195"/></g>'),
        'algorithms': ('LOGIC / STRUCTURE', 'O(n)', '<g stroke="#5080dc" fill="none" stroke-width="1.5"><path d="M360 70 210 200l150 130 150-130ZM210 200H70m440 0h140M360 70v260"/><circle cx="360" cy="70" r="12"/><circle cx="210" cy="200" r="12"/><circle cx="510" cy="200" r="12"/><circle cx="360" cy="330" r="12"/></g>'),
        'graphics': ('LIGHT / GEOMETRY', 'xyz', '<g stroke="#5080dc" fill="none"><ellipse cx="360" cy="210" rx="150" ry="150"/><ellipse cx="360" cy="210" rx="60" ry="150"/><ellipse cx="360" cy="210" rx="150" ry="60"/><path d="M210 210h300M360 60v300m-106-256 212 212m0-212L254 316"/></g>'),
        'code': ('LANGUAGE / EXPRESSION', '</>', '<g fill="none" stroke="#3b6dcc" stroke-width="3"><path d="m280 130-95 80 95 80m160-160 95 80-95 80M405 100l-90 220"/></g>'),
        'security': ('SECURITY / PRACTICE', '0x', '<g fill="none" stroke="#5080dc" stroke-width="2"><path d="M360 65 495 120v100c0 70-70 115-135 145-65-30-135-75-135-145V120Z"/><rect x="310" y="180" width="100" height="85" rx="7"/><path d="M330 180v-30a30 30 0 0 1 60 0v30M360 210v30"/></g>'),
        'notes': ('READ / REFLECT', '…', '<g fill="none" stroke="#5080dc" stroke-width="1.5"><path d="M230 70h190l70 70v210H230ZM420 70v70h70M275 195h170m-170 45h170m-170 45h100"/></g>'),
    }
    for key, (label, mark, shapes) in variants.items():
        source = f'''<svg xmlns="http://www.w3.org/2000/svg" width="720" height="420" viewBox="0 0 720 420"><defs><pattern id="grid" width="36" height="36" patternUnits="userSpaceOnUse"><path d="M36 0H0v36" fill="none" stroke="#789ae0" stroke-opacity=".12"/></pattern><radialGradient id="glow"><stop stop-color="#e3ecff"/><stop offset="1" stop-color="#f5f8ff"/></radialGradient></defs><rect width="720" height="420" fill="url(#glow)"/><rect width="720" height="420" fill="url(#grid)"/>{shapes}<text x="30" y="390" fill="#5271a9" font-family="monospace" font-size="12" letter-spacing="3">{escape(label)}</text><text x="680" y="45" text-anchor="end" fill="#5271a9" font-family="monospace" font-size="15">{escape(mark)}</text></svg>'''
        (directory / f'{key}.svg').write_text(source, encoding='utf8')


def _write_site():
    for page in SITE['pages']:
        kind = page['kind']
        extra = ''
        if kind == 'post':
            post = post_for(page['url'])
            body = post_page(post)
            title, description = post['title'], post['excerpt']
            extra = '<script>window.BLOG_COMMENTS=' + json.dumps(SITE.get('comments', {}), ensure_ascii=True) + ';</script>'
        elif kind == 'home':
            body, title, description = home(page), '保持好奇，认真记录', SITE['description']
        elif kind == 'archive':
            body, title, description = archive(page), '时间归档', 'doovvv 的学习与技术笔记归档'
        elif kind in ['tag', 'tags']:
            body, title, description = tag_page(page), '标签索引' if kind == 'tags' else SITE['tag_names'].get(unquote(page['url']), '标签'), '按主题探索 doovvv 的笔记'
        else:
            raise ValueError('Unsupported page kind: ' + kind)
        active = 'tags' if kind == 'tag' else kind
        output = ROOT / page['file']
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(layout(title, description, page['url'], body, active, kind, extra), encoding='utf8')
    about_dir = ROOT / 'about'
    about_dir.mkdir(exist_ok=True)
    (about_dir / 'index.html').write_text(layout('关于我', SITE['description'], '/about/', about(), 'about', 'about'), encoding='utf8')
    search = [{k: p[k] for k in ['url', 'title', 'excerpt', 'text', 'date']} for p in SITE['posts']]
    (ROOT / 'assets/search.json').write_text(json.dumps(search, ensure_ascii=False, separators=(',', ':')), encoding='utf8')
    write_covers()
    (ROOT / 'assets/ui-messages.js').write_text('window.BLOG_UI_MESSAGES=' + json.dumps(MESSAGES, ensure_ascii=False, separators=(',', ':')) + ';\n', encoding='utf8')
    (ROOT / '.nojekyll').touch()
    print(f'Built {len(SITE["pages"]) + 1} pages, {len(SITE["posts"])} searchable articles, and 7 cover illustrations.')


def _build_site(root=ROOT, include_drafts=False):
    global ROOT, SITE, POSTS, MESSAGES
    previous = ROOT, SITE, POSTS, MESSAGES
    try:
        ROOT = Path(root).resolve()
        SITE = load_site(ROOT, include_drafts=include_drafts)
        POSTS = {unquote(p['url']): p for p in SITE['posts']}
        MESSAGES = json.loads((ROOT / 'content/ui.json').read_text(encoding='utf8'))
        manifest = ROOT / 'content/generated-files.json'
        old_files = set(json.loads(manifest.read_text(encoding='utf8'))) if manifest.exists() else set()
        files = {p['file'] for p in SITE['pages']} | {'about/index.html', 'assets/search.json', 'assets/ui-messages.js', '.nojekyll'}
        files |= {'assets/covers/' + name + '.svg' for name in ['intelligence', 'systems', 'algorithms', 'graphics', 'code', 'security', 'notes']}
        files |= set(SITE['_assets'])
        # An image generated for A may still be explicitly used by public B
        # after A is withdrawn. Retain ownership until the final reference ends.
        files |= set(SITE['_public_assets']) & old_files
        files |= optimize_home_images(ROOT)
        files |= optimize_favicon(ROOT)
        def output_path(name):
            target = (ROOT / name).resolve()
            if not target.is_relative_to(ROOT) or target == ROOT or Path(name).parts[0] in ('content', 'tools', 'tests', '.git'):
                raise ValueError('Invalid generated output path: ' + name)
            return target
        for name in files | old_files:
            output_path(name)
        for name, source in SITE['_assets'].items():
            target = output_path(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        (ROOT / 'assets').mkdir(exist_ok=True)
        _write_site()
        for name in old_files - files:
            target = output_path(name)
            if target.is_file():
                target.unlink()
        manifest.write_text(json.dumps(sorted(files), ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        return SITE
    finally:
        ROOT, SITE, POSTS, MESSAGES = previous


def build_site(root=ROOT, include_drafts=False):
    with workflow_lock(root):
        return _build_site(root, include_drafts=include_drafts)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Generate blog pages from recovered and Markdown articles.')
    parser.add_argument('--drafts', action='store_true', help='Include drafts in local preview only')
    args = parser.parse_args()
    try:
        build_site(include_drafts=args.drafts)
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
