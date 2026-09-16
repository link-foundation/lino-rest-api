/**
 * A complete Links Notation REST service and a client that talks to it.
 *
 * Run with `npm run example` from the `js` directory. The script starts a server
 * on an ephemeral port, drives every part of the protocol through the client and
 * prints the wire representations, so the output doubles as a protocol tour.
 */

import {
  LINO_CONTENT_TYPE,
  MemoryStore,
  createLinoApp,
  createLinoClient,
  encode,
} from "../src/index.js";

const app = createLinoApp({
  title: "Tasks API",
  version: "1.0.0",
  description: "A task list served as Links Notation instead of JSON",
  cors: true,
});

const tasks = new MemoryStore();
tasks.create({ title: "Write the specification", done: true, priority: 1 });
tasks.create({ title: "Implement the server", done: false, priority: 2 });
tasks.create({ title: "Implement the client", done: false, priority: 3 });

// One call registers list, create, get, replace, merge and delete, together with
// automatic HEAD, automatic OPTIONS, 405, entity tags and problem details.
app.resource("/tasks", tasks, { name: "task" });

app.get("/health", () => ({ status: "ok" }), {
  summary: "Liveness probe",
});

const server = app.listen(0);
await new Promise((resolve) => server.once("listening", resolve));
const base = `http://127.0.0.1:${server.address().port}`;
const client = createLinoClient(base);

/**
 * Print a labelled section.
 *
 * @param {string} title - Section title
 * @returns {void}
 */
function section(title) {
  console.log(`\n=== ${title} ===`);
}

try {
  section("The service describes itself");
  const description = await client.describe();
  console.log(encode(description));

  section("Create a task");
  const created = await client.post("/tasks", {
    title: "Ship the release",
    done: false,
    priority: 4,
  });
  console.log(`status   ${created.status}`);
  console.log(`location ${created.location}`);
  console.log(`etag     ${created.etag}`);
  console.log(encode(created.data));

  section("List, filter, sort and paginate");
  const page = await client.list("/tasks", {
    done: false,
    sort: "-priority",
    limit: 2,
  });
  console.log(encode(page));

  section("The raw wire format");
  const raw = await fetch(`${base}/tasks/1`, {
    headers: { Accept: LINO_CONTENT_TYPE },
  });
  console.log(`content-type ${raw.headers.get("content-type")}`);
  console.log(await raw.text());

  section("Conditional requests");
  const current = await client.get("/tasks/1");
  const cached = await client.get("/tasks/1", { ifNoneMatch: current.etag });
  console.log(`unchanged    ${cached.status} (nothing was transferred)`);

  const updated = await client.patch(
    "/tasks/1",
    { done: false },
    { ifMatch: current.etag },
  );
  console.log(`updated      ${updated.status} with a new etag ${updated.etag}`);

  try {
    await client.patch("/tasks/1", { done: true }, { ifMatch: current.etag });
  } catch (error) {
    console.log(`lost update  ${error.status} ${error.message}`);
  }

  section("Errors are problem details, in Links Notation");
  try {
    await client.get("/tasks/999");
  } catch (error) {
    console.log(encode(error.problem));
  }

  section("Allowed methods");
  console.log(`/tasks     ${(await client.options("/tasks")).join(", ")}`);
  console.log(`/tasks/1   ${(await client.options("/tasks/1")).join(", ")}`);

  section("Delete");
  const deleted = await client.delete(created.location);
  console.log(`status ${deleted.status}`);
} finally {
  server.close();
}
