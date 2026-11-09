import { test, assert } from "test-anywhere";
import { readFileSync } from "node:fs";
import { BinaryLinoCodec, DecodeLimits, Link } from "links-notation";
import {
  createLinoApp,
  LinoClient,
  LinoClientError,
  encodeFor,
  decodeFrom,
  computeETag,
  LINO_BINARY_CONTENT_TYPE as binary,
  LINO_CONTENT_TYPE as text,
  BINARY_DECODE_LIMITS,
} from "../src/index.js";
import { withApp, rejects, throws } from "./helpers.js";

const cases = JSON.parse(
  readFileSync(new URL("./binary-fixtures.json", import.meta.url)),
);

test("binary typed AST preserves the portable value model and golden bytes", () => {
  for (const { value, hex } of cases) {
    const bytes = encodeFor(value, binary);
    assert.ok(bytes instanceof Uint8Array);
    assert.equal(Buffer.from(bytes).toString("hex"), hex);
    assert.deepEqual(decodeFrom(bytes, binary), value);
  }
  const shared = { value: 1 };
  const decoded = decodeFrom(encodeFor([shared, shared], binary), binary);
  assert.ok(decoded[0] === decoded[1]);
  const cyclic = [];
  cyclic.push(cyclic);
  const cycle = decodeFrom(encodeFor(cyclic, binary), binary);
  assert.ok(cycle[0] === cycle);
});

test("binary rejects malformed, truncated, trailing and over-depth packets", () => {
  const bytes = encodeFor({ ok: true }, binary);
  for (const packet of [
    new Uint8Array([0xff]),
    bytes.slice(0, -1),
    new Uint8Array([...bytes, 0]),
  ]) {
    assert.ok(throws(() => decodeFrom(packet, binary)));
  }
  const codec = new BinaryLinoCodec(
    undefined,
    new DecodeLimits({ ...BINARY_DECODE_LIMITS, maxDepth: 128 }),
  );
  let node = new Link("x", []);
  for (let i = 0; i < 70; i++) node = new Link(null, [node]);
  const deep = codec.encode([node]);
  assert.ok(throws(() => decodeFrom(deep, binary)));
});

test("binary client/server transport works without JSON, including errors, HEAD and ETags", async () => {
  const app = createLinoApp({ supported: [text, binary], maxBodyBytes: 4096 });
  app.post("/echo", (req) => req.body);
  app.get("/value", () => cases.at(-1).value);
  await withApp(app, async ({ base }) => {
    const client = new LinoClient(base, {
      accept: binary,
      contentType: binary,
    });
    const response = await client.post("/echo", cases.at(-1).value);
    assert.deepEqual(response.data, cases.at(-1).value);
    assert.equal(response.headers.get("content-type"), binary);
    const get = await client.get("/value");
    assert.equal(get.etag, computeETag(encodeFor(get.data, binary)));
    assert.equal(
      (await client.get("/value", { ifNoneMatch: get.etag })).status,
      304,
    );
    assert.equal((await client.head("/value")).data, undefined);
    const missing = await rejects(() => client.get("/missing"));
    assert.ok(missing instanceof LinoClientError);
    assert.equal(missing.problem.status, 404);
    for (const [headers, body, status] of [
      [{ Accept: "application/json" }, undefined, 406],
      [{ Accept: binary, "Content-Type": "application/json" }, "{}", 415],
      [{ Accept: binary, "Content-Type": binary }, new Uint8Array([0xff]), 400],
      [{ Accept: binary, "Content-Type": binary }, new Uint8Array(4097), 413],
    ]) {
      assert.equal(
        (await fetch(base + "/echo", { method: "POST", headers, body })).status,
        status,
      );
    }
    const description = await client.describe();
    assert.deepEqual(description.media_types, [text, binary]);
    const textClient = new LinoClient(base, {
      accept: text,
      contentType: text,
    });
    assert.deepEqual((await textClient.post("/echo", { ok: true })).data, {
      ok: true,
    });
  });
});

test("fetch binary decoding uses arrayBuffer even when the request asks for text", async () => {
  const client = new LinoClient("http://test", {
    fetch: async () => ({
      status: 200,
      ok: true,
      headers: new Headers({ "Content-Type": binary }),
      arrayBuffer: async () => encodeFor({ ok: true }, binary).buffer,
      text: async () => {
        throw new Error("binary must never be read as UTF-8");
      },
    }),
  });
  assert.deepEqual((await client.get("/")).data, { ok: true });
});

test("every binary graph budget rejects a small hostile packet", () => {
  const attacks = JSON.parse(
    readFileSync(new URL("./binary-limits.json", import.meta.url)),
  );
  for (const { limit, hex } of attacks) {
    const error = throws(() =>
      decodeFrom(new Uint8Array(Buffer.from(hex, "hex")), binary),
    );
    assert.ok(
      /limit|budget|excessive|too many|depth|nesting/i.test(error.message),
      `${limit}: ${error.message}`,
    );
  }
});
