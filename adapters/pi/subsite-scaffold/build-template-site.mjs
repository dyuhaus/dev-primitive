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
import { existsSync, promises as fs } from "node:fs";
import * as path from "node:path";

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

function stripHtmlComments(html) {
  return html.replace(/<!--[\s\S]*?-->/g, "");
}

function startTags(html) {
  return [...stripHtmlComments(html).matchAll(/<\s*([a-z][\w-]*)\b[^>]*>/gi)].map((match) => ({
    name: match[1].toLowerCase(),
    text: match[0],
  }));
}

function attribute(tag, name) {
  return tag.match(new RegExp(`(?:^|\\s)${name}\\s*=\\s*["']([^"']*)["']`, "i"))?.[1] || "";
}

function hasClass(tag, className) {
  return attribute(tag, "class").split(/\s+/).includes(className);
}

function hasElement(tags, tagName, { className, id } = {}) {
  return tags.some((tag) => (
    tag.name === tagName &&
    (!className || hasClass(tag.text, className)) &&
    (!id || attribute(tag.text, "id") === id)
  ));
}

function hasMobileBacklinkRule(css) {
  const uncommentedCss = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const mediaPattern = /@media\s*\(\s*max-width\s*:\s*(\d+)px\s*\)\s*\{/gi;
  for (const match of uncommentedCss.matchAll(mediaPattern)) {
    if (Number(match[1]) > 520) continue;
    const openBrace = match.index + match[0].lastIndexOf("{");
    let depth = 1;
    let cursor = openBrace + 1;
    while (cursor < uncommentedCss.length && depth > 0) {
      if (uncommentedCss[cursor] === "{") depth += 1;
      if (uncommentedCss[cursor] === "}") depth -= 1;
      cursor += 1;
    }
    if (depth !== 0) continue;
    const mediaBody = uncommentedCss.slice(openBrace + 1, cursor - 1);
    if (/\.mobile-safe-backlink(?![\w-])[^{}]*\{[^{}]*\bposition\s*:\s*static\b/i.test(mediaBody)) return true;
  }
  return false;
}

try {
  const hub = await readRequired("starter/index.html");
  const hubMarkup = stripHtmlComments(hub);
  requireMatch(hubMarkup, /<title>Template Library · dyuhaus\.com<\/title>/, "starter/index.html is not the template-library hub");
  requireMatch(hubMarkup, /href=["']ihtc\/["']/, "the template-library hub does not link to starter/ihtc/");

  const ihtcIndex = await readRequired("starter/ihtc/index.html");
  const ihtcStyles = await readRequired("starter/ihtc/styles.css");
  const ihtcScript = await readRequired("starter/ihtc/script.js");
  await readRequired("starter/ihtc/favicon.svg");
  await readRequired("starter/ihtc/robots.txt");

  const tags = startTags(ihtcIndex);
  const uncommentedCss = ihtcStyles.replace(/\/\*[\s\S]*?\*\//g, "");
  const uncommentedScript = ihtcScript.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|\s)\/\/.*$/gm, "$1");
  try {
    Function(uncommentedScript);
  } catch {
    throw new Error("starter/ihtc/script.js has invalid JavaScript syntax");
  }
  const backlink = tags.find((tag) => (
    tag.name === "a" &&
    hasClass(tag.text, "template-backlink") &&
    hasClass(tag.text, "mobile-safe-backlink") &&
    /^\.\.\/(?:index\.html)?$/.test(attribute(tag.text, "href"))
  ));
  const stylesheet = tags.find((tag) => (
    tag.name === "link" &&
    attribute(tag.text, "rel").split(/\s+/).includes("stylesheet") &&
    /^styles\.css(?:\?[^#]*)?$/.test(attribute(tag.text, "href"))
  ));
  const executableScript = tags.find((tag) => {
    if (tag.name !== "script" || !/^script\.js(?:\?[^#]*)?$/.test(attribute(tag.text, "src"))) return false;
    const type = attribute(tag.text, "type").toLowerCase();
    return !type || ["text/javascript", "application/javascript", "module"].includes(type);
  });

  const terminalContract = [
    [hasElement(tags, "div", { className: "term-window" }), "terminal window chrome"],
    [hasElement(tags, "p", { className: "sec-head" }), "shell-prompt section headers"],
    [hasElement(tags, "span", { className: "ghost-num" }), "ghost section numbers"],
    [hasElement(tags, "code", { id: "boot" }), "the boot-log output"],
    [hasElement(tags, "button", { id: "replay" }), "the replayable boot-log control"],
    [hasElement(tags, "span", { id: "sb-clock" }), "the live status-bar clock"],
    [Boolean(backlink), "the template-library backlink"],
    [Boolean(stylesheet), "the active local stylesheet link"],
    [Boolean(executableScript), "the executable local script link"],
    [/@media\s*\(prefers-reduced-motion:\s*reduce\)/.test(uncommentedCss), "reduced-motion styles"],
    [hasMobileBacklinkRule(ihtcStyles), "the mobile-safe backlink rule"],
    [/getElementById\(["']sb-clock["']\)[\s\S]*?setInterval\(\s*tick\s*,/.test(uncommentedScript), "the live-clock behavior"],
    [/getElementById\(["']replay["']\)[\s\S]*?addEventListener\(\s*["']click["']\s*,\s*runBoot/.test(uncommentedScript), "the boot-log replay behavior"],
  ];

  for (const [present, feature] of terminalContract) {
    if (!present) throw new Error(`starter/ihtc/ is missing ${feature}; restore the curated IHTC template instead of regenerating it`);
  }
} catch (error) {
  console.error(`IHTC template verification failed: ${error.message}`);
  process.exit(1);
}

console.log("IHTC template verification passed; no files were changed.");
console.log("Template: https://starter.dyuhaus.com/ihtc/");
