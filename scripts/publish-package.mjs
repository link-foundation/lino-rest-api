import { execFileSync } from "node:child_process";
import { appendFileSync, readdirSync, rmSync } from "node:fs";
import { resolve } from "node:path";
import { parseArgs } from "node:util";
import { setTimeout } from "node:timers/promises";
import { isPublished } from "./check-registry.mjs";
import { getPackageVersion } from "./package-version.mjs";

// Local entry points use the same checks and package directories as release.yml.
export async function publishPackage(
  registry,
  {
    root = ".",
    args = process.argv.slice(2),
    run = execFileSync,
    lookup = isPublished,
    pause = setTimeout,
  } = {},
) {
  const { values } = parseArgs({
    args,
    options: {
      "should-pull": {
        type: "boolean",
        default: process.env.SHOULD_PULL === "true",
      },
    },
  });
  if (values["should-pull"])
    run("git", ["pull", "--ff-only", "origin", "main"], {
      cwd: resolve(root),
      stdio: "inherit",
    });
  const version = getPackageVersion(root);
  const alreadyPublished = await lookup(registry, version);
  if (!alreadyPublished) {
    if (registry === "npm") {
      await uploadWithRetry(
        () =>
          run("npm", ["publish", "--provenance", "--access", "public"], {
            cwd: resolve(root, "js"),
            stdio: "inherit",
          }),
        registry,
        version,
        lookup,
        pause,
      );
    } else if (registry === "pypi") {
      // Never upload artifacts from an earlier build or release.
      rmSync(resolve(root, "python/dist"), { recursive: true, force: true });
      run("python", ["-m", "build"], {
        cwd: resolve(root, "python"),
        stdio: "inherit",
      });
      const artifacts = readdirSync(resolve(root, "python/dist")).map(
        (file) => `dist/${file}`,
      );
      run("python", ["-m", "twine", "check", ...artifacts], {
        cwd: resolve(root, "python"),
        stdio: "inherit",
      });
      await uploadWithRetry(
        () =>
          run(
            "python",
            [
              "-m",
              "twine",
              "upload",
              "--non-interactive",
              "--skip-existing",
              ...artifacts,
            ],
            { cwd: resolve(root, "python"), stdio: "inherit" },
          ),
        registry,
        version,
        lookup,
        pause,
      );
    } else {
      throw new Error(`Unsupported registry: ${registry}`);
    }
  }
  console.log(
    `${registry}: lino-rest-api@${version} ${alreadyPublished ? "already published" : "published"}`,
  );
  if (process.env.GITHUB_OUTPUT)
    appendFileSync(
      process.env.GITHUB_OUTPUT,
      `published=true\npublished_version=${version}\nalready_published=${alreadyPublished}\n`,
    );
  return { version, alreadyPublished };
}

async function uploadWithRetry(upload, registry, version, lookup, pause) {
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      upload();
      return;
    } catch (error) {
      // An upload may have reached the registry before the client lost its connection.
      if (await lookup(registry, version)) return;
      if (attempt === 3) throw error;
      console.error(
        `${registry} upload attempt ${attempt} failed: ${error.message}; retrying in 10 seconds`,
      );
      await pause(10_000);
    }
  }
}

export async function main(registry) {
  try {
    await publishPackage(registry);
  } catch (error) {
    console.error(error.message);
    if (process.env.DEBUG) console.error(error.stack);
    process.exitCode = 1;
  }
}
