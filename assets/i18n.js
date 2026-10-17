(function (global) {
  'use strict';
  const supported = ['en', 'zh-CN'];
  const storageKey = 'doovvv-language';
  function chooseLanguage(saved) { return supported.includes(saved) ? saved : 'en'; }
  function formatMessage(messages, language, key, params = {}) {
    const message = messages[key]?.[language] ?? messages[key]?.en ?? key;
    return message.replace(/\{([a-zA-Z0-9_]+)\}/g, (match, name) => Object.hasOwn(params, name) ? String(params[name]) : match);
  }
  function syncComments(instance, container, language, messages) {
    if (!instance?.i18n || !container) return;
    const phrases = Object.fromEntries(Object.keys(messages).filter(key => key.startsWith('valine.'))
      .map(key => [key.slice(7), formatMessage(messages, language, key)]));
    const previous = Object.fromEntries(Object.keys(phrases).map(key => [key, instance.i18n.t(key)]));
    // Valine 1.5.2 uses Polyglot. Update its dictionary and existing controls in
    // place so a language change preserves drafts, focus, and the reply target.
    instance.i18n.extend(phrases);
    instance.i18n.locale(language);
    instance.cfg.lang = language;
    instance.cfg.placeholder = formatMessage(messages, language, 'comments.placeholder');
    const update = (selector, key, attribute) => container.querySelectorAll(selector).forEach(element => {
      if (attribute) element.setAttribute(attribute, phrases[key]);
      else element.textContent = phrases[key];
    });
    ['nick', 'mail', 'link'].forEach(key => update('input[name="' + key + '"]', key, 'placeholder'));
    container.querySelectorAll('.veditor').forEach(element => element.setAttribute('placeholder', instance.cfg.placeholder));
    [['.vsubmit', 'submit'], ['.vmore', 'more'], ['.vat', 'reply']].forEach(([selector, key]) => update(selector, key));
    [['.cancel-reply', 'cancelReply'], ['.vemoji-btn', 'emoji'], ['.vpreview-btn', 'preview']]
      .forEach(([selector, key]) => update(selector, key, 'title'));
    update('.vcontent', 'expand', 'data-expand');
    container.querySelectorAll('.vcount').forEach(element => {
      [...element.childNodes].filter(node => node.nodeType === 3).forEach(node => { node.textContent = ' ' + phrases.comments; });
    });
    container.querySelectorAll('.vempty, .vtime').forEach(element => {
      const text = element.textContent;
      const key = Object.keys(previous).find(key => text === previous[key]);
      if (key) element.textContent = phrases[key];
      else for (const unit of ['seconds', 'minutes', 'hours', 'days']) {
        if (text.endsWith(' ' + previous[unit])) {
          element.textContent = text.slice(0, -previous[unit].length) + phrases[unit];
          break;
        }
      }
    });
  }
  // The same formatter is used by generated labels and interactive controls.
  if (typeof module === 'object' && module.exports) module.exports = { chooseLanguage, formatMessage, syncComments };
  if (!global.document) return;
  const messages = global.BLOG_UI_MESSAGES || {};
  let saved;
  try { saved = global.localStorage.getItem(storageKey); } catch (_) { /* Storage is optional. */ }
  let language = chooseLanguage(saved);
  const t = (key, params) => formatMessage(messages, language, key, params);
  function parameters(element, attribute) {
    try { return JSON.parse(element.getAttribute(attribute) || '{}'); } catch (_) { return {}; }
  }
  function setText(element, key, params = {}) {
    if (!element) return;
    element.setAttribute('data-i18n', key);
    element.setAttribute('data-i18n-params', JSON.stringify(params));
    element.textContent = t(key, params);
  }
  function translatePage() {
    global.document.querySelectorAll('[data-i18n]').forEach(element => {
      element.textContent = t(element.getAttribute('data-i18n'), parameters(element, 'data-i18n-params'));
    });
    ['aria-label', 'title', 'placeholder', 'alt', 'content'].forEach(attribute => {
      const marker = 'data-i18n-' + attribute;
      global.document.querySelectorAll('[' + marker + ']').forEach(element => {
        element.setAttribute(attribute, t(element.getAttribute(marker), parameters(element, marker + '-params')));
      });
    });
  }
  function setLanguage(next, persist = true) {
    language = chooseLanguage(next);
    global.document.documentElement.lang = language;
    global.document.documentElement.dataset.language = language;
    if (persist) {
      try { global.localStorage.setItem(storageKey, language); } catch (_) { /* Private mode can disable storage. */ }
    }
    translatePage();
    global.document.querySelectorAll('.language-toggle').forEach(button => {
      button.textContent = language === 'en' ? '中文' : 'EN';
      const label = t(language === 'en' ? 'language.toChinese' : 'language.toEnglish');
      button.setAttribute('aria-label', label);
      button.setAttribute('title', label);
    });
    global.document.dispatchEvent(new global.CustomEvent('blog:language-change', { detail: { language } }));
  }
  global.BlogI18n = { t, setText, setLanguage, getLanguage: () => language,
    syncComments: (instance, container) => syncComments(instance, container, language, messages) };
  global.document.querySelectorAll('.language-toggle').forEach(button => {
    button.addEventListener('click', () => setLanguage(language === 'en' ? 'zh-CN' : 'en'));
  });
  setLanguage(language, false);
})(typeof window === 'object' ? window : globalThis);
