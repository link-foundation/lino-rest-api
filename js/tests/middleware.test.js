/**
 * Tests for LINO middleware.
 */

import { test, assert } from 'test-anywhere';
import { encode, decode } from '../src/vendor/codec.js';
import {
  linoMiddleware,
  linoBodyParser,
  linoResponse,
  LINO_CONTENT_TYPE,
} from '../src/middleware.js';

test('LINO_CONTENT_TYPE should be text/lino', () => {
  assert.equal(LINO_CONTENT_TYPE, 'text/lino');
});

test('linoBodyParser should be a function', () => {
  assert.equal(typeof linoBodyParser, 'function');
});

test('linoMiddleware should be a function', () => {
  assert.equal(typeof linoMiddleware, 'function');
});

test('linoResponse should be a function', () => {
  assert.equal(typeof linoResponse, 'function');
});

test('encode and decode should roundtrip simple objects', () => {
  const original = { name: 'test', value: 42 };
  const encoded = encode(original);
  const decoded = decode(encoded);

  assert.deepEqual(decoded, original);
});

test('encode and decode should handle nested objects', () => {
  const original = {
    user: {
      name: 'Alice',
      age: 30,
    },
    items: [1, 2, 3],
  };
  const encoded = encode(original);
  const decoded = decode(encoded);

  assert.deepEqual(decoded, original);
});

test('encode and decode should handle special values', () => {
  const original = {
    nullValue: null,
    boolTrue: true,
    boolFalse: false,
    integer: 123,
    float: 3.14,
    string: 'hello world',
    array: [1, 'two', true],
  };
  const encoded = encode(original);
  const decoded = decode(encoded);

  assert.deepEqual(decoded, original);
});
