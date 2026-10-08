#!/usr/bin/env node

// Changeset and manual releases share one version, three manifests and changelogs.
import { readFileSync, writeFileSync, readdirSync, unlinkSync } from "node:fs";
import { resolve } from "node:path";
import { parseArgs } from "node:util";
import { pathToFileURL } from "node:url";
import {
  getPackageVersion,
  manifestSection,
  validateVersion,
} from "./package-version.mjs";

export function bumpVersion(version, bump) {
  const [major, minor, patch] = validateVersion(version).split(".").map(Number);
  if (bump === "major") return `${major + 1}.0.0`;
  if (bump === "minor") return `${major}.${minor + 1}.0`;
  if (bump === "patch") return `${major}.${minor}.${patch + 1}`;
  throw new Error(`Invalid bump type: ${bump}`);
}

function replaceTomlVersion(content, section, version) {
  const { start, end, text } = manifestSection(content, section);
  return (
    content.slice(0, start) +
    text.replace(
      /^version[ \t]*=[ \t]*"[^"\r\n]*"/m,
      `version = "${version}"`,
    ) +
    content.slice(end)
  );
}

export function versionPackages({ root = ".", bump, description } = {}) {
  const read = (file) => readFileSync(resolve(root, file), "utf8");
  const current = getPackageVersion(root);
  const files = readdirSync(resolve(root, ".changeset"))
    .filter((file) => file.endsWith(".md") && file !== "README.md")
    .sort();
  const descriptions = [];
  const manual = Boolean(bump);
  if (!bump) {
    if (!files.length) return current;
    const ranks = { patch: 0, minor: 1, major: 2 };
    bump = "patch";
    for (const file of files) {
      const content = read(`.changeset/${file}`);
      const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/);
      const type = match?.[1].match(
        /^["']lino-rest-api["']:\s*(patch|minor|major)\s*$/m,
      )?.[1];
      if (!type || !match[2].trim())
        throw new Error(`Invalid changeset: ${file}`);
      if (ranks[type] > ranks[bump]) bump = type;
      descriptions.push(match[2].trim());
    }
  } else {
    descriptions.push(description || `Manual ${bump} release`);
  }
  const version = bumpVersion(current, bump);
  const updates = new Map();
  const pkg = JSON.parse(read("js/package.json"));
  pkg.version = version;
  updates.set("js/package.json", JSON.stringify(pkg, null, 2) + "\n");
  const lock = JSON.parse(read("js/package-lock.json"));
  if (lock.version !== current || lock.packages[""].version !== current)
    throw new Error("JavaScript lockfile version is out of sync");
  lock.version = lock.packages[""].version = version;
  updates.set("js/package-lock.json", JSON.stringify(lock, null, 2) + "\n");
  updates.set(
    "python/pyproject.toml",
    replaceTomlVersion(read("python/pyproject.toml"), "project", version),
  );
  updates.set(
    "rust/Cargo.toml",
    replaceTomlVersion(read("rust/Cargo.toml"), "package", version),
  );
  const rustLock = read("rust/Cargo.lock");
  const selfEntry = /(^name = "lino-rest-api"\r?\nversion = ")([^"\r\n]*)(")/m;
  if (rustLock.match(selfEntry)?.[2] !== current)
    throw new Error("Rust lockfile version is out of sync");
  updates.set(
    "rust/Cargo.lock",
    rustLock.replace(
      selfEntry,
      (_match, before, _old, after) => before + version + after,
    ),
  );
  const date = new Date().toISOString().slice(0, 10);
  for (const language of ["js", "rust", "python"]) {
    const path = `${language}/CHANGELOG.md`;
    const changelog = read(path);
    if (!/^## \[Unreleased\]/m.test(changelog))
      throw new Error(`Missing Unreleased heading in ${path}`);
    const entry = `## [Unreleased]\n\n## [${version}] - ${date}\n\n${descriptions.map((text) => `- ${text}`).join("\n")}\n\n`;
    updates.set(
      path,
      changelog.replace(/^## \[Unreleased\]\s*\n/m, () => entry),
    );
  }
  // Validate every input before writing or removing a changeset.
  for (const [file, content] of updates)
    writeFileSync(resolve(root, file), content);
  if (!manual)
    for (const file of files) unlinkSync(resolve(root, ".changeset", file));
  return version;
}

export function main() {
  try {
    const { values } = parseArgs({
      options: {
        "bump-type": { type: "string", default: process.env.BUMP_TYPE },
        description: { type: "string", default: process.env.DESCRIPTION },
      },
    });
    console.log(
      versionPackages({
        bump: values["bump-type"],
        description: values.description,
      }),
    );
  } catch (error) {
    console.error(error.message);
    if (process.env.DEBUG) console.error(error.stack);
    process.exitCode = 1;
  }
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(resolve(process.argv[1])).href
)
  main();
