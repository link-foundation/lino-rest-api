#!/usr/bin/env node

import { writeFileSync } from "node:fs";
import { randomBytes } from "node:crypto";
import { parseArgs } from "node:util";
import { bumpVersion } from "./version-packages.mjs";

try {
  const { values } = parseArgs({
    options: {
      "bump-type": { type: "string", default: process.env.BUMP_TYPE },
      description: { type: "string", default: process.env.DESCRIPTION },
    },
  });
  const bump = values["bump-type"];
  bumpVersion("0.0.0", bump);
  const file = `.changeset/manual-release-${randomBytes(4).toString("hex")}.md`;
  writeFileSync(
    file,
    `---\n"lino-rest-api": ${bump}\n---\n\n${values.description || `Manual ${bump} release`}\n`,
  );
  console.log(`Created ${file}`);
} catch (error) {
  console.error(error.message);
  if (process.env.DEBUG) console.error(error.stack);
  process.exitCode = 1;
}
