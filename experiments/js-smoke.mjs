/**
 * End-to-end smoke check of the JavaScript server and client.
 *
 * Run with `node experiments/js-smoke.mjs` from the `js` directory.
 */

import {
  createLinoApp,
  createLinoClient,
  MemoryStore,
} from "../js/src/index.js";

const app = createLinoApp({ title: "Items API", version: "1.0.0", cors: true });
const store = new MemoryStore({
  items: [{ name: "first" }, { name: "second" }],
});
app.resource("/items", store, { name: "item" });
app.get("/health", () => ({ status: "ok" }));

const server = app.listen(0);
await new Promise((resolve) => server.once("listening", resolve));
const base = `http://127.0.0.1:${server.address().port}`;
const client = createLinoClient(base);

const show = (label, value) => console.log(`\n### ${label}\n${value}`);

show("health", await (await fetch(`${base}/health`)).text());
show("description", await (await fetch(`${base}/.well-known/lino-api`)).text());
show(
  "openapi",
  (await (await fetch(`${base}/.well-known/openapi.json`)).text()).slice(
    0,
    300,
  ),
);

const created = await client.post("/items", { name: "third", done: false });
show(
  "created",
  `${created.status} ${created.location}\n${JSON.stringify(created.data)}`,
);

const listed = await client.list("/items", { limit: 2, sort: "-name" });
show("list", JSON.stringify(listed));

const one = await client.get(`/items/${created.data.id}`);
show("get", `${one.status} etag=${one.etag}\n${JSON.stringify(one.data)}`);

const notModified = await client.get(`/items/${created.data.id}`, {
  ifNoneMatch: one.etag,
});
show("conditional get", String(notModified.status));

const patched = await client.patch(
  `/items/${created.data.id}`,
  { done: true },
  { ifMatch: one.etag },
);
show("patch", `${patched.status} ${JSON.stringify(patched.data)}`);

try {
  await client.patch(
    `/items/${created.data.id}`,
    { done: false },
    { ifMatch: one.etag },
  );
} catch (error) {
  show("stale If-Match", `${error.status} ${error.problem.title}`);
}

show("allow", (await client.options("/items/1")).join(", "));

try {
  await client.request("PUT", "/health", { body: {} });
} catch (error) {
  show("405", `${error.status} allow=${error.response.headers.get("allow")}`);
}

try {
  await client.get("/missing");
} catch (error) {
  show("404", `${error.status} ${error.problem.type}`);
}

const notAcceptable = await fetch(`${base}/health`, {
  headers: { Accept: "image/png" },
});
show("406", `${notAcceptable.status} ${await notAcceptable.text()}`);

const unsupported = await fetch(`${base}/items`, {
  method: "POST",
  headers: { "Content-Type": "application/xml" },
  body: "<item/>",
});
show("415", `${unsupported.status}`);

const deleted = await client.delete(`/items/${created.data.id}`);
show("delete", String(deleted.status));

const asJson = await fetch(`${base}/health`, {
  headers: { Accept: "application/json" },
});
show(
  "json negotiation",
  `${asJson.headers.get("content-type")} ${await asJson.text()}`,
);

server.close();
