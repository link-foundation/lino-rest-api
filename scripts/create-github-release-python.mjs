#!/usr/bin/env node

import { execFileSync, spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { validateVersion } from "./package-version.mjs";

export function extractReleaseNotes(changelog, version) {
  validateVersion(version);
  const pattern = new RegExp(
    `^## \\[${version.replaceAll(".", "\\.")}\\][^\\n]*\\n([\\s\\S]*?)(?=^## |$(?![\\s\\S]))`,
    "m",
  );
  const notes = changelog.match(pattern)?.[1].trim();
  if (!notes) throw new Error(`Missing release notes for ${version}`);
  return notes;
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(resolve(process.argv[1])).href
) {
  try {
    const { values } = parseArgs({
      options: {
        "release-version": {
          type: "string",
          default: process.env.RELEASE_VERSION,
        },
        repository: { type: "string", default: process.env.REPOSITORY },
        "commit-sha": { type: "string", default: process.env.RELEASE_SHA },
      },
    });
    const version = validateVersion(values["release-version"]);
    const repository = values.repository;
    const sha =
      values["commit-sha"] ||
      execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
    if (!repository || !/^[a-f0-9]{40}$/.test(sha))
      throw new Error("Repository and release commit SHA are required");
    const tag = `v${version}`;
    const existing = spawnSync(
      "gh",
      ["release", "view", tag, "--repo", repository],
      { stdio: "pipe" },
    );
    if (existing.error) throw existing.error;
    if (existing.status === 0) {
      console.log(`Release ${tag} already exists`);
    } else {
      const notes = extractReleaseNotes(
        readFileSync("python/CHANGELOG.md", "utf8"),
        version,
      );
      execFileSync(
        "gh",
        [
          "release",
          "create",
          tag,
          "--repo",
          repository,
          "--target",
          sha,
          "--title",
          tag,
          "--notes-file",
          "-",
        ],
        {
          input: notes,
          encoding: "utf8",
          stdio: ["pipe", "inherit", "inherit"],
        },
      );
    }
  } catch (error) {
    console.error(error.message);
    if (process.env.DEBUG) console.error(error.stack);
    process.exitCode = 1;
  }
}
