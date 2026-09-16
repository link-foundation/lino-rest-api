/**
 * Tests for the service description (specification §9).
 */

import { test, assert } from "test-anywhere";
import {
  LINO_API_DESCRIPTION_VERSION,
  infoObject,
  openApiDocument,
  pathParameters,
  serviceDescription,
  toOpenApiPath,
} from "../src/description.js";
import { LINO_CONTENT_TYPE } from "../src/media-type.js";

const info = { title: "Items API", version: "1.0.0" };
const routes = [
  { path: "/items", methods: ["GET", "POST"], summary: "Item collection" },
  { path: "/items/:id", methods: ["GET", "DELETE"] },
];

test("the description lists the version, the info and the media types", () => {
  const description = serviceDescription(info, routes);
  assert.equal(description.lino_api, LINO_API_DESCRIPTION_VERSION);
  assert.deepEqual(description.info, info);
  assert.ok(description.media_types.includes(LINO_CONTENT_TYPE));
  assert.deepEqual(description.routes, routes);
});

test("path parameters are translated to the OpenAPI template syntax", () => {
  assert.equal(toOpenApiPath("/items/:id/tags/:tag"), "/items/{id}/tags/{tag}");
  assert.deepEqual(pathParameters("/items/:id/tags/:tag"), ["id", "tag"]);
});

test("the OpenAPI document declares every representation", () => {
  const document = openApiDocument(info, routes);
  assert.equal(document.openapi, "3.1.0");
  const operation = document.paths["/items"].get;
  assert.ok(LINO_CONTENT_TYPE in operation.responses[200].content);
  assert.equal(operation.summary, "Item collection");
});

test("bodies are declared for methods that carry one", () => {
  const document = openApiDocument(info, routes);
  assert.ok(document.paths["/items"].post.requestBody);
  assert.ok(!document.paths["/items"].get.requestBody);
});

test("path parameters appear in the operation", () => {
  const document = openApiDocument(info, routes);
  assert.deepEqual(
    document.paths["/items/{id}"].get.parameters.map((p) => p.name),
    ["id"],
  );
});

test("every operation declares a default problem response", () => {
  const document = openApiDocument(info, routes);
  for (const path of Object.values(document.paths)) {
    for (const operation of Object.values(path)) {
      assert.ok(operation.responses.default);
    }
  }
});

test("a prose description is carried by both documents", () => {
  const described = { ...info, description: "A task list" };
  assert.equal(
    serviceDescription(described, routes).info.description,
    "A task list",
  );
  assert.equal(
    openApiDocument(described, routes).info.description,
    "A task list",
  );
});

test("the info object omits an absent description", () => {
  assert.deepEqual(infoObject(info), info);
  assert.ok(!("description" in infoObject({ ...info, description: "" })));
});
