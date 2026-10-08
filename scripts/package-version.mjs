#!/usr/bin/env node

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

export function validateVersion(version) {
  if (
    typeof version !== "string" ||
    !/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(version)
  ) {
    throw new Error(
      `Expected a single semantic version, got ${JSON.stringify(version)}`,
    );
  }
  return version;
}

// Inspect the named manifest section, never tool settings or dependencies.
export function manifestSection(content, section) {
  const headers = [...content.matchAll(/^\[([^\]\r\n]+)\][^\r\n]*\r?\n/gm)];
  const index = headers.findIndex((header) => header[1] === section);
  if (index < 0) throw new Error(`Missing [${section}] section`);
  const start = headers[index].index + headers[index][0].length;
  const end = headers[index + 1]?.index ?? content.length;
  return { start, end, text: content.slice(start, end) };
}

export function tomlVersion(content, section) {
  const versions = [
    ...manifestSection(content, section).text.matchAll(
      /^version[ \t]*=[ \t]*"([^"\r\n]*)"/gm,
    ),
  ];
  if (versions.length !== 1)
    throw new Error(`Expected one version in [${section}]`);
  return validateVersion(versions[0][1]);
}

export function getPackageVersion(root = ".") {
  const js = validateVersion(
    JSON.parse(readFileSync(resolve(root, "js/package.json"), "utf8")).version,
  );
  const rust = tomlVersion(
    readFileSync(resolve(root, "rust/Cargo.toml"), "utf8"),
    "package",
  );
  const python = tomlVersion(
    readFileSync(resolve(root, "python/pyproject.toml"), "utf8"),
    "project",
  );
  if (js !== rust || js !== python) {
    throw new Error(
      `Package versions must agree: npm=${js}, crates.io=${rust}, PyPI=${python}`,
    );
  }
  return js;
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(resolve(process.argv[1])).href
) {
  try {
    console.log(getPackageVersion());
  } catch (error) {
    console.error(error.message);
    if (process.env.DEBUG) console.error(error.stack);
    process.exitCode = 1;
  }
}
