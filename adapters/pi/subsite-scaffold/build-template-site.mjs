// build-template-site.mjs
//
// Compatibility command for the hand-authored template library. The original
// implementation generated starter/ from Pi-owned strings; that is no longer
// safe because starter/ is the library hub and starter/ihtc/ is curated.
//
// This command is deliberately read-only. Validation stays in the site repo so
// the library has one contract instead of a second parser that can drift.
//
//   node build-template-site.mjs [repoPath]
import { existsSync, statSync } from "node:fs";
import * as path from "node:path";
import { spawnSync } from "node:child_process";

const defaultRepo = "/home/dyadmin/githubStaging/dyuhaus.com";

function isSiteRepo(candidate) {
  return (
    existsSync(path.join(candidate, ".htaccess")) &&
    existsSync(path.join(candidate, "README.md")) &&
    existsSync(path.join(candidate, "index.html"))
  );
}

function resolveRepo() {
  const candidates = [];
  if (process.argv[2]) candidates.push(path.resolve(process.argv[2]));
  if (process.env.DYUHAUS_SITE_REPO) candidates.push(path.resolve(process.env.DYUHAUS_SITE_REPO));
  let current = process.cwd();
  for (let depth = 0; depth < 8; depth += 1) {
    candidates.push(current);
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  candidates.push(defaultRepo);
  return candidates.find(isSiteRepo) || defaultRepo;
}

const repo = resolveRepo();
const validator = path.join(repo, "ops", "validate-starter-templates.mjs");
if (!existsSync(validator) || !statSync(validator).isFile()) {
  console.error("Template-library validator not found. Land the dyuhaus.com genre-template library before running this compatibility command.");
  process.exit(1);
}

const result = spawnSync(process.execPath, [validator], { cwd: repo, stdio: "inherit" });
if (result.error) {
  console.error(`Could not run the template-library validator: ${result.error.message}`);
  process.exit(1);
}
if (result.status !== 0) process.exit(result.status ?? 1);

console.log("IHTC compatibility check passed; no files were changed.");
console.log("Template: https://starter.dyuhaus.com/ihtc/");
