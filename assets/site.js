(() => {
  'use strict';
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const root = document.documentElement;
  const { t, setText, getLanguage, syncComments } = window.BlogI18n;
  let commentInstance;
  function localizedAttribute(element, attribute, key) {
    element?.setAttribute('data-i18n-' + attribute, key);
    element?.setAttribute(attribute, t(key));
  }

  // Theme changes are local to the reader and survive navigation.
  const themeButton = $('.theme-toggle');
  function syncTheme() {
    const dark = root.dataset.theme !== 'light';
    localizedAttribute(themeButton, 'aria-label', dark ? 'theme.light' : 'theme.dark');
    localizedAttribute(themeButton, 'title', dark ? 'theme.light' : 'theme.dark');
    $('meta[name="theme-color"]')?.setAttribute('content', dark ? '#111827' : '#ffffff');
  }
  themeButton?.addEventListener('click', () => {
    root.dataset.theme = root.dataset.theme === 'light' ? 'dark' : 'light';
    try { localStorage.setItem('doovvv-theme', root.dataset.theme); } catch (_) { /* Private storage can be disabled. */ }
    syncTheme();
  });
  syncTheme();

  const menu = $('#site-nav');
  const menuButton = $('.menu-toggle');
  function syncMenuButton() {
    localizedAttribute(menuButton, 'aria-label', menu?.classList.contains('is-open') ? 'menu.close' : 'menu.open');
  }
  function closeMenu() {
    menu?.classList.remove('is-open');
    menuButton?.setAttribute('aria-expanded', 'false');
    syncMenuButton();
  }
  menuButton?.addEventListener('click', () => {
    const open = menu.classList.toggle('is-open');
    menuButton.setAttribute('aria-expanded', String(open));
    syncMenuButton();
  });
  menu?.addEventListener('click', event => { if (event.target.closest('a')) closeMenu(); });
  document.addEventListener('click', event => {
    if (!event.target.closest('.site-header')) closeMenu();
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') closeMenu(); });
  window.addEventListener('resize', () => { if (window.innerWidth > 800) closeMenu(); });

  // The featured notes use explicit controls; there is no forced auto-play.
  const slides = $$('.featured-slide');
  const slideButtons = $$('.slide-dot');
  slideButtons.forEach(button => button.addEventListener('click', () => {
    const target = Number(button.dataset.slideTo);
    slides.forEach((slide, i) => {
      slide.hidden = i !== target;
      slide.setAttribute('aria-hidden', String(i !== target));
      $$('a', slide).forEach(anchor => { anchor.tabIndex = i === target ? 0 : -1; });
    });
    slideButtons.forEach((control, i) => {
      control.classList.toggle('active', i === target);
      control.setAttribute('aria-pressed', String(i === target));
    });
  }));

  // Search the complete published text, rather than just the current page.
  const dialog = $('#search-dialog');
  const input = $('#search-input');
  const results = $('#search-results');
  const status = $('#search-status');
  let searchData;
  let searchPromise;
  let searchTimer;
  let searchVersion = 0;
  let searchOpener;
  const normalize = text => String(text).normalize('NFKC').toLowerCase();

  async function loadSearch() {
    if (searchData) return searchData;
    if (!searchPromise) {
      searchPromise = fetch('/assets/search.json').then(response => {
        if (!response.ok) throw new Error('Search index unavailable');
        return response.json();
      }).then(data => {
        searchData = data.map(post => ({ ...post, normalizedTitle: normalize(post.title), normalizedText: normalize(post.text) }));
        return searchData;
      }).catch(error => { searchPromise = null; throw error; });
    }
    return searchPromise;
  }

  function highlight(element, text, query) {
    // DOM nodes keep both article text and search input out of HTML injection paths.
    const position = normalize(text).indexOf(normalize(query));
    if (position < 0 || !query) { element.textContent = text; return; }
    element.append(document.createTextNode(text.slice(0, position)));
    const mark = document.createElement('mark');
    mark.textContent = text.slice(position, position + query.length);
    element.append(mark, document.createTextNode(text.slice(position + query.length)));
  }

  async function runSearch() {
    const version = ++searchVersion;
    const query = input.value.trim();
    results.replaceChildren();
    if (!query) { setText(status, 'search.initial', { count: 20 }); return; }
    setText(status, 'search.loading');
    try {
      const data = await loadSearch();
      if (version !== searchVersion) return;
      const terms = normalize(query).split(/\s+/).filter(Boolean).slice(0, 10);
      const found = data.filter(post => terms.every(term => post.normalizedTitle.includes(term) || post.normalizedText.includes(term)))
        .map(post => ({ post, score: terms.reduce((sum, term) => sum + (post.normalizedTitle.includes(term) ? 100 : 1), 0) }))
        .sort((a, b) => b.score - a.score || b.post.date.localeCompare(a.post.date));
      setText(status, found.length ? 'search.found' : 'search.empty', { count: found.length });
      found.forEach(({ post }) => {
        const anchor = document.createElement('a');
        anchor.className = 'search-result';
        anchor.href = post.url;
        const title = document.createElement('h3');
        highlight(title, post.title, query);
        const preview = document.createElement('p');
        const index = post.normalizedText.indexOf(terms[0]);
        const snippet = index >= 0 ? `${index > 30 ? '…' : ''}${post.text.slice(Math.max(0, index - 30), index + 100)}…` : post.excerpt;
        highlight(preview, snippet, terms[0]);
        const time = document.createElement('time');
        time.dateTime = post.date.slice(0, 10);
        time.textContent = post.date.slice(0, 10).replaceAll('-', '.');
        anchor.append(title, preview, time);
        results.append(anchor);
      });
    } catch (_) {
      if (version === searchVersion) setText(status, 'search.error');
    }
  }

  function openSearch() {
    if (!dialog || dialog.open) return;
    closeMenu();
    searchOpener = document.activeElement;
    dialog.showModal();
    input.focus();
    if (input.value.trim()) runSearch();
  }
  $$('.search-toggle').forEach(button => button.addEventListener('click', openSearch));
  $('.search-close')?.addEventListener('click', () => dialog.close());
  dialog?.addEventListener('close', () => {
    ++searchVersion;
    searchOpener?.focus();
  });
  dialog?.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
  });
  $('.search-form')?.addEventListener('submit', event => event.preventDefault());
  input?.addEventListener('input', () => {
    ++searchVersion;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(runSearch, 100);
  });
  input?.addEventListener('keydown', event => {
    if (event.key === 'ArrowDown') { event.preventDefault(); $('.search-result', results)?.focus(); }
  });
  document.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      openSearch();
    }
  });

  document.addEventListener('blog:language-change', () => {
    syncTheme();
    syncMenuButton();
    syncComments(commentInstance, $('#valine-comments'));
    if (dialog?.open) runSearch();
  });

  // Preserve the old article markup and enhance only presentation controls.
  $$('.post-body figure.highlight').forEach(figure => {
    const pre = $('.code pre', figure) || $('pre', figure);
    if (!pre) return;
    const label = document.createElement('span');
    label.className = 'code-language';
    label.textContent = [...figure.classList].find(name => name !== 'highlight')?.toUpperCase() || 'CODE';
    const button = document.createElement('button');
    button.className = 'code-copy';
    setText(button, 'code.copy');
    localizedAttribute(button, 'aria-label', 'code.copyAria');
    button.addEventListener('click', async () => {
      const copy = pre.cloneNode(true);
      $$('br', copy).forEach(br => br.replaceWith('\n'));
      try {
        await navigator.clipboard.writeText(copy.textContent);
        setText(button, 'code.copied');
      } catch (_) { setText(button, 'code.copyError'); }
      setTimeout(() => { setText(button, 'code.copy'); }, 1800);
    });
    figure.append(label, button);
  });

  // Failed external cover images retain a useful default, in both themes.
  $$('img[data-cover-fallback]').forEach(image => {
    const fallback = () => {
      if (image.getAttribute('src') === image.dataset.coverFallback) return;
      image.src = image.dataset.coverFallback;
      image.closest('[data-cover-kind]')?.classList.remove('article-cover');
      const container = image.closest('[data-cover-kind]');
      if (container) container.dataset.coverKind = 'default';
    };
    image.addEventListener('error', fallback, { once: true });
    if (image.complete && image.naturalWidth === 0) fallback();
  });

  const recoveredImages = window.BLOG_IMAGE_ALIASES || {};
  $$('.post-body img').forEach(image => {
    const original = image.getAttribute('src');
    const recovered = recoveredImages[original] || recoveredImages[original.split('/').pop()];
    if (recovered) image.src = recovered;
    image.loading = 'lazy';
    image.decoding = 'async';
    const showFallback = () => {
      if (!image.isConnected) return;
      const fallback = document.createElement('span');
      fallback.className = 'missing-image';
      setText(fallback, 'image.missing');
      fallback.setAttribute('role', 'img');
      localizedAttribute(fallback, 'aria-label', 'image.missingAria');
      image.replaceWith(fallback);
    };
    image.addEventListener('error', showFallback, { once: true });
    if (image.complete && image.naturalWidth === 0) showFallback();
  });

  const body = $('.reading-article .post-body');
  const headings = body ? $$('h1[id],h2[id],h3[id],h4[id],h5[id],h6[id]', body) : [];
  const tocLinks = $$('.reading-sidebar .post-toc a');
  let pendingScroll = false;
  function updateScroll() {
    pendingScroll = false;
    $('.back-top')?.classList.toggle('is-visible', window.scrollY > 600);
    if (!body) return;
    const start = body.getBoundingClientRect().top + window.scrollY - 120;
    const distance = Math.max(1, body.scrollHeight - window.innerHeight + 160);
    const progress = Math.max(0, Math.min(100, Math.round((window.scrollY - start) / distance * 100)));
    const percent = $('#reading-percent');
    if (percent) percent.textContent = `${progress}%`;
    const bar = $('#reading-progress-bar');
    if (bar) bar.style.width = `${progress}%`;
    let current = headings[0];
    for (const heading of headings) { if (heading.getBoundingClientRect().top <= 155) current = heading; else break; }
    tocLinks.forEach(anchor => {
      let id;
      try { id = decodeURIComponent(anchor.hash.slice(1)); } catch (_) { id = anchor.hash.slice(1); }
      anchor.classList.toggle('is-active', id === current?.id);
      if (id === current?.id) anchor.setAttribute('aria-current', 'location'); else anchor.removeAttribute('aria-current');
    });
  }
  window.addEventListener('scroll', () => {
    if (!pendingScroll) { pendingScroll = true; requestAnimationFrame(updateScroll); }
  }, { passive: true });
  window.addEventListener('load', updateScroll);
  window.addEventListener('resize', updateScroll);
  $('.back-top')?.addEventListener('click', () => window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' }));
  updateScroll();

  if (body && $$('.math', body).some(node => /\\\(|\\\[|\$/.test(node.textContent))) {
    window.MathJax = {
      tex: { inlineMath: [['\\(', '\\)'], ['$', '$']], displayMath: [['\\[', '\\]'], ['$$', '$$']], processEscapes: true },
      svg: { fontCache: 'local' }
    };
    const math = document.createElement('script');
    math.src = '/assets/vendor/mathjax.js';
    math.async = true;
    document.head.append(math);
  }

  const commentButton = $('.load-comments');
  commentButton?.addEventListener('click', () => {
    const status = $('.comment-status');
    const config = window.BLOG_COMMENTS;
    if (!config?.appId) { setText(status, 'comments.unavailable'); return; }
    commentButton.disabled = true;
    setText(status, 'comments.loading');
    const script = document.createElement('script');
    script.src = '/assets/vendor/valine.min.js';
    script.onload = () => {
      try {
        commentInstance = new window.Valine({ ...config, el: '#valine-comments', path: location.pathname, placeholder: t('comments.placeholder'), avatar: 'mm', meta: ['nick', 'mail', 'link'], pageSize: 10, visitor: false, lang: getLanguage() === 'en' ? 'en' : 'zh-cn', recordIP: false });
        syncComments(commentInstance, $('#valine-comments'));
        commentButton.hidden = true;
        status.removeAttribute('data-i18n');
        status.textContent = '';
      } catch (_) { setText(status, 'comments.error'); commentButton.disabled = false; }
    };
    script.onerror = () => { setText(status, 'comments.loadError'); commentButton.disabled = false; script.remove(); };
    document.head.append(script);
  });
})();
