/**
 * LinoApp - Express application wrapper with LINO support.
 *
 * Provides a convenient way to create Express applications that
 * communicate using Links Notation format by default.
 */

import express from 'express';
import { linoMiddleware, LINO_CONTENT_TYPE } from './middleware.js';
import { encode, decode } from './vendor/codec.js';

/**
 * LinoApp class - wraps Express with LINO support.
 */
export class LinoApp {
  /**
   * Create a new LinoApp instance.
   */
  constructor() {
    this.app = express();
    this.app.use(linoMiddleware());
  }

  /**
   * Register a GET route.
   *
   * @param {string} path - Route path
   * @param {Function} handler - Route handler (req, res) => data or Promise<data>
   */
  get(path, handler) {
    this.app.get(path, this._wrapHandler(handler));
  }

  /**
   * Register a POST route.
   *
   * @param {string} path - Route path
   * @param {Function} handler - Route handler (req, res) => data or Promise<data>
   */
  post(path, handler) {
    this.app.post(path, this._wrapHandler(handler));
  }

  /**
   * Register a PUT route.
   *
   * @param {string} path - Route path
   * @param {Function} handler - Route handler (req, res) => data or Promise<data>
   */
  put(path, handler) {
    this.app.put(path, this._wrapHandler(handler));
  }

  /**
   * Register a DELETE route.
   *
   * @param {string} path - Route path
   * @param {Function} handler - Route handler (req, res) => data or Promise<data>
   */
  delete(path, handler) {
    this.app.delete(path, this._wrapHandler(handler));
  }

  /**
   * Register a PATCH route.
   *
   * @param {string} path - Route path
   * @param {Function} handler - Route handler (req, res) => data or Promise<data>
   */
  patch(path, handler) {
    this.app.patch(path, this._wrapHandler(handler));
  }

  /**
   * Use Express middleware.
   *
   * @param  {...any} args - Middleware arguments
   */
  use(...args) {
    this.app.use(...args);
  }

  /**
   * Start the server.
   *
   * @param {number} port - Port to listen on
   * @param {Function} [callback] - Callback when server starts
   * @returns {object} HTTP server instance
   */
  listen(port, callback) {
    return this.app.listen(port, callback);
  }

  /**
   * Get the underlying Express app.
   *
   * @returns {object} Express application
   */
  getExpressApp() {
    return this.app;
  }

  /**
   * Wrap a handler to automatically encode responses as LINO.
   *
   * @param {Function} handler - Route handler
   * @returns {Function} Wrapped handler
   * @private
   */
  _wrapHandler(handler) {
    return async (req, res) => {
      try {
        const result = await handler(req, res);
        // Only send response if handler returned data
        // (handler might have already sent response via res.lino())
        if (result !== undefined && !res.headersSent) {
          res.lino(result);
        }
      } catch (err) {
        if (!res.headersSent) {
          res.lino({ error: err.message }, 500);
        }
      }
    };
  }
}

/**
 * Create a new LinoApp instance.
 *
 * @returns {LinoApp} New LinoApp instance
 */
export function createLinoApp() {
  return new LinoApp();
}

// Re-export utilities
export { encode, decode, LINO_CONTENT_TYPE };
