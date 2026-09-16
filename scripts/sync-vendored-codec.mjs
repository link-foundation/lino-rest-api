#!/usr/bin/env node
/**
 * Vendor the Python implementation of `lino-objects-codec` into this repository.
 *
 * The codec is published to npm and to crates.io, so the JavaScript and Rust
 * packages depend on it directly. It is not published to PyPI, so the Python
 * package carries a verbatim copy of the upstream sources instead, pinned to a
 * commit and checksummed.
 *
 * Usage:
 *   node scripts/sync-vendored-codec.mjs          # download and write the copy
 *   node scripts/sync-vendored-codec.mjs --check  # fail when the copy drifted
 *   node scripts/sync-vendored-codec.mjs --ref <sha>
 *
 * When upstream publishes `lino-objects-codec` to PyPI, delete this script and
 * the vendored package, and depend on the released distribution instead.
 */

import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const REPOSITORY = "link-foundation/lino-objects-codec";

/** Upstream commit the vendored copy is taken from. */
export const DEFAULT_REF = "8642bfbf907cb0b7125718ee0e0b26dbf13e94ba";

/** Files copied from the upstream Python package, in import order. */
const MODULES = ["__init__.py", "debug.py", "format.py", "readable.py", "codec.py"];

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const vendorDirectory = join(
  root,
  "python/src/lino_rest_api/vendor/lino_objects_codec",
);
const fixturesDirectory = join(root, "python/tests/fixtures");
const manifestPath = join(vendorDirectory, "VENDORED.md");

/**
 * Download one file from the pinned upstream commit.
 *
 * @param {string} ref - Upstream commit
 * @param {string} path - Repository relative path
 * @returns {Promise<string>} File contents
 */
async function download(ref, path) {
  const url = `https://raw.githubusercontent.com/${REPOSITORY}/${ref}/${path}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to download ${url}: ${response.status}`);
  }
  return response.text();
}

/**
 * Hash a file the way the manifest records it.
 *
 * @param {string} contents - File contents
 * @returns {string} Hexadecimal SHA-256
 */
function digest(contents) {
  return createHash("sha256").update(contents, "utf-8").digest("hex");
}

/**
 * Fetch every vendored file at a commit.
 *
 * @param {string} ref - Upstream commit
 * @returns {Promise<Map<string, string>>} Local path to contents
 */
async function collect(ref) {
  const files = new Map();
  for (const module of MODULES) {
    files.set(
      join(vendorDirectory, module),
      await download(ref, `python/src/link_notation_objects_codec/${module}`),
    );
  }
  // The cross-language fixtures are how the Python copy is proven to produce the
  // same bytes as the npm package the JavaScript side uses.
  files.set(
    join(fixturesDirectory, "readable-format-cases.json"),
    await download(ref, "fixtures/readable-format/cases.json"),
  );
  return files;
}

/**
 * Render the provenance manifest.
 *
 * @param {string} ref - Upstream commit
 * @param {Map<string, string>} files - Local path to contents
 * @returns {string} Manifest contents
 */
function manifest(ref, files) {
  const rows = [...files.entries()]
    .map(([path, contents]) => {
      const relative = path.slice(root.length + 1);
      return `| \`${relative}\` | \`${digest(contents)}\` |`;
    })
    .join("\n");

  return `# Vendored \`lino-objects-codec\`

These files are a verbatim copy of the Python implementation of
[\`lino-objects-codec\`](https://github.com/${REPOSITORY}). The codec is published
to npm and crates.io but not to PyPI, so the Python package carries the sources
instead of depending on a release.

- Upstream: https://github.com/${REPOSITORY}
- Commit: \`${ref}\`
- Synchronised by: \`node scripts/sync-vendored-codec.mjs\`

Do not edit these files. Run the script to update them, and
\`node scripts/sync-vendored-codec.mjs --check\` to verify that the copy still
matches the pinned commit. \`python/tests/test_codec_parity.py\` proves the copy
encodes the shared fixtures exactly as the npm package does.

| File | SHA-256 |
| ---- | ------- |
${rows}
`;
}

/**
 * Entry point.
 *
 * @returns {Promise<void>} Resolves when the copy is written or verified
 */
async function main() {
  const argv = process.argv.slice(2);
  const check = argv.includes("--check");
  const refIndex = argv.indexOf("--ref");
  const ref = refIndex === -1 ? DEFAULT_REF : argv[refIndex + 1];

  const files = await collect(ref);
  files.set(manifestPath, manifest(ref, files));

  if (check) {
    let drifted = false;
    for (const [path, contents] of files) {
      const current = await readFile(path, "utf-8").catch(() => undefined);
      if (current !== contents) {
        console.error(`drifted: ${path.slice(root.length + 1)}`);
        drifted = true;
      }
    }
    if (drifted) {
      console.error(`\nRun: node scripts/sync-vendored-codec.mjs --ref ${ref}`);
      process.exitCode = 1;
      return;
    }
    console.log(`Vendored codec matches ${REPOSITORY}@${ref.slice(0, 12)}`);
    return;
  }

  for (const [path, contents] of files) {
    await mkdir(dirname(path), { recursive: true });
    await writeFile(path, contents, "utf-8");
    console.log(`wrote ${path.slice(root.length + 1)}`);
  }
}

await main();
