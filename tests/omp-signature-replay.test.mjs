import assert from 'node:assert/strict';
import { createHash, createHmac } from 'node:crypto';
import { test } from 'node:test';
import { compareSignatures } from '../.omp/skills/omp-js-replay/scripts/signature-replay.mjs';

const sign = input => createHmac('sha256', 'fixture-only-key').update(JSON.stringify(input)).digest('hex');
const samples = () => [{ id: 'one', input: { value: 7, timestamp: 1700000000 }, expected: sign({ value: 7, timestamp: 1700000000 }) },
  { id: 'two', input: { value: 8, timestamp: 1700000000 }, expected: sign({ value: 8, timestamp: 1700000000 }) }];

test('sync and async signer use fixed baselines and input fingerprints', async () => {
  for (const replay of [sign, async input => sign(input)]) {
    const data = samples();
    const report = await compareSignatures(data, replay);
    assert.equal(report.passed, true);
    assert.equal(report.counts.matched, 2);
    assert.equal(report.cases[0].input_sha256, createHash('sha256').update(JSON.stringify(data[0].input)).digest('hex'));
    assert.equal(Object.hasOwn(report.cases[0], 'input'), false);
  }
});

test('mismatch, exception and non-string output have distinct failures with no raw error leak', async () => {
  const fixture = [samples()[0]];
  const mismatch = await compareSignatures(fixture, () => 'wrong');
  assert.equal(mismatch.counts.mismatched, 1);
  const failed = await compareSignatures(fixture, () => { throw new Error('private cookie body'); });
  assert.equal(failed.cases[0].error, 'replay_failed');
  assert.ok(!JSON.stringify(failed).includes('private cookie'));
  assert.equal((await compareSignatures(fixture, () => 7)).cases[0].error, 'non_string_signature');
});

test('callback and caller mutations cannot alter this run or later input baselines', async () => {
  const data = samples();
  const expectedTwo = data[1].expected;
  const report = await compareSignatures(data, (input, { id }) => {
    const result = sign(input);
    input.value = 999;
    if (id === 'one') {
      data[1].input.value = 999;
      data[1].expected = 'tampered';
      data.push({ id: 'extra', input: {}, expected: '' });
    }
    return result;
  });
  assert.equal(report.passed, true);
  assert.equal(report.coverage.total, 2);
  assert.equal(report.cases[1].expected, expectedTwo);
  assert.equal(report.cases[1].actual, expectedTwo);
});

test('partial and empty coverage never pass', async () => {
  const partial = await compareSignatures(samples(), sign, { maxCases: 1 });
  assert.deepEqual(partial.coverage, { total: 2, processed: 1, remaining: 1, complete: false });
  assert.equal(partial.passed, false);
  assert.equal((await compareSignatures([], sign)).passed, false);
});

test('maxCases snapshots only selected inputs and freezes the original total', async () => {
  const fixtures = Array.from({ length: 1000 }, (_, i) => ({ id: String(i), input: { value: 'x'.repeat(8192) }, expected: 'ok' }));
  const clone = globalThis.structuredClone;
  let clones = 0, calls = 0;
  globalThis.structuredClone = value => { clones++; return clone(value); };
  try {
    const report = await compareSignatures(fixtures, input => {
      calls++;
      input.value = 'changed';
      fixtures.length = 0;
      return 'ok';
    }, { maxCases: 1 });
    assert.equal(clones, 2);
    assert.equal(calls, 1);
    assert.deepEqual(report.coverage, { total: 1000, processed: 1, remaining: 999, complete: false });
    assert.equal(report.counts.matched, 1);
    assert.equal(report.passed, false);
  } finally { globalThis.structuredClone = clone; }
});

test('invalid unselected fixtures reject before replay or snapshots', async () => {
  const cycle = {}; cycle.self = cycle;
  for (const tail of [{ id: 'one', input: {}, expected: '' }, { id: 'tail', input: cycle, expected: '' }, { id: 'tail', input: {}, expected: 7 }]) {
    await assert.rejects(compareSignatures([samples()[0], tail], () => assert.fail('must not replay'), { maxCases: 1 }), TypeError);
  }
});

test('sample strings remain data', async () => {
  globalThis.fixtureExecuted = false;
  const input = 'globalThis.fixtureExecuted = true';
  assert.equal((await compareSignatures([{ id: 'code-string', input, expected: sign(input) }], sign)).passed, true);
  assert.equal(globalThis.fixtureExecuted, false);
});

test('invalid ids, expected, callback and budgets reject before replay', async () => {
  let calls = 0;
  const replay = () => { calls++; return ''; };
  for (const data of [[samples()[0], samples()[0]], [{ id: ' ', input: {}, expected: '' }], [{ id: 'one', input: {} }], [{ id: 'one', input: {}, expected: 7 }]])
    await assert.rejects(compareSignatures(data, replay), TypeError);
  await assert.rejects(compareSignatures(samples(), null), TypeError);
  for (const maxCases of [0, -1, 1.5, true, NaN]) await assert.rejects(compareSignatures(samples(), replay, { maxCases }), RangeError);
  assert.equal(calls, 0);
});

test('invalid JSON, cycles, sparse arrays, symbols and accessors never replay', async () => {
  const cycle = {}; cycle.self = cycle;
  const hidden = {}; Object.defineProperty(hidden, 'private', { value: 1 });
  let getterCalls = 0;
  const getter = {}; Object.defineProperty(getter, 'value', { enumerable: true, get() { getterCalls++; return 7; } });
  for (const input of [undefined, Infinity, NaN, cycle, new Date(), [,,], { [Symbol('private')]: 1 }, hidden, getter])
    await assert.rejects(compareSignatures([{ id: 'invalid', input, expected: '' }], () => assert.fail('must not replay')), TypeError);
  assert.equal(getterCalls, 0);
});

test('array subclasses cannot execute fixture iterator code', async () => {
  let executed = 0;
  class ExecutableFixtures extends Array {
    [Symbol.iterator]() { executed++; return super[Symbol.iterator](); }
  }
  const data = new ExecutableFixtures(...samples());
  await assert.rejects(compareSignatures(data, sign), TypeError);
  assert.equal(executed, 0);
});

test('proxy fixture traps cannot execute during validation', async () => {
  let executed = 0;
  const input = new Proxy({}, { ownKeys() { executed++; return []; } });
  await assert.rejects(compareSignatures([{ id: 'proxy', input, expected: '' }], sign), TypeError);
  assert.equal(executed, 0);
});
