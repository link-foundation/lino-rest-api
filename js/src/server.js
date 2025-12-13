/**
 * Example server demonstrating lino-rest-api usage.
 *
 * This server provides a simple REST API using Links Notation
 * instead of JSON for data exchange.
 */

import { createLinoApp } from './app.js';

const app = createLinoApp();

// In-memory data store for demo
const items = new Map();
let nextId = 1;

// GET /items - List all items
app.get('/items', (req) => {
  return {
    items: Array.from(items.values()),
    count: items.size,
  };
});

// GET /items/:id - Get item by ID
app.get('/items/:id', (req, res) => {
  const id = parseInt(req.params.id, 10);
  const item = items.get(id);

  if (!item) {
    res.lino({ error: 'Item not found' }, 404);
    return;
  }

  return item;
});

// POST /items - Create new item
app.post('/items', (req) => {
  const id = nextId++;
  const item = {
    id,
    ...req.body,
    createdAt: new Date().toISOString(),
  };

  items.set(id, item);

  return { created: item };
});

// PUT /items/:id - Update item
app.put('/items/:id', (req, res) => {
  const id = parseInt(req.params.id, 10);

  if (!items.has(id)) {
    res.lino({ error: 'Item not found' }, 404);
    return;
  }

  const item = {
    id,
    ...req.body,
    updatedAt: new Date().toISOString(),
  };

  items.set(id, item);

  return { updated: item };
});

// DELETE /items/:id - Delete item
app.delete('/items/:id', (req, res) => {
  const id = parseInt(req.params.id, 10);

  if (!items.has(id)) {
    res.lino({ error: 'Item not found' }, 404);
    return;
  }

  items.delete(id);

  return { deleted: id };
});

// Health check endpoint
app.get('/health', () => {
  return { status: 'ok', timestamp: new Date().toISOString() };
});

// Start server
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`LINO REST API server running on port ${PORT}`);
  console.log(`Try: curl -H "Content-Type: text/lino" http://localhost:${PORT}/health`);
});
