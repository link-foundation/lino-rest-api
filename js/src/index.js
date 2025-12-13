/**
 * lino-rest-api - REST API framework using Links Notation instead of JSON.
 *
 * This module provides middleware and utilities for Express.js to handle
 * requests and responses in Links Notation (LINO) format.
 */

export { linoMiddleware, linoBodyParser, linoResponse } from './middleware.js';
export { createLinoApp, LinoApp } from './app.js';
