// build-template-site.mjs
//
// Compatibility command for the hand-authored IHTC member of the dyuhaus.com
// template library. The old implementation generated starter/ from Pi-owned
// strings. That is no longer safe: starter/ is the library hub and
// starter/ihtc/ is a curated reference that must not be regenerated.
//
// This command is deliberately read-only. It verifies that the library and the
// preserved IHTC terminal behaviors are present, then exits without writing.
//
//   node build-template-site.mjs [repoPath]
import { promises as fs } from "node:fs";
import * as path from "node:path";

const repo = path.resolve(process.argv[2] || process.cwd());

async function readRequired(relativePath) {
  const file = path.join(repo, relativePath);
  let stat;
  try {
    stat = await fs.stat(file);
  } catch {
    throw new Error(`${relativePath} is missing`);
  }
  if (!stat.isFile()) throw new Error(`${relativePath} is not a file`);
  return fs.readFile(file, "utf8");
}

function requireMatch(content, pattern, message) {
  if (!pattern.test(content)) throw new Error(message);
}

try {
  const hub = await readRequired("starter/index.html");
  requireMatch(hub, /<title>Template Library · dyuhaus\.com<\/title>/, "starter/index.html is not the template-library hub");
  requireMatch(hub, /href=["']ihtc\/["']/, "the template-library hub does not link to starter/ihtc/");

  const ihtcIndex = await readRequired("starter/ihtc/index.html");
  const ihtcStyles = await readRequired("starter/ihtc/styles.css");
  const ihtcScript = await readRequired("starter/ihtc/script.js");
  await readRequired("starter/ihtc/favicon.svg");
  await readRequired("starter/ihtc/robots.txt");

  const terminalContract = [
    [ihtcIndex, /class=["'][^"']*term-window/, "terminal window chrome"],
    [ihtcIndex, /class=["'][^"']*sec-head/, "shell-prompt section headers"],
    [ihtcIndex, /class=["'][^"']*ghost-num/, "ghost section numbers"],
    [ihtcIndex, /id=["']replay["']/, "the replayable boot log"],
    [ihtcIndex, /id=["']sb-clock["']/, "the live status-bar clock"],
    [ihtcIndex, /class=["'][^"']*template-backlink[^"']*mobile-safe-backlink[^"']*["'][^>]*href=["']\.\.\/["']/, "the template-library backlink"],
    [ihtcStyles, /@media\s*\(prefers-reduced-motion:\s*reduce\)/, "reduced-motion styles"],
    [ihtcStyles, /@media\s*\(max-width:\s*520px\)[\s\S]*?\.mobile-safe-backlink[\s\S]*?position:\s*static/, "the mobile-safe backlink rule"],
    [ihtcScript, /getElementById\(["']sb-clock["']\)/, "the live-clock behavior"],
    [ihtcScript, /getElementById\(["']replay["']\)/, "the boot-log replay behavior"],
  ];

  for (const [content, pattern, feature] of terminalContract) {
    requireMatch(content, pattern, `starter/ihtc/ is missing ${feature}; restore the curated IHTC template instead of regenerating it`);
  }
} catch (error) {
  console.error(`IHTC template verification failed: ${error.message}`);
  process.exit(1);
}

console.log("IHTC template verification passed; no files were changed.");
console.log("Template: https://starter.dyuhaus.com/ihtc/");
