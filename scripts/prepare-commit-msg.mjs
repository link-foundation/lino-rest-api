#!/usr/bin/env node

/**
 * Prepare commit message hook - warns if committing source changes without a changeset
 *
 * Uses link-foundation libraries:
 * - use-m: Dynamic package loading without package.json dependencies
 * - command-stream: Modern shell command execution with streaming support
 */

import { readdirSync } from "fs";
import { createInterface } from "readline";

// Skip in CI environments
if (process.env.CI || process.env.GITHUB_ACTIONS) {
  process.exit(0);
}

// Get commit source from arguments
const commitSource = process.argv[3];

// Check if this is a merge commit, amend, or rebase
if (
  commitSource === "merge" ||
  commitSource === "squash" ||
  commitSource === "commit"
) {
  process.exit(0);
}

// Load use-m dynamically
const { use } = eval(
  await (await fetch("https://unpkg.com/use-m/use.js")).text(),
);

// Import command-stream for shell command execution
const { $ } = await use("command-stream");

try {
  // Check if there are any changesets (excluding README.md)
  const changesetDir = ".changeset";
  const changesetFiles = readdirSync(changesetDir).filter(
    (file) => file.endsWith(".md") && file !== "README.md",
  );
  const changesetCount = changesetFiles.length;

  // Check if we're modifying source files, package.json, or tests
  let modifiedSrc = [];
  try {
    const result = await $`git diff --cached --name-only`.run({
      capture: true,
    });
    modifiedSrc = result.stdout
      .split("\n")
      .filter((file) => file.match(/^(src\/|package\.json)/))
      .filter(Boolean);
  } catch (_error) {
    // No staged files
    modifiedSrc = [];
  }

  // If we're modifying source files and there's no changeset, warn the user
  if (modifiedSrc.length > 0 && changesetCount === 0) {
    console.log("");
    console.log("⚠️  WARNING: No changeset found!");
    console.log("");
    console.log("You are committing changes to source files or package.json");
    console.log("but no changeset has been created.");
    console.log("");
    console.log("Modified files:");
    modifiedSrc.forEach((file) => console.log(`  - ${file}`));
    console.log("");
    console.log("To create a changeset, run:");
    console.log("  npm run changeset");
    console.log("");
    console.log(
      "If this commit doesn't require a changeset (e.g., internal refactoring,",
    );
    console.log("test updates, or documentation), you can proceed.");
    console.log("");
    console.log(
      "To bypass this check permanently, use: git commit --no-verify",
    );
    console.log("");

    // Ask for confirmation (only in interactive mode)
    if (process.stdin.isTTY) {
      const rl = createInterface({
        input: process.stdin,
        output: process.stdout,
      });

      rl.question(
        "Do you want to continue without a changeset? [y/N] ",
        (answer) => {
          rl.close();

          const response = answer.trim().toLowerCase();
          if (response === "y" || response === "yes") {
            console.log("Proceeding without changeset...");
            process.exit(0);
          } else {
            console.log("");
            console.log(
              "Commit aborted. Please create a changeset first with: npm run changeset",
            );
            process.exit(1);
          }
        },
      );
    } else {
      // Non-interactive mode - fail by default
      console.log(
        "Non-interactive mode detected. Please create a changeset first.",
      );
      console.log("Or use --no-verify to skip this check.");
      process.exit(1);
    }
  }
} catch (error) {
  console.error("Error in prepare-commit-msg hook:", error.message);
  if (process.env.DEBUG) {
    console.error("Stack trace:", error.stack);
  }
  // Don't fail the commit on hook errors
  process.exit(0);
}
