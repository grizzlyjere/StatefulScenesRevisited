/* Exercise the actual panel methods without starting Home Assistant or a browser. */
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const vm = require('node:vm');

let Panel;
const clipboard = { writeText: async () => {} };
vm.runInNewContext(readFileSync('custom_components/stateful_scenes_revisited/frontend/panel.js', 'utf8'), {
  navigator: { clipboard },
  HTMLElement: class {},
  customElements: { get: () => undefined, define: (_, component) => { Panel = component; } },
  document: { createTextNode: text => ({ textContent: text }), createElement: () => ({
    dataset: {}, children: [], attributes: {},
    append(...children) { this.children.push(...children); },
    setAttribute(name, value) { this.attributes[name] = value; },
    removeAttribute(name) { delete this.attributes[name]; },
  }) },
});

function panel(callWS) {
  const instance = Object.create(Panel.prototype);
  const fields = new Map();
  instance.$ = id => {
    if (!fields.has(id)) fields.set(id, {
      value: '', children: [], attributes: {}, focus() {},
      setAttribute(name, value) { this.attributes[name] = value; },
      removeAttribute(name) { delete this.attributes[name]; }, replaceChildren(...children) { this.children = children; },
      append(...children) { this.children.push(...children); },
      querySelectorAll() { return []; },
    });
    return fields.get(id);
  };
  instance.generation = 1;
  instance.data = { scenes: [], scene_scope: 'tag', scene_tag: 'evening' };
  instance._hass = { callWS };
  instance.notice = (message, error) => { instance.lastNotice = { message, error }; };
  return instance;
}

function choices(instance) {
  return instance.$('tag').children.map(option => [option.value, option.textContent]);
}

test('global ignore list parses names and preserves drafts across live updates', () => {
  const instance = panel(async () => {});
  instance.data.ignored_attributes = ['supported_color_modes', 'effect_list', 'supported_features'];
  instance.render();
  assert.equal(instance.$('global-attributes').value, 'supported_color_modes\neffect_list\nsupported_features');
  instance.$('global-attributes').value = ' effect_list, custom_mode\n\neffect_list, brightness ';
  instance.render();
  assert.deepEqual(Array.from(instance.globalIgnoredAttributes()), ['effect_list', 'custom_mode', 'brightness']);
  instance.data.ignored_attributes = ['custom_mode'];
  instance.render();
  assert.equal(instance.$('global-attributes').value, 'custom_mode');
  instance.$('global-attributes').value = ' \n, ';
  assert.deepEqual(Array.from(instance.globalIgnoredAttributes()), []);
});

test('scene choices identify global exclusions without losing local drafts', () => {
  const instance = panel(async () => {});
  instance.data.scenes = [{
    key: 'desk', entity_id: 'scene.desk', name: 'Desk', monitored: true,
    attributes: ['effect_list'], comparison: [], differences: [],
    options: { brightness_tolerance: 3, ignored_attributes: [] },
  }];
  instance.data.ignored_attributes = ['effect_list'];
  instance.render();
  let label = instance.$('attributes').children[0];
  assert.equal(label.children[1].textContent, 'effect_list (ignored globally)');
  label.children[0].checked = false;
  instance.$('attributes').querySelectorAll = () => [label.children[0]];
  instance.data.ignored_attributes = [];
  instance.render();
  label = instance.$('attributes').children[0];
  assert.equal(label.children[1].textContent, 'effect_list');
  assert.equal(label.children[0].checked, false);
});

test('loads existing Home Assistant labels even when scene snapshot has no tags', async () => {
  const instance = panel(async message => {
    assert.equal(message.type, 'config/label_registry/list');
    return [{ label_id: 'work', name: 'Work' }, { label_id: 'evening', name: 'Evening' }];
  });
  await instance.refreshLabels();
  assert.deepEqual(choices(instance), [
    ['', 'Select a label'], ['evening', 'Evening'], ['work', 'Work'], ['__new__', 'Add a new label…'],
  ]);
  assert.equal(instance.$('tag').value, 'evening');
  assert.equal(instance.$('tag').disabled, false);
});

test('refresh updates names and deletions while preserving unsaved label creation', async () => {
  let labels = [{ label_id: 'evening', name: 'Evening' }];
  const instance = panel(async () => labels);
  await instance.refreshLabels();
  instance.$('tag').value = '__new__';
  instance.$('new-tag').value = 'My scenes';
  labels = [{ label_id: 'evening', name: 'Renamed' }, { label_id: 'new', name: 'New label' }];
  await instance.refreshLabels();
  assert.equal(instance.$('tag').value, '__new__');
  assert.equal(instance.$('new-tag').value, 'My scenes');
  assert.equal(instance.$('new-tag').disabled, false);
  assert.ok(choices(instance).some(([id, name]) => id === 'evening' && name === 'Renamed'));
  labels = [];
  await instance.refreshLabels();
  assert.ok(choices(instance).some(([id, name]) => id === 'evening' && name.includes('deleted')));
  assert.equal(instance.$('tag').value, '__new__');
});

test('failed registry request keeps snapshot labels and shows an error', async () => {
  const instance = panel(async () => { throw new Error('Connection lost'); });
  instance.data.tags = [{ id: 'evening', name: 'Evening' }];
  instance.renderScope();
  await instance.refreshLabels();
  assert.ok(choices(instance).some(([id]) => id === 'evening'));
  assert.equal(instance.lastNotice.message, 'Unable to load labels: Connection lost');
  assert.equal(instance.lastNotice.error, true);
});

test('ignores responses after disconnect and superseded refresh requests', async () => {
  const pending = [];
  const instance = panel(() => new Promise(resolve => pending.push(resolve)));
  const first = instance.refreshLabels();
  const second = instance.refreshLabels();
  pending[1]([{ label_id: 'evening', name: 'Newest' }]);
  await second;
  pending[0]([{ label_id: 'evening', name: 'Stale' }]);
  await first;
  assert.ok(choices(instance).some(([, name]) => name === 'Newest'));
  const disconnected = instance.refreshLabels();
  instance.generation++;
  pending[2]([]);
  await disconnected;
  assert.ok(choices(instance).some(([, name]) => name === 'Newest'));
});


test('shows the registered switch ID and follows live Home Assistant state updates', () => {
  const instance = panel();
  instance.selected = 'evening';
  instance.data.scenes = [{ key: 'evening', monitored: true, switch_entity_id: 'switch.renamed' }];
  for (const state of ['on', 'off', 'unknown', 'unavailable']) {
    instance.hass = { states: { 'switch.renamed': { state } } };
    assert.equal(instance.$('switch-entity').textContent, 'switch.renamed');
    assert.equal(instance.$('switch-state').textContent, `State: ${state}`);
    assert.equal(instance.$('copy-switch').disabled, false);
  }
  instance.hass = { states: {} };
  assert.equal(instance.$('switch-state').textContent, 'State: unavailable');
  instance.data.scenes[0] = { key: 'evening', monitored: false };
  instance.renderSwitch();
  assert.equal(instance.$('switch-entity').textContent, 'No switch (scene is not monitored)');
  assert.equal(instance.$('copy-switch').disabled, true);
  assert.equal(instance.$('switch-state').textContent, '');
  instance.data.scenes[0].monitored = true;
  instance.renderSwitch();
  assert.equal(instance.$('switch-entity').textContent, 'Switch not available');
  instance.selected = null;
  instance.renderSwitch();
  assert.equal(instance.$('switch-details').hidden, true);
});

test('copies the selected switch ID and reports clipboard failures', async () => {
  const instance = panel();
  instance.selected = 'evening';
  instance.data.scenes = [{ key: 'evening', switch_entity_id: 'switch.renamed' }];
  let copied;
  clipboard.writeText = async value => { copied = value; };
  await instance.copySwitchEntity();
  assert.equal(copied, 'switch.renamed');
  assert.equal(instance.lastNotice.message, 'Copied switch.renamed to clipboard.');
  clipboard.writeText = async () => { throw new Error('Permission denied'); };
  await instance.copySwitchEntity();
  assert.equal(instance.lastNotice.error, true);
  assert.match(instance.lastNotice.message, /copy it manually: switch.renamed/);
  instance.selected = null;
  copied = null;
  clipboard.writeText = async value => { copied = value; };
  await instance.copySwitchEntity();
  assert.equal(copied, null);
});


test('scene navigation selects details, preserves live drafts, and combines filters', () => {
  const instance = panel();
  instance.$('enabled-only').checked = true;
  const scene = (key, monitored, area_id) => ({
    key, name: key, monitored, area_id, area_name: area_id,
    supported: true, matches: true, entity_count: 1, differences: [], attributes: [],
    options: { brightness_tolerance: 3, brightness_tolerance_override: null, ignored_attributes: [] },
  });
  instance.data.scenes = [scene('Evening', true, 'Lounge'), scene('Reading', false, null)];
  instance.render();
  assert.equal(instance.selected, 'Evening');
  assert.equal(instance.$('scene-list').children.length, 1);
  instance.$('enabled-only').checked = false;
  instance.render();
  const reading = instance.$('scene-list').children[1];
  reading.onclick();
  assert.equal(instance.$('scene-name').textContent, 'Reading');
  assert.equal(reading.attributes['aria-current'], 'true');
  assert.equal(instance.$('scene-list').children[0].attributes['aria-current'], undefined);
  instance.$('tolerance').value = '12';
  instance.render();
  assert.equal(instance.$('scene-list').children[1], reading);
  assert.equal(instance.$('tolerance').value, '12');
  reading.onclick();
  assert.equal(instance.$('tolerance').value, '12');
  instance.$('scene-search').value = 'EVEN';
  instance.render();
  assert.equal(instance.selected, 'Evening');
  instance.$('area').value = '__unassigned__';
  instance.render();
  assert.equal(instance.selected, null);
  assert.equal(instance.$('scene-list').children.length, 0);
  assert.equal(instance.$('scene-list-empty').hidden, false);
  assert.match(instance.$('configuration-empty').textContent, /No scenes match/);
  assert.equal(instance.$('activate').disabled, true);
  instance.$('scene-search').value = '';
  instance.render();
  assert.equal(instance.selected, 'Reading');
  assert.equal(instance.$('scene-list-empty').hidden, true);
});

test('comparison shows every compared entity and identifies the selected scene', () => {
  const instance = panel();
  const comparison = [
    { entity_id: 'light.charlotte_reading', field: 'state', expected: 'on', actual: 'on', reason: 'match' },
    { entity_id: 'fan.charlotte_ceiling_fan', field: 'percentage', expected: 50, actual: 75, reason: 'different' },
  ];
  instance.data.scenes = [{
    key: 'charlotte', entity_id: 'scene.charlotte_reading', name: 'Charlotte Reading',
    monitored: true, supported: true, matches: false, entity_count: 2,
    comparison, differences: comparison.slice(1), attributes: [],
    options: { brightness_tolerance: 3, ignored_attributes: [] },
  }];
  instance.render();
  assert.equal(instance.$('scene-entity').textContent, 'scene.charlotte_reading');
  assert.deepEqual(instance.$('diff').children.map(row => row.children.map(cell => cell.textContent)), [
    ['light.charlotte_reading / state', 'on', 'on', 'Matches'],
    ['fan.charlotte_ceiling_fan / percentage', '50', '75', 'Does not match'],
  ]);
  instance.data.scenes = [];
  instance.render();
  assert.equal(instance.$('scene-entity').textContent, '');
  assert.equal(instance.$('diff').children.length, 0);
});

test('debug explains ignored attributes, unavailable targets and empty definitions', () => {
  const instance = panel();
  const comparison = [
    { entity_id: 'light.desk', field: 'brightness', expected: 51, actual: 60, reason: 'ignored' },
    { entity_id: 'switch.vendor', field: 'state', expected: null, actual: 'on', reason: 'target_unavailable' },
  ];
  instance.data.scenes = [{
    key: 'desk', entity_id: 'scene.desk', name: 'Desk', monitored: true,
    supported: false, matches: false, issue: 'Target definition unavailable.', entity_count: 2,
    comparison, differences: [], attributes: [],
    options: { brightness_tolerance: 3, ignored_attributes: [] },
  }];
  instance.render();
  assert.deepEqual(instance.$('diff').children.map(row => row.children[3].textContent),
    ['Ignored', 'Cannot compare']);
  assert.equal(instance.$('diff').children[1].children[1].textContent, 'Target unavailable');
  instance.data.scenes[0].comparison = [];
  instance.render();
  assert.equal(instance.$('diff').children[0].children[0].textContent, 'Target definition unavailable.');
});

test('fresh detail request restores rows when the matching scene list has no comparisons', async () => {
  const scene = {
    key: 'charlotte', entity_id: 'scene.charlotte_reading', name: 'Charlotte Reading',
    monitored: true, supported: true, matches: true, entity_count: 4,
    differences: [], attributes: [], options: { brightness_tolerance: 3, ignored_attributes: [] },
  };
  const members = ['light.nightstand', 'light.ceiling', 'light.ceiling_group', 'switch.wall'];
  const instance = panel(async message => {
    assert.equal(message.type, 'stateful_scenes_revisited/comparison');
    assert.equal(message.scene_key, 'charlotte');
    return { ...scene, comparison: members.map(entity_id => ({ entity_id, field: 'state', expected: 'on', actual: 'on', reason: 'match' })) };
  });
  instance.data.scenes = [scene];
  instance.render();
  assert.match(instance.$('diff').children[0].children[0].textContent, /details missing for 4 entities/);
  instance.$('tolerance').value = '12';
  await instance.refreshComparison();
  assert.equal(instance.$('diff').children.length, 4);
  assert.deepEqual(instance.$('diff').children.map(row => row.children[0].textContent), members.map(id => `${id} / state`));
  assert.equal(instance.$('tolerance').value, '12');
});

test('detail errors are visible and late results cannot replace a different scene', async () => {
  let resolve;
  const instance = panel(() => new Promise(done => { resolve = done; }));
  instance.selected = 'charlotte';
  instance.data.scenes = [{ key: 'charlotte' }, { key: 'other' }];
  const pending = instance.refreshComparison();
  instance.selected = 'other';
  resolve({ comparison: [] });
  await pending;
  assert.equal(instance.data.scenes[0].comparison, undefined);
  instance.selected = 'charlotte';
  instance._hass.callWS = async () => { throw new Error('Connection lost'); };
  await instance.refreshComparison();
  assert.match(instance.lastNotice.message, /Connection lost/);
  assert.equal(instance.lastNotice.error, true);
  instance._hass.callWS = async () => ({ supported: true, entity_count: 4, comparison: [] });
  await instance.refreshComparison();
  assert.match(instance.lastNotice.message, /server returned no entity comparisons/);
});


test('tag picker loads chips, searches options, preserves drafts and resets for a new scene', async () => {
  let labels = [{ label_id: 'evening', name: 'Evening' }, { label_id: 'work', name: 'Work' }];
  const instance = panel(async () => labels);
  instance.selected = 'desk';
  instance.data.scenes = [
    { key: 'desk', can_label: true, label_ids: ['evening'] },
    { key: 'other', can_label: true, label_ids: [] },
  ];
  await instance.refreshLabels();
  assert.equal(instance.$('label-chips').children[0].children[0].textContent, 'Evening');
  instance.$('label-search').value = 'WOR';
  instance.labelsOpen = true;
  instance.renderSceneLabels();
  assert.equal(instance.$('label-listbox').children.length, 1);
  assert.equal(instance.$('label-listbox').children[0].textContent, 'Work');
  instance.$('label-listbox').children[0].onclick();
  assert.deepEqual(Array.from(instance.labelDraft), ['evening', 'work']);
  labels[1].name = 'Office';
  await instance.refreshLabels();
  assert.deepEqual(Array.from(instance.labelDraft), ['evening', 'work']);
  assert.equal(instance.$('label-chips').children[1].children[0].textContent, 'Office');
  assert.equal(instance.$('label-listbox').children[0].textContent, 'No labels match your search.');
  instance.renderSceneLabels();
  assert.equal(instance.labelsDirty, true);
  instance.selected = 'other';
  instance.renderSceneLabels();
  assert.deepEqual(Array.from(instance.labelDraft), []);
  assert.equal(instance.$('label-search').value, '');
  instance.data.scenes[1].can_label = false;
  instance.renderSceneLabels();
  assert.equal(instance.$('label-search').disabled, true);
  assert.match(instance.$('scene-label-help').textContent, /No generated switch/);
  labels = [];
  await instance.refreshLabels();
  assert.equal(instance.$('label-listbox').children[0].textContent, 'No labels defined in Home Assistant.');
});

test('tag picker supports keyboard navigation, selection, chip removal, clearing, and escape', async () => {
  const instance = panel();
  instance.data.tags = [{ id: 'evening', name: 'Evening' }, { id: 'work', name: 'Work' }];
  instance.data.scenes = [{ key: 'desk', can_label: true, label_ids: [] }];
  instance.selected = 'desk';
  instance.renderSceneLabels();
  const key = key => instance.labelKeydown({ key, preventDefault() {} });
  key('ArrowDown');
  assert.equal(instance.$('label-search').attributes['aria-activedescendant'], 'scene-label-option-0');
  key('Enter');
  key('ArrowDown');
  key('Enter');
  assert.deepEqual(Array.from(instance.labelDraft), ['evening', 'work']);
  assert.equal(instance.$('label-listbox').children[1].attributes['aria-selected'], 'true');
  instance.$('label-chips').children[0].children[1].onclick();
  assert.deepEqual(Array.from(instance.labelDraft), ['work']);
  key('Backspace');
  assert.deepEqual(Array.from(instance.labelDraft), []);
  assert.equal(instance.labelsDirty, false);
  key('Escape');
  instance.activeLabel = -1;
  key('ArrowUp');
  assert.equal(instance.activeLabel, 1);
  key('Escape');
  assert.equal(instance.$('label-search').attributes['aria-expanded'], 'false');
  assert.equal(instance.$('label-search').attributes['aria-activedescendant'], undefined);
  instance.changeSceneLabels(['work']);
  instance.changeSceneLabels([]);
  assert.equal(instance.$('label-chips').children.length, 0);
});

test('saving labels persists the complete selection, permits clearing, and preserves failed drafts', async () => {
  const messages = [];
  const instance = panel(async message => { messages.push(message); });
  instance.data.tags = [{ id: 'work', name: 'Work' }, { id: 'existing', name: 'Existing' }];
  instance.data.scenes = [{ key: 'desk', name: 'Desk', can_label: true, label_ids: ['existing'] }];
  instance.selected = 'desk';
  instance.renderSceneLabels();
  instance.changeSceneLabels(['work', 'existing']);
  await instance.saveSceneLabels();
  assert.equal(messages[0].type, 'stateful_scenes_revisited/scene_labels');
  assert.equal(messages[0].scene_key, 'desk');
  assert.deepEqual(Array.from(messages[0].label_ids), ['work', 'existing']);
  assert.equal(instance.$('save-labels').disabled, true);
  assert.equal(instance.lastNotice.message, 'Switch labels saved for Desk.');
  instance.changeSceneLabels([]);
  instance._hass.callWS = async () => { throw new Error('Connection lost'); };
  await instance.saveSceneLabels();
  assert.match(instance.lastNotice.message, /Connection lost/);
  assert.equal(instance.lastNotice.error, true);
  assert.deepEqual(Array.from(instance.labelDraft), []);
  assert.deepEqual(Array.from(instance.data.scenes[0].label_ids), ['work', 'existing']);
  assert.equal(instance.$('save-labels').disabled, false);
  instance._hass.callWS = async message => { messages.push(message); };
  await instance.saveSceneLabels();
  assert.deepEqual(Array.from(messages[1].label_ids), []);
  assert.deepEqual(Array.from(instance.data.scenes[0].label_ids), []);
});

test('tag picker is read only during save and ignores a response after disconnect', async () => {
  let resolve;
  const instance = panel(() => new Promise(done => { resolve = done; }));
  instance.data.scenes = [{ key: 'desk', name: 'Desk', can_label: true, label_ids: [] }];
  instance.selected = 'desk';
  instance.renderSceneLabels();
  instance.changeSceneLabels(['work']);
  const saving = instance.saveSceneLabels();
  assert.equal(instance.$('label-search').readOnly, true);
  instance.changeSceneLabels([]);
  assert.deepEqual(Array.from(instance.labelDraft), ['work']);
  instance.generation++;
  resolve();
  await saving;
  assert.deepEqual(instance.data.scenes[0].label_ids, []);
  assert.equal(instance.$('label-search').readOnly, false);
});


test('outside pointer clicks dismiss tag results without changing the selection or search', () => {
  const instance = panel();
  instance.selected = 'desk';
  instance.data.scenes = [{ key: 'desk', can_label: true, label_ids: [] }];
  instance.data.tags = [{ id: 'work', name: 'Work' }];
  instance.renderSceneLabels();
  instance.changeSceneLabels(['work']);
  instance.$('label-search').value = 'wor';
  instance.labelsOpen = true;
  instance.activeLabel = 0;
  instance.renderSceneLabels();
  instance.dismissLabelsOutside({ composedPath: () => [instance.$('label-search'), instance.$('label-picker')] });
  assert.equal(instance.$('label-listbox').hidden, false);
  instance.dismissLabelsOutside({ composedPath: () => [{}] });
  assert.equal(instance.$('label-listbox').hidden, true);
  assert.equal(instance.$('label-search').attributes['aria-expanded'], 'false');
  assert.equal(instance.$('label-search').attributes['aria-activedescendant'], undefined);
  assert.equal(instance.$('label-search').value, 'wor');
  assert.deepEqual(Array.from(instance.labelDraft), ['work']);
  assert.equal(instance.labelsDirty, true);
});

test('outside click listener is registered and cleaned up with the panel lifecycle', () => {
  const instance = panel();
  const calls = [];
  instance._hass = null;
  instance.labelOutsidePointerDown = () => {};
  instance.ownerDocument = {
    addEventListener(...args) { calls.push(['add', ...args]); },
    removeEventListener(...args) { calls.push(['remove', ...args]); },
  };
  instance.connectedCallback();
  instance.disconnectedCallback();
  assert.deepEqual(calls, [
    ['add', 'pointerdown', instance.labelOutsidePointerDown, true],
    ['remove', 'pointerdown', instance.labelOutsidePointerDown, true],
  ]);
});
