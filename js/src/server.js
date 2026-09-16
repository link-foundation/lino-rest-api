/**
 * Demonstration server.
 *
 * Serves a full CRUD resource plus a health endpoint, entirely in Links
 * Notation. Start it with `npm start` and explore it with curl:
 *
 * ```sh
 * curl -H 'Accept: text/lino' http://localhost:3000/.well-known/lino-api
 * curl -H 'Content-Type: text/lino' --data-binary $'(\n  name "first"\n)' \
 *   http://localhost:3000/items
 * ```
 */

import { createLinoApp } from "./app.js";
import { MemoryStore } from "./store.js";

const app = createLinoApp({
  title: "Items API",
  version: "1.0.0",
  cors: true,
});

const items = new MemoryStore({
  items: [
    { name: "first", done: false },
    { name: "second", done: true },
  ],
});

app.resource("/items", items, { name: "item" });

app.get("/health", () => ({ status: "ok", items: items.items.size }), {
  summary: "Health check",
});

const PORT = Number(process.env.PORT ?? 3000);

app.listen(PORT, () => {
  console.log(`LINO REST API server running on port ${PORT}`);
  console.log(
    `Try: curl -H "Accept: text/lino" http://localhost:${PORT}/health`,
  );
});
