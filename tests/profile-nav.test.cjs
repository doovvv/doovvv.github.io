const assert = require('node:assert/strict');
const test = require('node:test');
let selectProfileSection;
try { ({ selectProfileSection } = require('../assets/site.js')); } catch (_) { /* Not implemented yet. */ }

test('the final resume section is active at the bottom of a tall screen', () => {
  assert.equal(typeof selectProfileSection, 'function');
  const sections = [{ id: 'skills', top: -200 }, { id: 'writing', top: 273 }];
  assert.equal(selectProfileSection(sections, 175, false), 'skills');
  assert.equal(selectProfileSection(sections, 175, true), 'writing');
});
test('ordinary scrolling selects the most recently reached section', () => {
  assert.equal(typeof selectProfileSection, 'function');
  const sections = [{ id: 'overview', top: -600 }, { id: 'experience', top: 110 }, { id: 'education', top: 750 }];
  assert.equal(selectProfileSection(sections, 175, false), 'experience');
});
test('pages without a resume do not have a selected profile section', () => {
  assert.equal(typeof selectProfileSection, 'function');
  assert.equal(selectProfileSection([], 175, true), null);
});
