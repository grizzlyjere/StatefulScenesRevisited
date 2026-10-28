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
  document: { createElement: () => ({
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
      value: '', children: [], replaceChildren(...children) { this.children = children; },
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
