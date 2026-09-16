#!/usr/bin/env node

/**
 * Build the documentation website into `docs/site`.
 *
 * The site has two halves. The prose half is the markdown that already lives in
 * the repository — the landing page, the wire specification, the three package
 * guides and the case studies — rendered to HTML with a shared template, so a
 * page is written once and read both on GitHub and on the website. The
 * reference half is generated from the source of each package by its own
 * documentation tool: JSDoc, pdoc and rustdoc.
 *
 * Usage:
 *   node scripts/build-docs.mjs                 # everything
 *   node scripts/build-docs.mjs --pages         # prose only, no toolchains needed
 *   node scripts/build-docs.mjs --skip rust     # everything but the Rust reference
 */

import { spawnSync } from "node:child_process";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, posix, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { marked } from "marked";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const site = join(root, "docs/site");
const repository = "https://github.com/link-foundation/lino-rest-api";
const blob = `${repository}/blob/main`;

/**
 * The prose pages of the site, in navigation order.
 *
 * `source` is the markdown in the repository, `output` the path on the site.
 * Only the pages marked `nav` appear in the header.
 */
const pages = [
  { source: "docs/index.md", output: "index.html", title: "Home", nav: true },
  {
    source: "js/README.md",
    output: "guides/javascript/index.html",
    title: "JavaScript",
    nav: true,
  },
  {
    source: "python/README.md",
    output: "guides/python/index.html",
    title: "Python",
    nav: true,
  },
  {
    source: "rust/README.md",
    output: "guides/rust/index.html",
    title: "Rust",
    nav: true,
  },
  {
    source: "docs/spec/README.md",
    output: "spec/index.html",
    title: "Specification",
    nav: true,
  },
  {
    source: "docs/case-studies/issue-5/README.md",
    output: "case-studies/issue-5/index.html",
    title: "Case study: issue #5",
    nav: false,
  },
  {
    source: "js/CHANGELOG.md",
    output: "changelog/javascript/index.html",
    title: "JavaScript changelog",
    nav: false,
  },
  {
    source: "python/CHANGELOG.md",
    output: "changelog/python/index.html",
    title: "Python changelog",
    nav: false,
  },
  {
    source: "rust/CHANGELOG.md",
    output: "changelog/rust/index.html",
    title: "Rust changelog",
    nav: false,
  },
];

/** Where each generated API reference lands, and how to build it. */
const references = [
  {
    key: "javascript",
    title: "JavaScript API",
    entry: "api/javascript/index.html",
    build: buildJavaScriptReference,
  },
  {
    key: "python",
    title: "Python API",
    entry: "api/python/lino_rest_api.html",
    build: buildPythonReference,
  },
  {
    key: "rust",
    title: "Rust API",
    entry: "api/rust/lino_rest_api/index.html",
    build: buildRustReference,
  },
];

/** Every markdown source that becomes a page, mapped to its site path. */
const rendered = new Map(pages.map((page) => [page.source, page.output]));

/** The page being rendered, so that its links can be resolved relatively. */
let current = pages[0];

marked.use({
  gfm: true,
  walkTokens(token) {
    if (token.type === "link" || token.type === "image") {
      token.href = rewrite(token.href);
    }
  },
});

/**
 * Turn a link written for GitHub into one that works on the site.
 *
 * A link to a page of the site becomes a relative link between the two
 * generated files; a link to anything else in the repository becomes a link to
 * that file on GitHub; anything already absolute is left alone.
 */
function rewrite(href) {
  if (!href || /^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith("#")) {
    return href;
  }
  const [path, fragment] = splitFragment(href);
  if (path === "") return href;
  const target = posix.normalize(
    posix.join(posix.dirname(current.source), path),
  );
  const page = rendered.get(target) ?? rendered.get(`${target}/README.md`);
  if (page) {
    const from = posix.dirname(current.output);
    return `${posix.relative(from, page)}${fragment}`;
  }
  return `${blob}/${target}${fragment}`;
}

/** Split a link into its path and its `#fragment`, if it has one. */
function splitFragment(href) {
  const hash = href.indexOf("#");
  return hash === -1
    ? [href, ""]
    : [href.slice(0, hash), href.slice(hash)].map(String);
}

/** Escape the characters that may not appear in HTML text. */
function escape(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** The header navigation, with the current page marked. */
function navigation(page) {
  const from = posix.dirname(page.output);
  const links = pages
    .filter((entry) => entry.nav)
    .map((entry) => {
      const href = posix.relative(from, entry.output);
      const attributes =
        entry.output === page.output ? ' aria-current="page"' : "";
      return `<a href="${href}"${attributes}>${escape(entry.title)}</a>`;
    });
  for (const reference of references) {
    const href = posix.relative(from, reference.entry);
    links.push(`<a href="${href}">${escape(reference.title)}</a>`);
  }
  return links.join("\n        ");
}

/** Wrap rendered markdown in the site template. */
function template(page, body) {
  const suffix = page.output === "index.html" ? "" : " — lino-rest-api";
  const title = page.output === "index.html" ? "lino-rest-api" : page.title;
  const home = posix.relative(posix.dirname(page.output), "index.html");
  const styles = posix.relative(posix.dirname(page.output), "style.css");
  const icon = posix.relative(posix.dirname(page.output), "favicon.svg");
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>${escape(title + suffix)}</title>
    <meta
      name="description"
      content="A REST API framework and client that speak Links Notation instead of JSON, in JavaScript, Python and Rust."
    />
    <link rel="icon" href="${icon}" type="image/svg+xml" />
    <link rel="stylesheet" href="${styles}" />
  </head>
  <body>
    <header>
      <a class="brand" href="${home}">lino-rest-api</a>
      <nav>
        ${navigation(page)}
      </nav>
    </header>
    <main>
${body.trimEnd()}
    </main>
    <footer>
      <a href="${blob}/${page.source}">Edit this page on GitHub</a> ·
      <a href="${repository}">Source</a> ·
      <a href="${blob}/LICENSE">Unlicense</a>
    </footer>
  </body>
</html>
`;
}

/** Render every prose page. */
function buildPages() {
  for (const page of pages) {
    const source = join(root, page.source);
    if (!existsSync(source)) {
      console.log(`  skipped ${page.source} (no such file)`);
      continue;
    }
    current = page;
    const body = marked.parse(readFileSync(source, "utf8"));
    write(page.output, template(page, body));
    console.log(`  ${page.source} → ${page.output}`);
  }
  write("style.css", readFileSync(join(root, "docs/style.css"), "utf8"));
  write("favicon.svg", readFileSync(join(root, "docs/favicon.svg"), "utf8"));
  // Tell GitHub Pages to serve the files as they are, without Jekyll, which
  // would otherwise drop the rustdoc directories whose names start with `_`.
  write(".nojekyll", "");
}

/** Write a file below the site root, creating its directory. */
function write(output, contents) {
  const destination = join(site, output);
  mkdirSync(dirname(destination), { recursive: true });
  writeFileSync(destination, contents, "utf8");
}

/** Run a command, reporting whether it succeeded. */
function run(command, args, options = {}) {
  // An inline program is shown as a placeholder, so that the log stays readable.
  const shown = [command, ...args]
    .map((argument) => (argument.includes("\n") ? "<program>" : argument))
    .join(" ");
  console.log(`  $ ${shown}`);
  const result = spawnSync(command, args, {
    stdio: "inherit",
    shell: process.platform === "win32",
    ...options,
  });
  if (result.error || result.status !== 0) {
    console.log(`  ! ${shown} failed`);
    return false;
  }
  return true;
}

/** Generate the JavaScript reference with JSDoc. */
function buildJavaScriptReference() {
  return run("npx", ["--yes", "jsdoc", "-c", "jsdoc.json"], {
    cwd: join(root, "js"),
  });
}

/**
 * The program that generates the Python reference.
 *
 * The package resolves its optional FastAPI adapter through a module
 * `__getattr__`, so those names are absent from the module dictionary until
 * something asks for them, and pdoc — which reads that dictionary — would
 * report them as unresolvable. Touching them first, when FastAPI is installed,
 * puts them in place; pdoc then documents the module that is already imported.
 */
const pdocProgram = `
import sys

import lino_rest_api

for name in ("LinoAPI", "LinoAPIRoute", "LinoRequest", "LinoResponse", "lino_request_handler"):
    try:
        getattr(lino_rest_api, name)
    except ImportError:
        pass  # FastAPI is not installed; the adapter is optional.

sys.argv = ["pdoc", "lino_rest_api", "--output-directory", sys.argv[1]]
from pdoc.__main__ import cli

cli()
`;

/** Generate the Python reference with pdoc. */
function buildPythonReference() {
  return run("python3", ["-c", pdocProgram, join(site, "api/python")], {
    cwd: join(root, "python"),
    env: { ...process.env, PYTHONPATH: join(root, "python/src") },
  });
}

/** Generate the Rust reference with rustdoc, and copy it into the site. */
function buildRustReference() {
  if (!run("cargo", ["doc", "--no-deps"], { cwd: join(root, "rust") })) {
    return false;
  }
  const generated = join(root, "rust/target/doc");
  const destination = join(site, "api/rust");
  rmSync(destination, { recursive: true, force: true });
  cpSync(generated, destination, { recursive: true });
  return true;
}

/** Read the command line. */
function options(argv) {
  const skip = new Set();
  let pagesOnly = false;
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--pages") pagesOnly = true;
    else if (argument === "--skip") skip.add(argv[(index += 1)]);
    else if (argument.startsWith("--skip=")) skip.add(argument.slice(7));
    else throw new Error(`Unknown option: ${argument}`);
  }
  return { pagesOnly, skip };
}

function main() {
  const { pagesOnly, skip } = options(process.argv.slice(2));

  console.log("Rendering pages");
  buildPages();

  const failed = [];
  for (const reference of references) {
    if (pagesOnly || skip.has(reference.key)) {
      console.log(`Skipping the ${reference.key} reference`);
      continue;
    }
    console.log(`Generating the ${reference.key} reference`);
    if (!reference.build()) failed.push(reference.key);
  }

  console.log(`\nSite written to ${relative(root, site)}`);
  if (failed.length > 0) {
    console.error(
      `References that could not be generated: ${failed.join(", ")}`,
    );
    process.exit(1);
  }
}

main();
