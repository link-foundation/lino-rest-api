#!/usr/bin/env node

/**
 * Create GitHub release from Python CHANGELOG.md
 * Usage: node scripts/create-github-release-python.mjs --release-version <version> --repository <owner/repo>
 *
 * Uses link-foundation libraries:
 * - use-m: Dynamic package loading without package.json dependencies
 * - command-stream: Modern shell command execution with streaming support
 * - lino-arguments: Unified configuration from CLI args, env vars, and .lenv files
 */

import { readFileSync } from "fs";

// Load use-m dynamically
const { use } = eval(
  await (await fetch("https://unpkg.com/use-m/use.js")).text(),
);

// Import link-foundation libraries
const { $ } = await use("command-stream");
const { makeConfig } = await use("lino-arguments");

// Parse CLI arguments using lino-arguments
const config = makeConfig({
  yargs: ({ yargs, getenv }) =>
    yargs
      .option("release-version", {
        type: "string",
        default: getenv("RELEASE_VERSION", ""),
        describe: "Version number to release (e.g., 1.0.0)",
      })
      .option("repository", {
        type: "string",
        default: getenv("REPOSITORY", ""),
        describe: "GitHub repository (owner/repo)",
      }),
});

const { releaseVersion, repository } = config;

if (!releaseVersion || !repository) {
  console.error("Error: Both --release-version and --repository are required");
  process.exit(1);
}

/**
 * Extract release notes from CHANGELOG.md for a specific version
 * @param {string} version
 * @returns {string|null}
 */
function extractReleaseNotes(version) {
  try {
    const changelog = readFileSync("./python/CHANGELOG.md", "utf8");

    // Find the section for this version
    // Pattern: ## [version] - date
    const versionRegex = new RegExp(
      `## \\[${version.replace(/\./g, "\\.")}\\][^\\n]*\\n([\\s\\S]*?)(?=\\n## |$)`,
    );
    const match = changelog.match(versionRegex);

    if (!match) {
      console.error(`Could not find release notes for version ${version}`);
      return null;
    }

    return match[1].trim();
  } catch (error) {
    console.error("Error reading CHANGELOG.md:", error.message);
    return null;
  }
}

async function main() {
  try {
    const releaseNotes = extractReleaseNotes(releaseVersion);

    if (!releaseNotes) {
      console.error("Failed to extract release notes");
      process.exit(1);
    }

    console.log(`Creating GitHub release for version ${releaseVersion}...`);

    // Create the release using gh CLI
    // Pass the body via stdin to avoid shell escaping issues
    const releasePayload = JSON.stringify({
      tag_name: `v${releaseVersion}`,
      name: `v${releaseVersion}`,
      body: releaseNotes,
      draft: false,
      prerelease: false,
    });

    await $`echo ${releasePayload} | gh release create v${releaseVersion} --repo ${repository} --title v${releaseVersion} --notes-file -`;

    console.log(`✅ Created GitHub release for v${releaseVersion}`);
  } catch (error) {
    console.error("Error:", error.message);
    if (process.env.DEBUG) {
      console.error(error.stack);
    }
    process.exit(1);
  }
}

main();
