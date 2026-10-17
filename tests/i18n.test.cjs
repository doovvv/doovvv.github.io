const assert = require('node:assert/strict');
const test = require('node:test');
const messages = require('../content/ui.json');
const { chooseLanguage, formatMessage, syncComments } = require('../assets/i18n.js');

test('a first visit and unsupported saved values use English', () => {
  for (const saved of [undefined, null, '', 'fr', 'zh', '<script>']) assert.equal(chooseLanguage(saved), 'en');
  assert.equal(chooseLanguage('zh-CN'), 'zh-CN');
  assert.equal(chooseLanguage('en'), 'en');
});
test('dynamic search counts follow the current interface language', () => {
  assert.equal(formatMessage(messages, 'en', 'search.found', { count: 2 }), '2 notes found');
  assert.equal(formatMessage(messages, 'zh-CN', 'search.found', { count: 2 }), '找到 2 篇相关笔记');
});
test('an untranslated article title is preserved inside a localized label', () => {
  assert.equal(formatMessage(messages, 'en', 'cover.read', { title: '人工智能' }), 'Read 人工智能');
  assert.equal(formatMessage(messages, 'zh-CN', 'cover.read', { title: '人工智能' }), '阅读 人工智能');
});
test('loaded comments switch language without replacing a draft or reply form', () => {
  const element = (textContent = '') => ({ textContent, attributes: {}, setAttribute(name, value) { this.attributes[name] = value; } });
  const editor = element();
  editor.value = '未发送的评论';
  editor.replyTarget = 'original-comment';
  const submit = element('Submit');
  const countLabel = { nodeType: 3, textContent: ' Comments' };
  const count = { childNodes: [{ nodeType: 1, textContent: '5' }, countLabel] };
  const time = element('3 minutes ago');
  const selectors = { '.veditor': [editor], '.vsubmit': [submit], '.vcount': [count], '.vempty, .vtime': [time] };
  const container = { querySelectorAll: selector => selectors[selector] || [] };
  const phrases = Object.fromEntries(Object.keys(messages).filter(key => key.startsWith('valine.')).map(key => [key.slice(7), messages[key].en]));
  const instance = { cfg: {}, i18n: { t: key => phrases[key], extend: next => Object.assign(phrases, next), locale: () => {} } };
  syncComments(instance, container, 'zh-CN', messages);
  assert.equal(submit.textContent, '提交');
  assert.equal(countLabel.textContent, ' 条评论');
  assert.equal(time.textContent, '3 分钟前');
  assert.equal(editor.attributes.placeholder, messages['comments.placeholder']['zh-CN']);
  assert.equal(editor.value, '未发送的评论');
  assert.equal(editor.replyTarget, 'original-comment');
  assert.equal(instance.i18n.t('reply'), '回复');
  syncComments(instance, container, 'en', messages);
  assert.equal(submit.textContent, 'Submit');
  assert.equal(time.textContent, '3 minutes ago');
});
