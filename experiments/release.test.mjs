import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import {
  cpSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { resolve } from "node:path";
import test from "node:test";
import { parse } from "yaml";
import {
  getPackageVersion,
  tomlVersion,
  validateVersion,
} from "../scripts/package-version.mjs";
import { bumpVersion, versionPackages } from "../scripts/version-packages.mjs";
import { isPublished } from "../scripts/check-registry.mjs";
import { publishPackage } from "../scripts/publish-package.mjs";
import { extractReleaseNotes } from "../scripts/create-github-release-python.mjs";

function fixture(t) {
  const base = mkdtempSync(resolve("experiments/.release-test-"));
  const root = resolve(base, "repo");
  mkdirSync(root);
  t.after(() => rmSync(base, { recursive: true, force: true }));
  for (const file of [
    "js/package.json",
    "js/package-lock.json",
    "rust/Cargo.toml",
    "rust/Cargo.lock",
    "python/pyproject.toml",
    "js/CHANGELOG.md",
    "rust/CHANGELOG.md",
    "python/CHANGELOG.md",
  ]) {
    mkdirSync(resolve(root, file, ".."), { recursive: true });
    cpSync(file, resolve(root, file));
  }
  mkdirSync(resolve(root, ".changeset"));
  cpSync(".changeset/README.md", resolve(root, ".changeset/README.md"));
  cpSync("scripts", resolve(root, "scripts"), { recursive: true });
  return {
    root,
    base,
    read: (file) => readFileSync(resolve(root, file), "utf8"),
  };
}

function changeset(
  root,
  bump = "patch",
  description = "Release regression fix",
  name = "change",
) {
  writeFileSync(
    resolve(root, `.changeset/${name}.md`),
    `---\n"lino-rest-api": ${bump}\n---\n\n${description}\n`,
  );
}

test("workflow version extraction emits one semantic version", () => {
  const workflow = readFileSync(".github/workflows/release.yml", "utf8");
  const commands = [
    ...workflow.matchAll(/(?:NEW|CURRENT)_VERSION=\$\((.+)\)/g),
  ];
  assert.ok(commands.length > 0, "exercise the actual workflow command");
  for (const [, command] of commands) {
    const version = execFileSync("bash", ["-c", command], {
      encoding: "utf8",
    }).trim();
    assert.match(
      version,
      /^\d+\.\d+\.\d+$/,
      "GitHub outputs need a single-line version",
    );
  }
});

test("Python packaging has a local copy of the repository license", () => {
  assert.equal(
    readFileSync("python/LICENSE", "utf8"),
    readFileSync("LICENSE", "utf8"),
  );
});

test("version reader ignores Ruff, mypy and dependency versions and rejects multiline values", () => {
  assert.equal(
    tomlVersion(readFileSync("python/pyproject.toml", "utf8"), "project"),
    getPackageVersion(),
  );
  assert.equal(
    tomlVersion(
      '[package]\nversion = "1.2.3"\n[dependencies.x]\nversion = "9.9.9"\n',
      "package",
    ),
    "1.2.3",
  );
  for (const version of [
    "0.2.0\npy313\n3.13",
    "1.2",
    "01.2.3",
    "bad",
    undefined,
  ])
    assert.throws(() => validateVersion(version));
  assert.throws(() =>
    tomlVersion('[project]\nversion = "1.2.3"\nversion = "2.0.0"\n', "project"),
  );
});

test("changesets bump all manifests, locks and changelogs once without changing tool settings", (t) => {
  const { root, read } = fixture(t);
  const current = getPackageVersion(root);
  changeset(
    root,
    "patch",
    "Do not let the description word major choose a bump",
    "first",
  );
  changeset(root, "minor", "Support all registries", "second");
  const expected = bumpVersion(current, "minor");
  assert.equal(versionPackages({ root }), expected);
  assert.equal(getPackageVersion(root), expected);
  const lock = JSON.parse(read("js/package-lock.json"));
  assert.equal(lock.version, expected);
  assert.equal(lock.packages[""].version, expected);
  assert.match(
    read("rust/Cargo.lock"),
    new RegExp(`name = "lino-rest-api"\\nversion = "${expected}"`),
  );
  assert.match(read("python/pyproject.toml"), /target-version = "py313"/);
  assert.match(read("python/pyproject.toml"), /python_version = "3.13"/);
  for (const language of ["js", "rust", "python"])
    assert.ok(read(`${language}/CHANGELOG.md`).includes(`## [${expected}]`));
  assert.deepEqual(readdirSync(resolve(root, ".changeset")), ["README.md"]);
  assert.equal(
    versionPackages({ root }),
    expected,
    "rerun must keep the committed version",
  );
  assert.equal(read("js/CHANGELOG.md").split(`## [${expected}]`).length, 2);
});

for (const bump of ["patch", "minor", "major"]) {
  test(`instant ${bump} release uses the same version for all three packages`, (t) => {
    const { root, read } = fixture(t);
    const current = getPackageVersion(root);
    const description =
      "Keep literal $(), `quotes` and newlines\nwith --- separators";
    const expected = bumpVersion(current, bump);
    assert.equal(versionPackages({ root, bump, description }), expected);
    assert.equal(getPackageVersion(root), expected);
    assert.ok(read("python/CHANGELOG.md").includes(description));
  });
}

test("malformed changesets and mismatched versions fail before modifying files", (t) => {
  const { root, read } = fixture(t);
  const original = read("js/package.json");
  writeFileSync(
    resolve(root, ".changeset/bad.md"),
    '---\n"test-anywhere": patch\n---\n\nWrong package\n',
  );
  assert.throws(() => versionPackages({ root }), /Invalid changeset/);
  assert.equal(read("js/package.json"), original);
  assert.ok(read(".changeset/bad.md"));
  writeFileSync(
    resolve(root, "js/package.json"),
    original.replace(getPackageVersion(root), "99.0.0"),
  );
  assert.throws(() => versionPackages({ root }), /versions must agree/);
});

test("manual changesets target this package and pass the existing validator", (t) => {
  const { root } = fixture(t);
  execFileSync(
    process.execPath,
    [
      "scripts/create-manual-changeset.mjs",
      "--bump-type",
      "minor",
      "--description",
      "Manual release",
    ],
    { cwd: root },
  );
  execFileSync(process.execPath, ["scripts/validate-changeset.mjs"], {
    cwd: root,
  });
  assert.equal(
    versionPackages({ root }),
    bumpVersion(getPackageVersion(), "minor"),
  );
});

const payloads = {
  npm: (version) => ({ version }),
  "crates-io": (version) => ({ version: { num: version } }),
  pypi: (version) => ({ info: { version } }),
};
for (const registry of Object.keys(payloads)) {
  test(`${registry} uses an exact uncached version lookup and only treats 404 as missing`, async () => {
    const requests = [];
    const fetcher = async (url, options) => {
      requests.push({ url: url.toString(), options });
      return {
        status: 200,
        ok: true,
        json: async () => payloads[registry]("0.2.0"),
      };
    };
    assert.equal(await isPublished(registry, "0.2.0", fetcher), true);
    assert.equal(await isPublished(registry, "0.2.0", fetcher), true);
    assert.notEqual(requests[0].url, requests[1].url);
    assert.ok(requests[0].url.includes("/lino-rest-api/0.2.0"));
    assert.equal(requests[0].options.cache, "no-store");
    assert.equal(requests[0].options.headers["cache-control"], "no-cache");
    assert.equal(
      await isPublished(registry, "0.2.0", async () => ({ status: 404 })),
      false,
    );
    for (const status of [401, 403, 429, 500])
      await assert.rejects(
        isPublished(registry, "0.2.0", async () => ({ status, ok: false })),
        /lookup failed/,
      );
    await assert.rejects(
      isPublished(registry, "0.2.0", async () => ({
        status: 200,
        ok: true,
        json: async () => payloads[registry]("0.2.01"),
      })),
      /unexpected version/,
    );
    await assert.rejects(
      isPublished(registry, "0.2.0", async () => {
        throw new Error("Network unavailable");
      }),
      /Network unavailable/,
    );
  });
}

const workflow = parse(readFileSync(".github/workflows/release.yml", "utf8"));
test("all publishing jobs use the prepared commit and require successful validation", () => {
  const release = workflow.jobs.release;
  assert.ok(release.if.includes("github.ref == 'refs/heads/main'"));
  assert.deepEqual(release.needs, [
    "lint",
    "test-js",
    "test-python",
    "test-rust",
  ]);
  for (const job of release.needs)
    assert.ok(release.if.includes(`needs.${job}.result == 'success'`));
  for (const jobName of ["publish-npm", "publish-crates", "publish-pypi"]) {
    const job = workflow.jobs[jobName];
    assert.deepEqual(job.needs, ["release"]);
    assert.equal(job.if, "always() && needs.release.result == 'success'");
    assert.equal(job.permissions["id-token"], "write");
    assert.equal(job.steps[0].with.ref, "${{ needs.release.outputs.sha }}");
    const check = job.steps.find((step) => step.id === "registry");
    assert.ok(check.run.includes("scripts/check-registry.mjs"));
    const publish = job.steps.find(
      (step) =>
        step.run?.includes("npm publish") ||
        step.run?.includes("cargo publish") ||
        step.uses?.startsWith("pypa/gh-action-pypi-publish"),
    );
    assert.equal(publish.if, "steps.registry.outputs.published == 'false'");
  }
  assert.ok(
    workflow.jobs["publish-npm"].steps.some(
      (step) => step.run === "npm install --global npm@11",
    ),
  );
  assert.equal(
    workflow.jobs["publish-crates"].steps.find((step) =>
      step.run?.includes("cargo publish"),
    ).env.CARGO_REGISTRY_TOKEN,
    "${{ steps.auth.outputs.token }}",
  );
});

for (const mode of ["changeset", "instant", "no-changesets"]) {
  test(`${mode} workflow rerun reuses the release commit without another bump`, (t) => {
    const { root, base } = fixture(t);
    const git = (...args) =>
      execFileSync("git", args, {
        cwd: root,
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
      }).trim();
    git("init", "--initial-branch=main");
    git("config", "user.name", "Release test");
    git("config", "user.email", "release-test@example.com");
    if (mode === "changeset") changeset(root);
    git("add", ".");
    git("commit", "-m", "Initial fixture");
    const remote = resolve(base, "remote.git");
    git("init", "--bare", remote);
    git("remote", "add", "origin", remote);
    git("push", "origin", "main");
    const run = workflow.jobs.release.steps.find(
      (step) => step.id === "version",
    ).run;
    const env = {
      ...process.env,
      RELEASE_MODE: mode === "instant" ? "instant" : "changeset",
      BUMP_TYPE: mode === "instant" ? "patch" : "",
      DESCRIPTION: "Release test",
      GITHUB_RUN_ID: "123",
      GITHUB_OUTPUT: resolve(base, "output"),
      SOURCE_SHA: git("rev-parse", "HEAD"),
    };
    execFileSync("bash", ["-e", "-c", run], { cwd: root, env, stdio: "pipe" });
    const releaseSha = git("rev-parse", "HEAD");
    const version = getPackageVersion(root);
    execFileSync("bash", ["-e", "-c", run], { cwd: root, env, stdio: "pipe" });
    assert.equal(git("rev-parse", "HEAD"), releaseSha);
    assert.equal(getPackageVersion(root), version);
    assert.equal(
      git("rev-list", "--count", "HEAD"),
      mode === "no-changesets" ? "1" : "2",
    );
    assert.equal(
      version,
      mode === "no-changesets"
        ? getPackageVersion()
        : bumpVersion(getPackageVersion(), "patch"),
    );
    assert.equal(
      readFileSync(env.GITHUB_OUTPUT, "utf8"),
      `version=${version}\nsha=${releaseSha}\nversion=${version}\nsha=${releaseSha}\n`,
    );
  });
}

test("release preparation rejects untested main commits and ignores another run's trailer", (t) => {
  const { root, base } = fixture(t);
  const git = (...args) =>
    execFileSync("git", args, {
      cwd: root,
      encoding: "utf8",
      stdio: "pipe",
    }).trim();
  git("init", "--initial-branch=main");
  git("config", "user.name", "Release test");
  git("config", "user.email", "release-test@example.com");
  git("add", ".");
  git("commit", "-m", "Initial fixture");
  const source = git("rev-parse", "HEAD");
  git("commit", "--allow-empty", "-m", "Other run", "-m", "Release-Run: 1234");
  const run = workflow.jobs.release.steps.find(
    (step) => step.id === "version",
  ).run;
  assert.throws(
    () =>
      execFileSync("bash", ["-e", "-c", run], {
        cwd: root,
        env: {
          ...process.env,
          SOURCE_SHA: source,
          RELEASE_MODE: "changeset",
          GITHUB_RUN_ID: "123",
          GITHUB_OUTPUT: resolve(base, "output"),
        },
        stdio: "pipe",
      }),
    /main advanced after validation/,
  );
  assert.equal(getPackageVersion(root), getPackageVersion());
});

test("local npm publisher uploads this package from js with provenance and bounded retries", async (t) => {
  const { root } = fixture(t);
  const calls = [];
  const delays = [];
  await publishPackage("npm", {
    root,
    args: [],
    lookup: async () => false,
    run: (command, args, options) => {
      calls.push({ command, args, options });
      if (calls.length === 1) throw new Error("Transient upload failure");
    },
    pause: async (delay) => delays.push(delay),
  });
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0].args, [
    "publish",
    "--provenance",
    "--access",
    "public",
  ]);
  assert.equal(calls[0].command, "npm");
  assert.equal(calls[0].options.cwd, resolve(root, "js"));
  assert.deepEqual(delays, [10_000]);
  let attempts = 0;
  await assert.rejects(
    publishPackage("npm", {
      root,
      args: [],
      lookup: async () => false,
      pause: async () => {},
      run: () => {
        attempts++;
        throw new Error("Permanent upload failure");
      },
    }),
    /Permanent upload failure/,
  );
  assert.equal(attempts, 3);
});

test("already published versions skip every upload and network errors propagate", async (t) => {
  const { root } = fixture(t);
  const unexpected = () => {
    throw new Error("Must not upload");
  };
  for (const registry of ["npm", "pypi"]) {
    const result = await publishPackage(registry, {
      root,
      args: [],
      lookup: async () => true,
      run: unexpected,
    });
    assert.equal(result.alreadyPublished, true);
    await assert.rejects(
      publishPackage(registry, {
        root,
        args: [],
        lookup: async () => {
          throw new Error("Registry unavailable");
        },
        run: unexpected,
      }),
      /Registry unavailable/,
    );
  }
});

test("PyPI helper builds fresh artifacts and never uploads an older distribution", async (t) => {
  const { root } = fixture(t);
  mkdirSync(resolve(root, "python/dist"));
  writeFileSync(resolve(root, "python/dist/stale.whl"), "stale");
  const calls = [];
  await publishPackage("pypi", {
    root,
    args: [],
    lookup: async () => false,
    run: (command, args, options) => {
      assert.equal(command, "python");
      assert.equal(options.cwd, resolve(root, "python"));
      calls.push(args);
      if (args[1] === "build") {
        mkdirSync(resolve(root, "python/dist"));
        writeFileSync(resolve(root, "python/dist/current.whl"), "fresh");
      }
    },
  });
  assert.deepEqual(calls, [
    ["-m", "build"],
    ["-m", "twine", "check", "dist/current.whl"],
    [
      "-m",
      "twine",
      "upload",
      "--non-interactive",
      "--skip-existing",
      "dist/current.whl",
    ],
  ]);
});

test("GitHub release notes contain the selected changelog section as Markdown", () => {
  const notes = "- Fix version extraction\n\n### Added\n\n- Three registries";
  const changelog = `# Changelog\n\n## [Unreleased]\n\n## [0.2.1] - 2026-10-08\n\n${notes}\n\n## [0.2.0] - 2026-09-16\n\n- Old release\n`;
  assert.equal(extractReleaseNotes(changelog, "0.2.1"), notes);
  assert.throws(
    () => extractReleaseNotes(changelog, "9.9.9"),
    /Missing release notes/,
  );
});
