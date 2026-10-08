#!/usr/bin/env node

import { appendFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";
import { parseArgs } from "node:util";
import { pathToFileURL } from "node:url";
import { getPackageVersion, validateVersion } from "./package-version.mjs";

export async function isPublished(registry, version, fetcher = fetch) {
  validateVersion(version);
  const endpoints = {
    npm: `https://registry.npmjs.org/lino-rest-api/${version}`,
    "crates-io": `https://crates.io/api/v1/crates/lino-rest-api/${version}`,
    pypi: `https://pypi.org/pypi/lino-rest-api/${version}/json`,
  };
  if (!endpoints[registry]) throw new Error(`Unknown registry: ${registry}`);
  const url = new URL(endpoints[registry]);
  // npm metadata can be cached by its CDN for five minutes after a publish.
  // A unique URL also prevents stale 404s when resuming a partial release.
  url.searchParams.set("_", randomUUID());
  const response = await fetcher(url, {
    cache: "no-store",
    headers: {
      accept: "application/json",
      "cache-control": "no-cache",
      "user-agent":
        "lino-rest-api-release (https://github.com/link-foundation/lino-rest-api)",
    },
    signal: AbortSignal.timeout(30_000),
  });
  if (response.status === 404) return false;
  if (!response.ok)
    throw new Error(`${registry} lookup failed: HTTP ${response.status}`);
  const body = await response.json();
  const publishedVersion =
    registry === "npm"
      ? body.version
      : registry === "crates-io"
        ? body.version?.num
        : body.info?.version;
  if (publishedVersion !== version)
    throw new Error(
      `${registry} returned an unexpected version: ${JSON.stringify(publishedVersion)}`,
    );
  return true;
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(resolve(process.argv[1])).href
) {
  try {
    const { values } = parseArgs({ options: { registry: { type: "string" } } });
    const version = getPackageVersion();
    const published = await isPublished(values.registry, version);
    console.log(
      `${values.registry}: lino-rest-api@${version} ${published ? "already published; skipping" : "not published"}`,
    );
    if (process.env.GITHUB_OUTPUT)
      appendFileSync(process.env.GITHUB_OUTPUT, `published=${published}\n`);
  } catch (error) {
    console.error(error.message);
    if (process.env.DEBUG) console.error(error.stack);
    process.exitCode = 1;
  }
}
