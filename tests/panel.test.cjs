const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function environment() {
  const context = vm.createContext({
    HTMLElement: class {
      attachShadow() {
        this.shadowRoot = { innerHTML: '', getElementById: () => null, querySelectorAll: () => [] };
      }
    },
    localStorage: { getItem: () => '', setItem() {}, removeItem() {} },
    customElements: { get: () => false, define() {} },
  });
  vm.runInContext(fs.readFileSync('custom_components/lorawan_iobroker/panel.js', 'utf8') + '\nglobalThis.Panel = LoRaWANIobrokerPanel;', context);
  return context.Panel;
}
const payload = { sources: [{ entry_id: 'one', source: 'LoRaWAN.1', title: 'Bridge', devices: [], periodic_interval_minutes: 10 }] };
const tick = () => new Promise(resolve => setImmediate(resolve));

test('return shows cached data and filters while refreshing, without duplicate requests', async () => {
  const Panel = environment();
  let calls = 0;
  let resolve;
  const hass = { connection: {}, user: { id: 'admin' }, callApi: () => { calls++; return Promise.resolve(payload); } };
  const first = new Panel();
  first.hass = hass;
  await tick();
  first.view = 'flow'; first.search = 'kitchen'; first.integration = 'mqtt'; first.render();
  hass.callApi = () => { calls++; return new Promise(r => { resolve = r; }); };
  const second = new Panel();
  second.hass = hass;
  second.connectedCallback();
  second.hass = hass;
  assert.equal(calls, 2);
  assert.equal(second.data, payload);
  assert.equal(second.view, 'flow');
  assert.equal(second.search, 'kitchen');
  assert.equal(second.integration, 'mqtt');
  assert.match(second.shadowRoot.innerHTML, /flow-section/);
  assert.doesNotMatch(second.shadowRoot.innerHTML, /Lade Home-Assistant-Geräte/);
  resolve({ sources: [] });
  await tick();
  assert.equal(second.data.sources.length, 0);
  assert.match(second.shadowRoot.innerHTML, /Keine Quelle eingerichtet/);
});

test('initial loading, network errors, and retry', async () => {
  const Panel = environment();
  let reject;
  const hass = { connection: {}, user: { id: 'admin' }, callApi: () => new Promise((_, r) => { reject = r; }) };
  const panel = new Panel();
  panel.hass = hass;
  assert.doesNotMatch(panel.shadowRoot.innerHTML, /Keine Quelle eingerichtet/);
  reject(new Error('offline'));
  await tick();
  assert.match(panel.shadowRoot.innerHTML, /konnten nicht geladen/);
  assert.equal(panel.loading, false);
  hass.callApi = () => Promise.resolve(payload);
  await panel.refresh();
  assert.equal(panel.data, payload);
  hass.callApi = () => Promise.reject(new Error('offline'));
  await panel.refresh();
  assert.equal(panel.data, payload);
});

test('cache is separated by user and connection; revoked access clears data', async () => {
  const Panel = environment();
  const connection = {};
  const first = new Panel();
  first.hass = { connection, user: { id: 'a' }, callApi: () => Promise.resolve(payload) };
  await tick();
  for (const hass of [
    { connection: {}, user: { id: 'a' } },
    { connection, user: { id: 'b' } },
  ]) {
    const next = new Panel();
    next.hass = { ...hass, callApi: () => new Promise(() => {}) };
    assert.equal(next.data, null);
  }
  first._hass.callApi = () => Promise.reject({ status_code: 403 });
  await first.refresh();
  assert.equal(first.data, null);
});
