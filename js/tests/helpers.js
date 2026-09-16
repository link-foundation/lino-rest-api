/**
 * Shared helpers for the HTTP level tests.
 */

import { createLinoClient } from "../src/index.js";

/**
 * Start an application on an ephemeral port.
 *
 * @param {object} app - {@link LinoApp} to serve
 * @returns {Promise<{base: string, server: object, client: object, close: Function}>} Live server handle
 */
export async function startApp(app) {
  const server = app.getExpressApp().listen(0);
  await new Promise((resolve) => server.once("listening", resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  return {
    base,
    server,
    client: createLinoClient(base),
    close: () => new Promise((resolve) => server.close(resolve)),
  };
}

/**
 * Run a function against a live application and always shut the server down.
 *
 * @param {object} app - {@link LinoApp} to serve
 * @param {Function} fn - Receives the server handle
 * @returns {Promise<void>} Resolves once the server is closed
 */
export async function withApp(app, fn) {
  const handle = await startApp(app);
  try {
    await fn(handle);
  } finally {
    await handle.close();
  }
}

/**
 * Await a call that is expected to fail and return the rejection.
 *
 * `test-anywhere` has no `assert.rejects`, and every runtime in the matrix needs
 * the same behaviour.
 *
 * @param {Function} fn - Call that should reject
 * @returns {Promise<*>} The rejection value
 * @throws {Error} When the call resolves instead
 */
export async function rejects(fn) {
  try {
    await fn();
  } catch (error) {
    return error;
  }
  throw new Error("Expected the call to be rejected, but it resolved");
}

/**
 * Call something that is expected to fail and return the thrown value.
 *
 * `test-anywhere`'s `assert.throws` treats its second argument as a message, so
 * a constructor or predicate passed there is silently ignored; returning the
 * error lets a test assert on it explicitly instead.
 *
 * @param {Function} fn - Call that should throw
 * @returns {*} The thrown value
 * @throws {Error} When the call returns normally
 */
export function throws(fn) {
  try {
    fn();
  } catch (error) {
    return error;
  }
  throw new Error("Expected the call to throw, but it returned");
}
