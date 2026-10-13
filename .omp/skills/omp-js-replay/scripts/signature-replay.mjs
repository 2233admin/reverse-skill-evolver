import { createHash } from 'node:crypto';

function validateJson(value, ancestors = new Set(), depth = 0) {
  if (value === null || ['string', 'boolean'].includes(typeof value)) return;
  if (typeof value === 'number' && Number.isFinite(value)) return;
  if (typeof value !== 'object' || depth > 64 || ancestors.has(value))
    throw new TypeError('Fixture input must be finite JSON without cycles (maximum depth 64)');
  const array = Array.isArray(value);
  if (!array && ![Object.prototype, null].includes(Object.getPrototypeOf(value)))
    throw new TypeError('Fixture input must contain only plain JSON objects');
  const keys = Reflect.ownKeys(value);
  if (array && keys.length !== value.length + 1)
    throw new TypeError('Fixture arrays must be dense without additional properties');
  ancestors.add(value);
  for (const key of keys) {
    if (array && key === 'length') continue;
    if (array && (typeof key !== 'string' || !/^(0|[1-9]\d*)$/.test(key) || Number(key) >= value.length))
      throw new TypeError('Fixture arrays must be dense without additional properties');
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (typeof key !== 'string' || !descriptor.enumerable || !('value' in descriptor))
      throw new TypeError('Fixture input cannot contain symbols, hidden properties or accessors');
    validateJson(descriptor.value, ancestors, depth + 1);
  }
  ancestors.delete(value);
}

export async function compareSignatures(fixtures, replay, { maxCases = 100 } = {}) {
  if (!Array.isArray(fixtures) || typeof replay !== 'function')
    throw new TypeError('Expected a fixture array and a replay function');
  if (!Number.isSafeInteger(maxCases) || maxCases < 1)
    throw new RangeError('maxCases must be a positive safe integer');
  validateJson(fixtures);
  const ids = new Set();
  for (const fixture of fixtures) {
    if (!fixture || Array.isArray(fixture) || typeof fixture !== 'object'
        || typeof fixture.id !== 'string' || !fixture.id.trim() || ids.has(fixture.id)
        || typeof fixture.expected !== 'string' || !Object.hasOwn(fixture, 'input'))
      throw new TypeError('Fixtures require unique nonempty ids, JSON input and string expected signatures');
    ids.add(fixture.id);
  }
  const baseline = fixtures.map(({ id, input, expected }) => {
    const snapshot = structuredClone(input);
    return {
      id, input: snapshot, expected,
      input_sha256: createHash('sha256').update(JSON.stringify(snapshot)).digest('hex'),
    };
  });
  const cases = [];
  const counts = { matched: 0, mismatched: 0, failed: 0 };
  for (const fixture of baseline.slice(0, maxCases)) {
    const { id, input, expected, input_sha256 } = fixture;
    const row = {
      id, input_sha256,
      matched: false, expected, actual: null, error: null,
    };
    try {
      const actual = await replay(structuredClone(input), { id });
      if (typeof actual !== 'string') {
        row.error = 'non_string_signature';
        counts.failed++;
      } else {
        row.actual = actual;
        row.matched = actual === expected;
        counts[row.matched ? 'matched' : 'mismatched']++;
      }
    } catch {
      // Callback messages can contain cookies or request bodies; retain only the failure category.
      row.error = 'replay_failed';
      counts.failed++;
    }
    cases.push(row);
  }
  const complete = cases.length === baseline.length;
  return {
    schema_version: 1,
    coverage: { total: baseline.length, processed: cases.length, remaining: baseline.length - cases.length, complete },
    counts, passed: complete && baseline.length > 0 && counts.failed === 0 && counts.mismatched === 0,
    cases,
  };
}
