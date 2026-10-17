"""Build the blog's static pages using only the Python standard library."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
SITE = json.loads((ROOT / 'content/site.json').read_text(encoding='utf8'))
POSTS = {unquote(p['url']): p for p in SITE['posts']}

ICONS = {
    'arrow': '<path d="M5 12h14m-6-6 6 6-6 6"/>',
    'up-right': '<path d="M7 17 17 7M7 7h10v10"/>',
    'down': '<path d="M12 4v16m-6-6 6 6 6-6"/>',
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
    links = [('/', '首页', 'home'), ('/archives/', '归档', 'archive'), ('/tags/', '标签', 'tags'), ('/2023/12/05/%E8%B5%84%E6%BA%90%E9%93%BE%E6%8E%A5/', '资源', 'resource'), ('/about/', '关于', 'about')]
    nav = ''.join(f'<a href="{url}" class="nav-link{" is-active" if key == active else ""}"{chr(32) + "aria-current=page" if key == active else ""}>{label}</a>' for url, label, key in links)
    return f'''<a class="skip-link" href="#main-content">跳到主要内容</a>
    <header class="site-header"><div class="header-inner">
    <a class="brand" href="/" aria-label="doovvv 首页"><span class="brand-symbol" aria-hidden="true">&lt;/&gt;</span><span>doovvv<span class="brand-dot">_</span></span></a>
    <nav id="site-nav" class="site-nav" aria-label="主导航">{nav}</nav>
    <div class="header-actions"><button class="icon-button search-toggle" aria-label="搜索文章" title="搜索文章（Ctrl K）">{icon('search')}</button>
    <span class="header-divider"></span><button class="icon-button theme-toggle" aria-label="切换为浅色模式" title="切换主题">{icon('sun', 'sun-icon')}{icon('moon', 'moon-icon')}</button>
    <a class="github-link icon-button" href="https://github.com/doovvv" target="_blank" rel="noopener noreferrer" aria-label="GitHub">{icon('github')}</a>
    <button class="icon-button menu-toggle" aria-label="打开导航菜单" aria-expanded="false" aria-controls="site-nav">{icon('menu')}</button></div></div></header>'''


def footer():
    return f'''<footer class="site-footer"><div class="footer-main"><a class="brand" href="/">doovvv<span class="brand-dot">.</span></a>
    <p>记录思考，保持好奇。</p><a href="https://github.com/doovvv" target="_blank" rel="noopener noreferrer">在 GitHub 找到我 {icon('up-right')}</a></div>
    <div class="footer-bottom"><span>© {datetime.now().year} doovvv · Personal notes & explorations</span><a href="#top">回到顶部 ↑</a></div></footer>'''


def search_dialog():
    return f'''<dialog id="search-dialog" class="search-dialog" aria-labelledby="search-title"><div class="search-heading"><h2 id="search-title">搜索笔记</h2><button class="icon-button search-close" aria-label="关闭搜索">{icon('close')}</button></div>
    <form class="search-form" role="search"><label class="sr-only" for="search-input">搜索标题或正文</label>{icon('search')}<input id="search-input" type="search" placeholder="搜索标题、关键词或正文…" autocomplete="off"><kbd>ESC</kbd></form>
    <div id="search-status" class="search-status" role="status" aria-live="polite">在 20 篇笔记中，寻找一个想法。</div><div id="search-results" class="search-results"></div></dialog>'''


def layout(title, description, url, content, active='home', kind='page', extra=''):
    canonical = SITE['url'] + quote(unquote(url), safe='/')
    extra = '<script>window.BLOG_IMAGE_ALIASES=' + json.dumps(SITE.get('image_aliases', {}), ensure_ascii=True) + ';</script>' + extra
    return f'''<!doctype html>
<html lang="zh-CN" data-theme="light"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light dark"><meta name="theme-color" content="#ffffff">
<title>{escape(title)} | doovvv</title><meta name="description" content="{escape(description, quote=True)}"><link rel="canonical" href="{canonical}"><meta property="og:title" content="{escape(title, quote=True)}"><meta property="og:description" content="{escape(description, quote=True)}"><meta property="og:type" content="{'article' if kind == 'post' else 'website'}"><meta property="og:url" content="{canonical}"><meta property="og:image" content="{SITE['url']}/assets/social-card.jpg"><meta property="og:image:type" content="image/jpeg"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<link rel="icon" type="image/svg+xml" href="/assets/favicon.svg"><link rel="preload" href="/assets/fonts/ibm-plex-mono-bold.ttf" as="font" type="font/ttf" crossorigin><script>try{{const t=localStorage.getItem('doovvv-theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t}}catch(e){{}}</script><link rel="stylesheet" href="/assets/site.css"><script src="/assets/site.js" defer></script>{extra}</head>
<body class="page-{kind}" id="top">{navigation(active)}<main id="main-content">{content}</main>{footer()}{search_dialog()}<button class="back-top icon-button" aria-label="返回顶部">{icon('arrow')}</button></body></html>'''


def card(post, index):
    label, category, number = topic(post)
    cover = article_cover(post)
    cover_class = ' article-cover' if cover['article_image'] else ''
    cover_kind = 'article' if cover['article_image'] else 'default'
    return f'''<article class="article-card"><a class="card-cover cover-{category}{cover_class}" data-cover-kind="{cover_kind}" href="{post['url']}" aria-label="阅读 {escape(post['title'], quote=True)}"><img src="{escape(cover['src'], quote=True)}" data-cover-fallback="{cover['fallback']}" alt="" loading="lazy" width="720" height="420"><span class="cover-category">{escape(label)}</span><span class="cover-open">{icon('up-right')}</span></a>
    <div class="card-content"><div class="card-meta"><span>{escape(label)}</span><time datetime="{post['date'][:10]}">{post['date'][:10].replace('-', '.')}</time></div>
    <h3><a href="{post['url']}">{escape(post['title'])}</a></h3><p>{escape(post['excerpt'])}</p><div class="card-bottom"><span>{icon('clock')}{post['minutes']} 分钟阅读</span><a href="{post['url']}" aria-label="阅读 {escape(post['title'], quote=True)}">阅读笔记 {icon('arrow')}</a></div></div></article>'''


def pagination(page):
    if not page.get('pagination'):
        return ''
    parts = []
    for item in page['pagination']:
        label = item['label']
        if item['href']:
            parts.append(f'<a href="{item["href"]}" aria-label="第 {escape(label)} 页">{escape(label)}</a>')
        else:
            parts.append(f'<span class="{"current" if item["current"] else "gap"}" {"aria-current=page" if item["current"] else ""}>{escape(label)}</span>')
    return '<nav class="pagination" aria-label="文章分页">' + ''.join(parts) + '</nav>'


def hero():
    symbols = ''.join(f'<span>{escape(s)}</span>' for s in ['</>', '{}', '=>', '[]', '<>', '()', '::', '==', '++', ';', '/**/', '{ }'])
    return f'''<section class="hero" aria-labelledby="hero-title"><div class="hero-grid" aria-hidden="true"></div><div class="code-symbols" aria-hidden="true">{symbols}</div>
    <div class="hero-inner"><p class="hero-greeting">Hello.</p><h1 id="hero-title">I'm <span>doovvv.</span></h1>
    <p class="hero-subtitle">代码、系统与学习笔记</p><p class="hero-description">保持好奇，让每一次思考留下痕迹。</p><div class="hero-actions"><a class="button button-primary" href="#notes">探索笔记 {icon('arrow')}</a><a class="text-link" href="/about/">关于我 {icon('up-right')}</a></div></div>
    <div class="hero-bottom"><div class="hero-socials"><a href="https://github.com/doovvv" target="_blank" rel="noopener noreferrer" aria-label="在 GitHub 找到 doovvv">{icon('github')}</a><a href="/archives/" aria-label="浏览所有笔记">{icon('book')}</a><span>PERSONAL NOTEBOOK</span></div><a class="scroll-cue" href="#notes">SCROLL TO EXPLORE {icon('down')}</a></div></section>'''


def featured():
    selected = [next(p for p in SITE['posts'] if key in p['slug']) for key in ['machine-learning', '分布式', '算法模板']]
    slides = []
    for i, post in enumerate(selected):
        cover = article_cover(post)
        cover_class = ' article-cover' if cover['article_image'] else ''
        cover_kind = 'article' if cover['article_image'] else 'default'
        slides.append(f'''<article class="featured-slide" {'hidden' if i else ''} data-slide="{i}"><a class="featured-image{cover_class}" data-cover-kind="{cover_kind}" href="{post['url']}" aria-label="阅读 {escape(post['title'], quote=True)}" tabindex="{'-1' if i else '0'}"><img src="{escape(cover['src'], quote=True)}" data-cover-fallback="{cover['fallback']}" alt="" loading="lazy" width="1100" height="800"></a><div class="featured-content"><div class="eyebrow">SELECTED NOTE <span class="slide-number">0{i+1} / 03</span></div><span class="featured-category">{topic(post)[0]}</span><h3><a href="{post['url']}">{escape(post['title'])}</a></h3><p>{escape(post['excerpt'])}</p><a class="text-link" href="{post['url']}">继续阅读 {icon('up-right')}</a></div></article>''')
    controls = ''.join(f'<button class="slide-dot{" active" if i == 0 else ""}" aria-label="查看精选文章 {i+1}" aria-pressed="{"true" if i == 0 else "false"}" data-slide-to="{i}"><span>0{i+1}</span></button>' for i in range(3))
    return '<section class="featured-section" aria-labelledby="featured-title"><div class="section-label"><p class="eyebrow">01 / SELECTED</p><h2 id="featured-title">精选笔记</h2><span class="section-rule"></span><p>值得回看的思考，<br>也许是新的起点。</p></div><div class="featured">' + ''.join(slides) + '<div class="featured-controls">' + controls + '</div></div></section>'


def home(page):
    is_root = page['file'] == 'index.html'
    body = hero() if is_root else page_heading('THE NOTEBOOK', '继续探索', '想法慢慢积累，线索在这里延伸。')
    body += '<div class="page-container home-content" id="notes">'
    if is_root:
        body += featured()
    body += f'''<section class="notes-section"><div class="section-heading"><div><div class="eyebrow">02 / THE NOTEBOOK <span class="small-count">20</span></div><h2>最新笔记<span class="heading-dot">.</span></h2><span class="section-rule"></span></div><a class="text-link" href="/archives/">查看归档 {icon('up-right')}</a></div>
    <div class="notes-toolbar"><span>{icon('grid')} 持续学习，认真记录。</span><span class="toolbar-order">按发布时间排序 {icon('down')}</span></div><div class="article-grid" id="article-grid">'''
    body += ''.join(card(post_for(url), i) for i, url in enumerate(page['posts'])) + '</div>' + pagination(page) + '</section>'
    body += f'''<section class="about-strip"><div class="section-label"><div class="eyebrow">03 / ABOUT ME</div><h2>关于这里</h2><span class="section-rule"></span></div><div><h3>一切都没有意外，<br>只是多了些波折。</h3><p>这里是 doovvv 的个人博客。记录学习中的问题、实践里的发现，也给暂时没有答案的思考留一个位置。</p><div class="topic-chips"><span>Computer Science</span><span>Algorithms</span><span>AI & Systems</span></div><a class="text-link" href="/about/">认识一下 {icon('up-right')}</a></div></section></div>'''
    return body


def page_heading(eyebrow, title, description):
    return f'<section class="page-heading page-container"><div class="eyebrow">{eyebrow}</div><h1>{escape(title)}<span class="heading-dot">.</span></h1><span class="section-rule"></span><p>{escape(description)}</p></section>'


def archive(page):
    parts = page['file'].split('/')
    period = ' / '.join(p for p in parts[1:] if p.isdigit() and len(p) in (2, 4))
    title = f'{period} 的笔记' if period else '时间归档'
    result = page_heading('THE ARCHIVE', title, '把零散的思考，放进时间的坐标里。')
    years = sorted({p['date'][:4] for p in SITE['posts']}, reverse=True)
    filters = '<a href="/archives/">全部</a>' + ''.join(f'<a href="/archives/{year}/">{year}</a>' for year in years)
    result += f'<div class="page-container archive-layout"><aside class="archive-summary"><span class="big-number">20<span>篇</span></span><p>从 2023 年开始的记录</p><nav class="year-filters" aria-label="按年份浏览">{filters}</nav><div class="archive-note">Keep learning.<br>Keep a record.</div></aside><div class="timeline">'
    year = None
    for url in page['posts']:
        post = post_for(url)
        if post['date'][:4] != year:
            year = post['date'][:4]
            result += f'<h2 class="timeline-year">{year}<span>YEAR</span></h2>'
        result += f'<a class="timeline-entry" href="{post["url"]}"><time datetime="{post["date"][:10]}">{post["date"][5:10].replace("-", ".")}</time><div><span>{topic(post)[0]}</span><h3>{escape(post["title"])}</h3></div>{icon("up-right")}</a>'
    return result + pagination(page) + '</div></div>'


def tag_page(page):
    if page['kind'] == 'tags':
        result = page_heading('THE INDEX', '标签索引', '从一个关键词，找到相连的思考。') + '<div class="page-container tag-grid">'
        for i, (url, name) in enumerate(SITE['tag_names'].items()):
            count = sum(any(unquote(t['url']) == url for t in p['tags']) for p in SITE['posts'])
            result += f'<a class="tag-card" href="{quote(url, safe="/")}"><span class="tag-number">0{i+1}</span>{icon("tag")}<h2>{escape(name)}</h2><div><span>{count:02d} 篇笔记</span>{icon("up-right")}</div></a>'
        return result + '</div>'
    name = SITE['tag_names'].get(unquote(page['url']), page['url'].split('/')[-2])
    result = page_heading('TAG / ' + name.upper(), name, f'关于这个主题的 {len(page["posts"])} 篇记录。')
    return result + '<div class="page-container"><a class="back-link" href="/tags/">← 所有标签</a><div class="article-grid" id="article-grid">' + ''.join(card(post_for(url), i) for i, url in enumerate(page['posts'])) + '</div></div>'


def post_page(post):
    label = topic(post)[0]
    date = post['date'][:10].replace('-', '.')
    tags = ''.join(f'<a href="{t["url"]}">#{escape(t["name"])}</a>' for t in post['tags'])
    toc = post['toc'] or '<p class="toc-empty">本文没有章节目录。</p>'
    result = f'''<section class="article-heading page-container"><a class="back-link" href="/archives/">← 返回笔记</a><div class="eyebrow">{escape(label)} / NOTEBOOK</div><h1>{escape(post['title'])}</h1><div class="article-meta"><a href="/about/" class="author-meta"><span class="author-initial">d.</span>doovvv</a><span class="meta-divider"></span><time datetime="{post['date'][:10]}">{date}</time><span>{icon('clock')}{post['minutes']} 分钟阅读</span></div><div class="article-tags">{tags}</div></section>
    <div class="reading-layout page-container"><article class="reading-article" aria-label="文章正文">{post['body']}<div class="article-end"><span>END OF NOTE</span><i></i>{icon('code')}</div><div class="article-license"><span>最后更新 {post['updated'][:10]}</span><span>本文内容采用 <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/" target="_blank" rel="noopener noreferrer">CC BY-NC-SA 4.0</a> 许可</span></div>'''
    result += '<nav class="article-neighbors" aria-label="相邻文章">'
    for direction, title in [('prev', '上一篇'), ('next', '下一篇')]:
        neighbor = post[direction]
        result += f'<a href="{neighbor["url"]}"><span>{title}</span><strong>{escape(neighbor["title"])}</strong>{icon("arrow")}</a>' if neighbor else '<span></span>'
    result += f'''</nav><section class="comments-section" aria-labelledby="comments-heading"><div class="section-heading"><h2 id="comments-heading">交流与讨论<span class="heading-dot">.</span></h2></div><button class="button button-outline load-comments">展开评论 {icon('arrow')}</button><p class="comment-status" role="status"></p><div id="valine-comments"></div></section></article><aside class="reading-sidebar"><div class="toc-heading"><span>ON THIS PAGE</span>{icon('book')}</div>{toc}<div class="reading-progress"><div><span>阅读进度</span><span id="reading-percent">0%</span></div><div class="progress-track"><span id="reading-progress-bar"></span></div></div></aside></div>'''
    return result


def about():
    return page_heading('BEHIND THE NOTES', '你好，我是 doovvv', '一个用代码探索问题，用文字整理思考的人。') + f'''<div class="page-container about-page"><div class="about-portrait"><span>d.</span><div class="eyebrow">ALWAYS A WORK IN PROGRESS</div></div><div class="about-copy"><div class="eyebrow">MY LITTLE CORNER OF THE INTERNET</div><h2>保持好奇，<br>让思考留下痕迹。</h2><p>这里收集了我在计算机科学、算法、人工智能和系统学习中的笔记。它们不总是完整的答案，更像是理解一个问题时留下的路标。</p><p>一切都没有意外，只是多了些波折。</p><a class="button button-primary" href="https://github.com/doovvv" target="_blank" rel="noopener noreferrer">{icon('github')} GitHub {icon('up-right')}</a><div class="about-stats"><div><strong>20</strong><span>篇学习笔记</span></div><div><strong>06</strong><span>个原有标签</span></div><div><strong>2023</strong><span>开始记录</span></div></div></div></div>'''


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


def main():
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
            body = page_heading('RESOURCES', '资源与链接', '常用工具与参考资料。') + '<div class="page-container reading-article">' + page.get('body', '') + '</div>'
            title, description = '资源与链接', SITE['description']
        active = 'tags' if kind == 'tag' else kind
        output = ROOT / page['file']
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(layout(title, description, page['url'], body, active, kind, extra), encoding='utf8')
    about_dir = ROOT / 'about'
    about_dir.mkdir(exist_ok=True)
    (about_dir / 'index.html').write_text(layout('关于我', SITE['description'], '/about/', about(), 'about', 'about'), encoding='utf8')
    search = [{k: p[k] for k in ['url', 'title', 'excerpt', 'text', 'date']} for p in SITE['posts']]
    (ROOT / 'assets/search.json').write_text(json.dumps(search, ensure_ascii=False, separators=(',', ':')), encoding='utf8')
    (ROOT / 'assets/favicon.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="#1d4ed8"/><text x="13" y="47" fill="#f1f4f6" font-size="46" font-family="Arial" font-weight="bold">d<tspan fill="#bfdbfe">.</tspan></text></svg>', encoding='utf8')
    write_covers()
    (ROOT / '.nojekyll').touch()
    print(f'Built {len(SITE["pages"]) + 1} pages, 20 searchable articles, and 7 cover illustrations.')


if __name__ == '__main__':
    main()
