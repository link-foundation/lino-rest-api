/**
 * Tests for the application over real HTTP.
 */

import { test, assert } from "test-anywhere";
import { createLinoApp, LinoApp } from "../src/app.js";
import { decode, encode } from "../src/codec.js";
import { created, noContent, status } from "../src/response.js";
import { LinoHttpError } from "../src/problem.js";
import { throws, withApp } from "./helpers.js";

/**
 * Build an application exercising the whole surface.
 *
 * @returns {LinoApp} Application under test
 */
function buildApp() {
  const app = createLinoApp({ title: "Test API", version: "2.0.0" });
  app.get("/health", () => ({ status: "ok" }), { summary: "Health check" });
  app.post("/echo", (req) => created({ echoed: req.body }, "/echo/1"));
  app.put("/replace", (req) => ({ replaced: req.body }));
  app.patch("/merge", (req) => status(202, { queued: req.body }));
  app.delete("/gone", () => noContent());
  app.get("/boom", () => {
    throw new LinoHttpError(409, "Already exists");
  });
  app.get("/crash", () => {
    throw new Error("unexpected");
  });
  app.get("/raw", (req, res) => {
    res.lino({ raw: true }, 200);
  });
  return app;
}

test("createLinoApp returns a LinoApp", () => {
  const app = createLinoApp();
  assert.ok(app instanceof LinoApp);
  assert.equal(typeof app.get, "function");
  assert.equal(typeof app.post, "function");
  assert.equal(typeof app.put, "function");
  assert.equal(typeof app.patch, "function");
  assert.equal(typeof app.delete, "function");
  assert.equal(typeof app.use, "function");
  assert.equal(typeof app.listen, "function");
  assert.ok(app.getExpressApp());
});

test("route registration is chainable and rejects unknown methods", () => {
  const app = createLinoApp();
  assert.ok(app.get("/a", () => ({})) === app);
  const error = throws(() => app.route("TRACE", "/a", () => ({})));
  assert.ok(error instanceof TypeError);
});

test("a handler return value is encoded as Links Notation", async () => {
  await withApp(buildApp(), async ({ base }) => {
    const response = await fetch(`${base}/health`);
    assert.equal(response.status, 200);
    assert.equal(
      response.headers.get("content-type"),
      "text/lino; charset=utf-8",
    );
    assert.equal(response.headers.get("vary"), "Accept");
    assert.deepEqual(decode(await response.text()), { status: "ok" });
  });
});

test("a request body is decoded from Links Notation", async () => {
  await withApp(buildApp(), async ({ base }) => {
    const response = await fetch(`${base}/echo`, {
      method: "POST",
      headers: { "Content-Type": "text/lino" },
      body: encode({ name: "Alice" }),
    });
    assert.equal(response.status, 201);
    assert.equal(response.headers.get("location"), "/echo/1");
    assert.deepEqual(decode(await response.text()), {
      echoed: { name: "Alice" },
    });
  });
});

test("explicit results carry their status code", async () => {
  await withApp(buildApp(), async ({ base }) => {
    const accepted = await fetch(`${base}/merge`, {
      method: "PATCH",
      headers: { "Content-Type": "text/lino" },
      body: encode({ a: 1 }),
    });
    assert.equal(accepted.status, 202);

    const deleted = await fetch(`${base}/gone`, { method: "DELETE" });
    assert.equal(deleted.status, 204);
    assert.equal(await deleted.text(), "");
  });
});

test("a handler may write the response itself", async () => {
  await withApp(buildApp(), async ({ base }) => {
    const response = await fetch(`${base}/raw`);
    assert.deepEqual(decode(await response.text()), { raw: true });
  });
});

test("a thrown LinoHttpError becomes problem details", async () => {
  await withApp(buildApp(), async ({ base }) => {
    const response = await fetch(`${base}/boom`);
    assert.equal(response.status, 409);
    assert.equal(
      response.headers.get("content-type"),
      "application/problem+lino; charset=utf-8",
    );
    const problem = decode(await response.text());
    assert.equal(problem.status, 409);
    assert.equal(problem.title, "Conflict");
    assert.equal(problem.instance, "/boom");
  });
});

test("an unexpected error becomes a 500 without leaking the stack", async () => {
  await withApp(buildApp(), async ({ base }) => {
    const response = await fetch(`${base}/crash`);
    assert.equal(response.status, 500);
    const problem = decode(await response.text());
    assert.equal(problem.status, 500);
    assert.equal(problem.stack, undefined);
  });
});

test("exposeStack attaches the stack to 5xx problems", async () => {
  const app = createLinoApp({ exposeStack: true });
  app.get("/crash", () => {
    throw new Error("unexpected");
  });
  await withApp(app, async ({ base }) => {
    const problem = decode(await (await fetch(`${base}/crash`)).text());
    assert.ok(problem.stack.includes("Error: unexpected"));
  });
});

test("the service description reflects the registered routes", async () => {
  await withApp(buildApp(), async ({ base }) => {
    const description = decode(
      await (await fetch(`${base}/.well-known/lino-api`)).text(),
    );
    assert.equal(description.info.title, "Test API");
    assert.equal(description.info.version, "2.0.0");
    const health = description.routes.find((route) => route.path === "/health");
    assert.equal(health.summary, "Health check");
    assert.deepEqual(health.methods, ["GET", "HEAD", "OPTIONS"]);
  });
});

test("the OpenAPI document is served as JSON", async () => {
  await withApp(buildApp(), async ({ base }) => {
    const response = await fetch(`${base}/.well-known/openapi.json`);
    assert.equal(
      response.headers.get("content-type"),
      "application/json; charset=utf-8",
    );
    const document = await response.json();
    assert.equal(document.openapi, "3.1.0");
    assert.ok(document.paths["/health"].get);
  });
});

test("the description can be turned off", async () => {
  const app = createLinoApp({ describe: false });
  app.get("/health", () => ({ status: "ok" }));
  await withApp(app, async ({ base }) => {
    assert.equal((await fetch(`${base}/.well-known/lino-api`)).status, 404);
  });
});

test("middleware added with use runs before the routes", async () => {
  const app = createLinoApp();
  app.use((req, res, next) => {
    res.set("X-Trace", "on");
    next();
  });
  app.get("/health", () => ({ status: "ok" }));
  await withApp(app, async ({ base }) => {
    assert.equal((await fetch(`${base}/health`)).headers.get("x-trace"), "on");
  });
});
