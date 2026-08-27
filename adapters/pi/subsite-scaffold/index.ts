// subsite-scaffold — pi extension
//
// Scaffolds a new sub-site under the dyuhaus.com repo following the existing
// pattern (folder + .htaccess routing + README domain row + optional tunnel
// ingress), and emits a portable "artifact" bundle you can carry off this
// headless box to generate the real UI elsewhere.
//
// Exposes:
//   /new-subsite            interactive command (TUI)
//   create_subsite tool     LLM-callable, param-driven
//
// Repo resolution: explicit arg -> $DYUHAUS_SITE_REPO -> walk up from cwd ->
// /home/dyadmin/githubStaging/dyuhaus.com

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { StringEnum } from "@earendil-works/pi-ai";

import { buildManifest, type BrandKey, type SiteMode } from "./templates";
import {
  ARTIFACT_ROOT,
  type RawInput,
  apply,
  buildConfig,
  defaultTitle,
  isSiteRepo,
  normalizeSlug,
  pageListSummary,
  plan,
  resolveRepo,
  summarize,
  validSlug,
  RESERVED,
  zipArtifact,
} from "./core";

export type CreateSubsiteInput = RawInput & {
  repoPath?: string;
  emitArtifact?: boolean;
  zipArtifact?: boolean;
  dryRun?: boolean;
};

export default function (pi: ExtensionAPI) {
  /* ---- LLM tool -------------------------------------------------------- */
  pi.registerTool({
    name: "create_subsite",
    label: "Create dyuhaus sub-site",
    description:
      "Scaffold a new sub-site under the dyuhaus.com repo (folder + .htaccess/tunnel routing + README row) " +
      "and emit a portable artifact (manifest, brief, tokens, prompt) for generating the UI elsewhere. " +
      "Idempotent: existing files are skipped and wiring is added only once.",
    promptSnippet: "Scaffold a new dyuhaus.com sub-site and emit its portable UI artifact",
    promptGuidelines: [
      "Use create_subsite when the user asks to add a new sub-site/subdomain under dyuhaus.com.",
      "For create_subsite, prefer mode 'static' unless the sub-site is backed by a running service on a port.",
    ],
    parameters: Type.Object({
      slug: Type.String({ description: "Subdomain label / folder name, e.g. 'labs' for labs.dyuhaus.com" }),
      title: Type.Optional(Type.String({ description: "Human title for the site" })),
      description: Type.Optional(Type.String({ description: "One-line purpose / meta description" })),
      brand: Type.Optional(StringEnum(["ihtc", "personal", "none"] as const)),
      mode: Type.Optional(
        StringEnum(["tunnel", "static", "service"] as const, {
          description:
            "tunnel (default): static files via ops/static-server.cjs fronted by the Cloudflare tunnel; " +
            "static: Hostinger + .htaccess only; service: tunnel -> your own backend on --port",
        }),
      ),
      port: Type.Optional(
        Type.Number({ description: "Local origin port. Required for service; auto-assigned for tunnel if omitted." }),
      ),
      routeAsPath: Type.Optional(Type.Boolean({ description: "Also serve at dyuhaus.com/<slug>/" })),
      immutableAssets: Type.Optional(Type.Boolean({ description: "True only for hashed/Vite assets" })),
      pages: Type.Optional(Type.Array(Type.String(), { description: "Extra page slugs, e.g. ['pricing','about']" })),
      tagline: Type.Optional(Type.String()),
      repoPath: Type.Optional(Type.String({ description: "Override path to the dyuhaus.com repo" })),
      emitArtifact: Type.Optional(Type.Boolean({ description: "Emit the portable artifact bundle (default true)" })),
      zipArtifact: Type.Optional(Type.Boolean({ description: "Also zip the artifact into ~/transfer (default false)" })),
      dryRun: Type.Optional(Type.Boolean({ description: "Only report the plan; write nothing" })),
    }),
    async execute(_id, params: CreateSubsiteInput, _signal, _onUpdate, ctx) {
      const repo = resolveRepo(ctx.cwd, params.repoPath);
      if (!isSiteRepo(repo)) {
        return {
          content: [{ type: "text", text: `Could not find the dyuhaus.com repo (looked at ${repo}). Pass repoPath.` }],
          isError: true,
          details: {},
        };
      }
      const { cfg, error } = buildConfig(params);
      if (!cfg) {
        return { content: [{ type: "text", text: error! }], isError: true, details: {} };
      }
      const emitArtifact = params.emitArtifact !== false;
      const planned = await plan(repo, cfg, emitArtifact);
      const summary = summarize(cfg, planned, repo);

      if (params.dryRun) {
        return {
          content: [{ type: "text", text: `DRY RUN — nothing written.\n\n${summary}` }],
          details: { plan: planned.map((p) => ({ path: p.path, kind: p.kind })), manifest: buildManifest(cfg) },
        };
      }

      const done = await apply(repo, planned);
      let zipPath: string | null = null;
      if (params.zipArtifact && emitArtifact) zipPath = await zipArtifact(repo, cfg);

      const tail = [
        "",
        "Next steps:",
        `  1. Review the scaffold in ${cfg.slug}/ and the artifact in ${ARTIFACT_ROOT}/${cfg.slug}/`,
        `  2. Generate the real UI off-box from ${ARTIFACT_ROOT}/${cfg.slug}/PROMPT.md`,
        `  3. ${
          cfg.mode === "tunnel"
            ? `Route DNS (cloudflared tunnel route dns <id> ${cfg.subdomain}) and add the dy-${cfg.slug}-static NSSM origin on :${cfg.port}`
            : cfg.mode === "service"
              ? `Route DNS for ${cfg.subdomain} and run your service on :${cfg.port}`
              : `Add DNS for ${cfg.subdomain} and point Hostinger at the same doc root`
        }`,
        `  4. Commit + push main (Hostinger auto-pulls)`,
      ];
      if (zipPath) tail.push(`  Artifact archive: ${zipPath}`);

      return {
        content: [{ type: "text", text: `${summary}\n\nApplied ${done.length} change(s).${tail.join("\n")}` }],
        details: { applied: done, manifest: buildManifest(cfg), zip: zipPath },
      };
    },
  });

  /* ---- interactive command -------------------------------------------- */
  pi.registerCommand("new-subsite", {
    description: "Scaffold a new dyuhaus.com sub-site + portable UI artifact",
    handler: async (args, ctx) => {
      if (!ctx.hasUI) {
        ctx.ui.notify("/new-subsite needs an interactive UI. Use the create_subsite tool instead.", "warn");
        return;
      }
      const repo = resolveRepo(ctx.cwd);
      if (!isSiteRepo(repo)) {
        ctx.ui.notify(`Could not find the dyuhaus.com repo at ${repo}. Set $DYUHAUS_SITE_REPO.`, "error");
        return;
      }

      const slugInput = (args && args.trim()) || (await ctx.ui.input("Subdomain / folder name (e.g. labs):", ""));
      if (!slugInput) return;
      const slug = normalizeSlug(slugInput);
      if (!validSlug(slug) || RESERVED.has(slug)) {
        ctx.ui.notify(`Invalid or reserved slug "${slug}".`, "error");
        return;
      }

      const title = (await ctx.ui.input("Site title:", defaultTitle(slug, "ihtc"))) || defaultTitle(slug, "ihtc");
      const description = (await ctx.ui.input("One-line description:", `${title} — a dyuhaus.com sub-site.`)) || "";
      const brand = (await ctx.ui.select("Brand:", ["ihtc", "personal", "none"])) as BrandKey | undefined;
      const mode = (await ctx.ui.select("Hosting mode:", ["tunnel", "static", "service"])) as SiteMode | undefined;
      let port: number | undefined;
      if (mode === "service" || mode === "tunnel") {
        const hint = mode === "tunnel" ? "Local origin port (blank = auto-assign):" : "Local origin port (e.g. 8790):";
        const portStr = await ctx.ui.input(hint, "");
        port = portStr ? Number(portStr) : undefined;
        if (portStr && (Number.isNaN(port) || !port)) {
          ctx.ui.notify("Invalid port.", "error");
          return;
        }
        if (mode === "service" && !port) {
          ctx.ui.notify("Service mode needs a valid port.", "error");
          return;
        }
      }
      const routeAsPath = await ctx.ui.confirm("Also serve at dyuhaus.com/<slug>/ ?", `Add path route for /${slug}/`);
      const pagesStr = await ctx.ui.input("Extra pages (comma-separated, optional):", "");
      const pages = pagesStr ? pagesStr.split(",").map((s) => s.trim()).filter(Boolean) : [];
      const zipIt = await ctx.ui.confirm("Zip artifact to ~/transfer?", "Create a portable archive for handoff");

      const { cfg, error } = buildConfig({ slug, title, description, brand, mode, port, routeAsPath, pages });
      if (!cfg) {
        ctx.ui.notify(error!, "error");
        return;
      }

      const planned = await plan(repo, cfg, true);
      const proceed = await ctx.ui.confirm("Apply this plan?", summarize(cfg, planned, repo));
      if (!proceed) {
        ctx.ui.notify("Cancelled — nothing written.", "info");
        return;
      }

      const done = await apply(repo, planned);
      let zipPath: string | null = null;
      if (zipIt) zipPath = await zipArtifact(repo, cfg);

      ctx.ui.notify(
        `Sub-site '${cfg.slug}' scaffolded (${done.length} change(s)). Artifact: ${ARTIFACT_ROOT}/${cfg.slug}/` +
          (zipPath ? ` · zip: ${zipPath}` : ""),
        "info",
      );
      pi.sendMessage(
        {
          customType: "subsite-scaffold",
          display: true,
          content:
            `Scaffolded sub-site **${cfg.title}** (\`${cfg.subdomain}\`) in ${repo}.\n\n` +
            "```\n" +
            done.join("\n") +
            "\n```\n\n" +
            `Pages: ${pageListSummary(cfg)}\n` +
            `Portable artifact: \`${ARTIFACT_ROOT}/${cfg.slug}/\` (BRIEF.md, PROMPT.md, tokens.css, site.manifest.json).` +
            (zipPath ? `\nArchive: \`${zipPath}\`` : ""),
        },
        { deliverAs: "nextTurn" },
      );
    },
  });
}
