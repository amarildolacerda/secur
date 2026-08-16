const test = require('node:test');
const assert = require('node:assert');
const { transitionFault, nextRetryIntervalMs, FAULT_DEFAULTS } = require('../../src/static/camera_fault.js');

test('erro vindo de estado limpo -> retrying e recarrega', () => {
  const { state, reload, offline } = transitionFault(null, 'error', 1000);
  assert.strictEqual(state.status, 'retrying');
  assert.strictEqual(state.firstFailAt, 1000);
  assert.strictEqual(reload, true);
  assert.strictEqual(offline, false);
});

test('erro dentro do limiar continua retrying', () => {
  const s = { status: 'retrying', firstFailAt: 1000, timer: null };
  const { state, offline } = transitionFault(s, 'error', 1000 + 60000, FAULT_DEFAULTS);
  assert.strictEqual(state.status, 'retrying');
  assert.strictEqual(offline, false);
});

test('erro apos limiar de 5min -> offline', () => {
  const s = { status: 'retrying', firstFailAt: 1000, timer: null };
  const { state, offline } = transitionFault(s, 'error', 1000 + 300000, FAULT_DEFAULTS);
  assert.strictEqual(state.status, 'offline');
  assert.strictEqual(offline, true);
});

test('load -> recupera (estado nulo)', () => {
  const s = { status: 'offline', firstFailAt: 1000, timer: null };
  const { state, reload } = transitionFault(s, 'load', 5000);
  assert.strictEqual(state, null);
  assert.strictEqual(reload, false);
});

test('intervalo de retry usa valor offline quando offline', () => {
  const s = { status: 'offline', firstFailAt: 0, timer: null };
  assert.strictEqual(nextRetryIntervalMs(s, FAULT_DEFAULTS), FAULT_DEFAULTS.offlineRetryIntervalMs);
  assert.strictEqual(nextRetryIntervalMs(null, FAULT_DEFAULTS), FAULT_DEFAULTS.retryIntervalMs);
  assert.strictEqual(nextRetryIntervalMs({ status: 'retrying', firstFailAt: 0, timer: null }, FAULT_DEFAULTS), FAULT_DEFAULTS.retryIntervalMs);
});
