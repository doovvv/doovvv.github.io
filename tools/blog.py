"""Local article creation, draft preview, and non-force GitHub Pages publishing."""
from __future__ import annotations

import argparse
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
import zipfile

try:
    from .build import build_site
    from .content import load_site, read_document, yaml
    from .locking import workflow_lock
except ImportError:
    from build import build_site
    from content import load_site, read_document, yaml
    from locking import workflow_lock

ROOT = Path(__file__).resolve().parents[1]


def new_article(root, title, slug=None):
    root = Path(root).resolve()
    title = title.strip()
    if not title:
        raise ValueError('请输入文章标题。')
    slug = slug or re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-') or datetime.now().strftime('note-%Y%m%d-%H%M%S')
    if not re.fullmatch(r'[\w-]+', slug):
        raise ValueError('文件夹名只能包含字母、数字、中文、短横线或下划线。')
    directory = root / 'content/posts' / slug
    directory.mkdir(parents=True, exist_ok=False)
    (directory / 'images').mkdir()
    meta = {'title': title, 'date': datetime.now().date().isoformat(), 'tags': [], 'draft': True}
    sample = '\n这里写文章简介。\n\n<!-- 把图片放进 images 文件夹后，使用：![图片说明](images/cover.jpg) -->\n\n## 第一节\n\n这里写正文。\n'
    path = directory / 'index.md'
    path.write_text('---\n' + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + '---\n' + sample, encoding='utf8')
    return path


def git(root, *args, check=True):
    result = subprocess.run(['git', '--literal-pathspecs', *args], cwd=root, capture_output=True, text=True, encoding='utf8', errors='replace', timeout=90)
    if check and result.returncode:
        raise ValueError('Git 操作失败：' + (result.stderr.strip() or result.stdout.strip()))
    return result


def git_paths(root, *args):
    return [p for p in git(root, args[0], '-z', *args[1:]).stdout.split('\0') if p]


def backup_sources(root):
    directory = root / '.backups'
    directory.mkdir(exist_ok=True)
    destination = directory / (datetime.now().strftime('articles-%Y%m%d-%H%M%S-%f') + '.zip')
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for source in [root / 'content/site.json', *(root / 'content/posts').rglob('*')]:
            if source.is_file() and source.resolve().is_relative_to(root / 'content'):
                archive.write(source, source.relative_to(root).as_posix())
    return destination


def validate_output(root, site):
    expected = {post['url'] for post in site['posts']}
    search = json.loads((root / 'assets/search.json').read_text(encoding='utf8'))
    if {post['url'] for post in search} != expected:
        raise ValueError('搜索索引与文章列表不一致，发布已停止。')
    for page in site['pages']:
        if not (root / page['file']).is_file():
            raise ValueError('页面未生成：' + page['file'])
    cname = root / 'CNAME'
    if not cname.is_file() or cname.read_text(encoding='utf8').strip() != 'doovvv.cn':
        raise ValueError('CNAME 应保留 doovvv.cn，发布已停止。')


def prepare_simple_posts(root):
    """Save inferred dates and slugs once so edits keep the original public URL."""
    for path in sorted((root / 'content/posts').glob('*.md')):
        meta, body, missing = read_document(path, root)
        if meta.get('draft') or not missing:
            continue
        source = '---\n' + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + '---\n' + body
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf8', newline='\n',
                    dir=path.parent, prefix='.blog-', suffix='.tmp', delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(source)
            os.replace(temporary, path)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
        print('已自动补齐文章信息：' + path.name, flush=True)


def _publish(root=ROOT):
    root = Path(root).resolve()
    if not shutil.which('git'):
        raise ValueError('请先安装 Git for Windows，再运行发布。')
    if Path(git(root, 'rev-parse', '--show-toplevel').stdout.strip()).resolve() != root:
        raise ValueError('请在博客文件夹中运行发布脚本。')
    if git(root, 'diff', '--cached', '--quiet', check=False).returncode:
        raise ValueError('Git 暂存区已有改动；请先完成或取消原来的暂存，再发布博客。')
    # Validate all content before any Git mutation. A failed build cannot publish.
    load_site(root)
    print('正在检查远端版本…', flush=True)
    git(root, 'fetch', 'origin', 'main')
    if git(root, 'merge-base', '--is-ancestor', 'origin/main', 'HEAD', check=False).returncode:
        raise ValueError('远端有尚未同步的提交，请先同步远端改动后再发布；本地内容未被覆盖。')
    backup = backup_sources(root)
    prepare_simple_posts(root)
    site = build_site(root, include_drafts=False)
    validate_output(root, site)
    public_sources = set(site['_public_sources'])
    source_prefix = 'content/posts/'
    tracked_sources = git_paths(root, 'ls-files', '--', 'content/posts')
    private_sources = set(tracked_sources) - public_sources
    # Removing a source from the index keeps the local draft on disk. Published
    # sources are backed up in Git; drafts are included only in the local ZIP.
    for path in sorted(private_sources):
        git(root, 'rm', '--cached', '--quiet', '--', path)
    changed = set(git_paths(root, 'ls-files', '--modified', '--deleted'))
    changed = {p for p in changed if not p.startswith(source_prefix)}
    generated = set(json.loads((root / 'content/generated-files.json').read_text(encoding='utf8')))
    candidates = changed | generated | set(site['_public_assets']) | {'content/generated-files.json', 'CNAME'}
    candidates = sorted(p for p in candidates if (root / p).exists() or p in changed)
    for i in range(0, len(candidates), 60):
        git(root, 'add', '--all', '--', *candidates[i:i+60])
    for path in sorted(public_sources):
        git(root, 'add', '--force', '--', path)
    if git(root, 'diff', '--cached', '--quiet', check=False).returncode:
        # Use this repository's existing public author if Git has no identity;
        # avoid changing the user's machine-wide Git configuration.
        name = git(root, 'config', 'user.name', check=False).stdout.strip() or git(root, 'log', '-1', '--format=%an').stdout.strip()
        email = git(root, 'config', 'user.email', check=False).stdout.strip() or git(root, 'log', '-1', '--format=%ae').stdout.strip()
        git(root, '-c', 'user.name=' + name, '-c', 'user.email=' + email, 'commit', '-m', 'Publish blog ' + datetime.now().strftime('%Y-%m-%d %H:%M'))
    print('本地已保存。正在上传到 GitHub…', flush=True)
    git(root, 'push', 'origin', 'HEAD:main')
    print('已推送到 GitHub，Pages 完成部署后可访问：https://doovvv.cn/')
    print('本地文章备份：' + str(backup))
    return git(root, 'rev-parse', 'HEAD').stdout.strip()


def publish(root=ROOT):
    with workflow_lock(root):
        return _publish(root)


def source_signature(root):
    paths = [root / 'content/site.json', root / 'content/ui.json', *(root / 'content/posts').rglob('*')]
    return tuple(sorted((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths if p.is_file()))


def preview(root=ROOT, port=8001, open_browser=True):
    root = Path(root).resolve()
    build_site(root, include_drafts=True)
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    for candidate in range(port, port + 10):
        try:
            server = ThreadingHTTPServer(('127.0.0.1', candidate), handler)
            break
        except OSError:
            if candidate == port + 9:
                raise ValueError('预览端口被占用，请关闭旧预览窗口后重试。')
    url = f'http://127.0.0.1:{server.server_port}/'
    print('本地预览（包含草稿）：' + url)
    print('保存文章后会自动重新生成，刷新浏览器查看。关闭此窗口或按 Ctrl+C 可停止预览。', flush=True)
    stopped = threading.Event()
    def watch():
        previous = source_signature(root)
        while not stopped.wait(1):
            try:
                current = source_signature(root)
                if current != previous:
                    previous = current
                    build_site(root, include_drafts=True)
                    print('已重新生成，请刷新浏览器。', flush=True)
            except (ValueError, OSError) as error:
                print('文章暂未生成：' + str(error), flush=True)
    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stopped.set()
        thread.join(timeout=3)
        server.server_close()


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf8')
        sys.stderr.reconfigure(encoding='utf8')
    parser = argparse.ArgumentParser(description='新建文章、预览和发布博客')
    commands = parser.add_subparsers(dest='command', required=True)
    new = commands.add_parser('new', help='新建 Markdown 草稿')
    new.add_argument('--title')
    new.add_argument('--slug')
    new.add_argument('--no-open', action='store_true')
    view = commands.add_parser('preview', help='本地预览，包含草稿')
    view.add_argument('--port', type=int, default=8001)
    view.add_argument('--no-open', action='store_true')
    commands.add_parser('publish', help='生成并发布公开文章')
    args = parser.parse_args()
    try:
        if args.command == 'new':
            path = new_article(ROOT, args.title or input('文章标题：'), args.slug)
            print('已创建草稿：' + str(path))
            print('写完后把 draft: true 改为 draft: false，再发布。')
            if not args.no_open and os.name == 'nt':
                os.startfile(path)
        elif args.command == 'preview':
            preview(port=args.port, open_browser=not args.no_open)
        else:
            publish()
    except (ValueError, OSError, subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        parser.exit(1, '\n操作未完成：' + str(error) + '\n本地文章仍然保留。若已创建本地提交，可修复问题后再次发布。\n')


if __name__ == '__main__':
    main()
