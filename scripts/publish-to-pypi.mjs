#!/usr/bin/env node

/**
 * Publish Python package to PyPI using OIDC trusted publishing
 * Usage: node scripts/publish-to-pypi.mjs [--should-pull]
 *   should_pull: Optional flag to pull latest changes before publishing (for release job)
 *
 * Uses link-foundation libraries:
 * - use-m: Dynamic package loading without package.json dependencies
 * - command-stream: Modern shell command execution with streaming support
 * - lino-arguments: Unified configuration from CLI args, env vars, and .lenv files
 */

import { readFileSync, appendFileSync } from "fs";

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
    yargs.option("should-pull", {
      type: "boolean",
      default: getenv("SHOULD_PULL", false),
      describe: "Pull latest changes before publishing",
    }),
});

const { shouldPull } = config;
const MAX_RETRIES = 3;
const RETRY_DELAY = 10000; // 10 seconds

/**
 * Sleep for specified milliseconds
 * @param {number} ms
 */
function sleep(ms) {
  return new Promise((resolve) => globalThis.setTimeout(resolve, ms));
}

/**
 * Append to GitHub Actions output file
 * @param {string} key
 * @param {string} value
 */
function setOutput(key, value) {
  const outputFile = process.env.GITHUB_OUTPUT;
  if (outputFile) {
    appendFileSync(outputFile, `${key}=${value}\n`);
  }
}

/**
 * Extract version from pyproject.toml
 */
function getPyProjectVersion() {
  const content = readFileSync("./python/pyproject.toml", "utf8");
  const versionMatch = content.match(/^version\s*=\s*"([^"]+)"/m);
  if (!versionMatch) {
    throw new Error("Could not find version in pyproject.toml");
  }
  return versionMatch[1];
}

async function main() {
  try {
    if (shouldPull) {
      // Pull the latest changes we just pushed
      await $`git pull origin main`;
    }

    // Get current version from pyproject.toml
    const currentVersion = getPyProjectVersion();
    console.log(`Current version to publish: ${currentVersion}`);

    // Check if this version is already published on PyPI
    console.log(
      `Checking if version ${currentVersion} is already published...`,
    );
    const checkResult = await $`pip index versions lino-rest-api`.run({
      capture: true,
    });

    // Check if version already exists
    if (checkResult.stdout.includes(currentVersion)) {
      console.log(`Version ${currentVersion} is already published to PyPI`);
      setOutput("published", "true");
      setOutput("published_version", currentVersion);
      setOutput("already_published", "true");
      return;
    } else {
      console.log(
        `Version ${currentVersion} not found on PyPI, proceeding with publish...`,
      );
    }

    // Build the package
    console.log("Building package...");
    await $`cd python && python -m build`;

    // Publish to PyPI using trusted publishing with retry logic
    for (let i = 1; i <= MAX_RETRIES; i++) {
      console.log(`Publish attempt ${i} of ${MAX_RETRIES}...`);
      try {
        // Use twine with --skip-existing to handle race conditions
        await $`cd python && python -m twine upload --skip-existing dist/*`;
        setOutput("published", "true");
        setOutput("published_version", currentVersion);
        console.log(`✅ Published lino-rest-api@${currentVersion} to PyPI`);
        return;
      } catch (_error) {
        if (i < MAX_RETRIES) {
          console.log(
            `Publish failed, waiting ${RETRY_DELAY / 1000}s before retry...`,
          );
          await sleep(RETRY_DELAY);
        }
      }
    }

    console.error(`❌ Failed to publish after ${MAX_RETRIES} attempts`);
    process.exit(1);
  } catch (error) {
    console.error("Error:", error.message);
    if (process.env.DEBUG) {
      console.error(error.stack);
    }
    process.exit(1);
  }
}

main();
