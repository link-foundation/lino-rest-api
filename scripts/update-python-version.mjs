#!/usr/bin/env node

/**
 * Update Python package version in pyproject.toml and CHANGELOG.md
 * This script adapts the npm changesets workflow for Python packages
 *
 * Usage: node scripts/update-python-version.mjs
 *
 * Uses link-foundation libraries:
 * - use-m: Dynamic package loading without package.json dependencies
 * - command-stream: Modern shell command execution with streaming support
 */

import { readFileSync, writeFileSync } from "fs";

// Load use-m dynamically
const { use } = eval(
  await (await fetch("https://unpkg.com/use-m/use.js")).text(),
);

// Import link-foundation libraries
const { $ } = await use("command-stream");

/**
 * Parse changesets to determine version bump
 */
async function parseChangesets() {
  const changesetDir = ".changeset";
  const { readdirSync, readFileSync: readFileSyncLocal } = await import("fs");

  const files = readdirSync(changesetDir).filter(
    (f) => f.endsWith(".md") && f !== "README.md",
  );

  if (files.length === 0) {
    return null;
  }

  let highestBump = "patch";
  const descriptions = [];

  for (const file of files) {
    const content = readFileSyncLocal(`${changesetDir}/${file}`, "utf8");

    // Extract YAML frontmatter
    const frontmatterMatch = content.match(/^---\n([\s\S]+?)\n---/);
    if (!frontmatterMatch) continue;

    const frontmatter = frontmatterMatch[1];

    // Check for bump type
    if (frontmatter.includes("major")) {
      highestBump = "major";
    } else if (frontmatter.includes("minor") && highestBump !== "major") {
      highestBump = "minor";
    }

    // Extract description (everything after ---)
    const description = content.split("---")[2]?.trim();
    if (description) {
      descriptions.push(description);
    }
  }

  return { bump: highestBump, descriptions, files };
}

/**
 * Bump version according to semver
 */
function bumpVersion(version, bump) {
  const [major, minor, patch] = version.split(".").map(Number);

  switch (bump) {
    case "major":
      return `${major + 1}.0.0`;
    case "minor":
      return `${major}.${minor + 1}.0`;
    case "patch":
      return `${major}.${minor}.${patch + 1}`;
    default:
      throw new Error(`Invalid bump type: ${bump}`);
  }
}

/**
 * Update pyproject.toml version
 */
function updatePyProjectVersion(newVersion) {
  const pyprojectPath = "./python/pyproject.toml";
  let content = readFileSync(pyprojectPath, "utf8");

  content = content.replace(
    /^version\s*=\s*"[^"]+"/m,
    `version = "${newVersion}"`,
  );

  writeFileSync(pyprojectPath, content, "utf8");
}

/**
 * Update CHANGELOG.md
 */
function updateChangelog(newVersion, descriptions) {
  const changelogPath = "./python/CHANGELOG.md";
  let content = readFileSync(changelogPath, "utf8");

  const today = new Date().toISOString().split("T")[0];
  const newEntry = `\n## [${newVersion}] - ${today}\n\n${descriptions.map((d) => `- ${d}`).join("\n")}\n`;

  // Insert after ## [Unreleased]
  content = content.replace(
    /## \[Unreleased\]\s*\n/,
    `## [Unreleased]\n${newEntry}`,
  );

  writeFileSync(changelogPath, content, "utf8");
}

/**
 * Delete processed changeset files
 */
async function deleteChangesets(files) {
  const { unlinkSync } = await import("fs");
  for (const file of files) {
    unlinkSync(`.changeset/${file}`);
  }
}

async function main() {
  try {
    const changesetInfo = await parseChangesets();

    if (!changesetInfo) {
      console.log("No changesets found, skipping version update");
      return;
    }

    const { bump, descriptions, files } = changesetInfo;

    // Get current version
    const pyprojectContent = readFileSync("./python/pyproject.toml", "utf8");
    const currentVersionMatch = pyprojectContent.match(
      /^version\s*=\s*"([^"]+)"/m,
    );
    if (!currentVersionMatch) {
      throw new Error("Could not find version in pyproject.toml");
    }
    const currentVersion = currentVersionMatch[1];

    // Calculate new version
    const newVersion = bumpVersion(currentVersion, bump);

    console.log(
      `Bumping version from ${currentVersion} to ${newVersion} (${bump})`,
    );

    // Update pyproject.toml
    updatePyProjectVersion(newVersion);
    console.log("✓ Updated pyproject.toml");

    // Update CHANGELOG.md
    updateChangelog(newVersion, descriptions);
    console.log("✓ Updated CHANGELOG.md");

    // Delete processed changesets
    await deleteChangesets(files);
    console.log(`✓ Deleted ${files.length} changeset file(s)`);

    console.log(`\n✅ Version updated to ${newVersion}`);
  } catch (error) {
    console.error("Error:", error.message);
    if (process.env.DEBUG) {
      console.error(error.stack);
    }
    process.exit(1);
  }
}

main();
