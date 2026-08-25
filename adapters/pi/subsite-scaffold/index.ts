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

import {
  buildManifest,
  type BrandKey,
  type SubsiteConfig,
  type SiteMode,
  type SiteTheme,
  SITE_THEME_KEYS,
  siteThemeLabel,
} from "./templates";
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
  readPersistedSiteConfig,
  resolveRepo,
  summarize,
  validSlug,
  RESERVED,
  withConfirmedTheme,
  zipArtifact,
} from "./core";

export type CreateSubsiteInput = Omit<RawInput, "theme"> & {
  repoPath?: string;
  zipArtifact?: boolean;
  dryRun?: boolean;
};

export default async function (pi: ExtensionAPI) {
  /* ---- LLM tool -------------------------------------------------------- */
  pi.registerTool({
    name: "create_subsite",
    label: "Create dyuhaus sub-site",
    description:
      "Scaffold a new sub-site under the dyuhaus.com repo (folder + .htaccess/tunnel routing + README row) " +
      "after the user explicitly chooses a template theme, and emit a portable artifact (manifest, brief, tokens, prompt) for generating the UI elsewhere. " +
      "Idempotent: existing files are skipped and wiring is added only once.",
    promptSnippet: "Scaffold a new dyuhaus.com sub-site and emit its portable UI artifact",
    promptGuidelines: [
      "Use create_subsite when the user asks to add a new sub-site/subdomain under dyuhaus.com.",
      "For any new site, including one for an existing project, the tool opens a local interactive selector and waits for the user to choose one of the eight template themes before it plans or writes anything.",
      "Do not infer or default a new-site theme. Existing sites reuse their persisted creation settings without asking again.",
      "For create_subsite, prefer mode 'static' unless the sub-site is backed by a running service on a port.",
    ],
    executionMode: "sequential",
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
      zipArtifact: Type.Optional(Type.Boolean({ description: "Also zip the artifact into ~/transfer (default false)" })),
      dryRun: Type.Optional(Type.Boolean({ description: "Only report the plan; write nothing" })),
    }),
    async execute(_id, params: CreateSubsiteInput, signal, _onUpdate, ctx) {
      const repo = resolveRepo(ctx.cwd, params.repoPath);
      if (!isSiteRepo(repo)) {
        return {
          content: [{ type: "text", text: `Could not find the dyuhaus.com repo (looked at ${repo}). Pass repoPath.` }],
          isError: true,
          details: {},
        };
      }
      const persisted = await readPersistedSiteConfig(repo, params.slug);
      if (signal?.aborted) {
        return { content: [{ type: "text", text: "Operation aborted; nothing was planned or written." }], isError: true, details: {} };
      }
      let cfg: SubsiteConfig;
      if (persisted.error) {
        return { content: [{ type: "text", text: persisted.error }], isError: true, details: {} };
      }
      if (persisted.exists) {
        if (!persisted.cfg) {
          return {
            content: [{ type: "text", text: `Existing site "${normalizeSlug(params.slug)}" has no reusable persisted configuration.` }],
            isError: true,
            details: {},
          };
        }
        cfg = persisted.cfg;
      } else {
        if (!ctx.hasUI || ctx.mode !== "tui") {
          return {
            content: [
              {
                type: "text",
                text: "A new-site theme must be chosen by David in a local interactive Pi session. Nothing was planned or written.",
              },
            ],
            isError: true,
            details: {},
          };
        }
        const themeLabel = await ctx.ui.select(
          "Which theme should this new site use? Preview: https://starter.dyuhaus.com/",
          SITE_THEME_KEYS.map(siteThemeLabel),
          { signal },
        );
        if (signal?.aborted) {
          return { content: [{ type: "text", text: "Operation aborted; nothing was planned or written." }], isError: true, details: {} };
        }
        const theme = SITE_THEME_KEYS.find((key) => siteThemeLabel(key) === themeLabel) as SiteTheme | undefined;
        if (!theme) {
          return {
            content: [{ type: "text", text: "Theme selection was cancelled; nothing was planned or written." }],
            isError: true,
            details: {},
          };
        }
        if (persisted.pendingCfg) {
          if (theme !== persisted.pendingCfg.theme) {
            return {
              content: [{ type: "text", text: `The interrupted scaffold recorded ${siteThemeLabel(persisted.pendingCfg.theme)}. Confirm that theme to resume, or use the existing-site workflow to replace the pending scaffold.` }],
              isError: true,
              details: {},
            };
          }
          cfg = persisted.pendingCfg;
        } else {
          const built = buildConfig(withConfirmedTheme(params, theme));
          if (!built.cfg) {
            return { content: [{ type: "text", text: built.error! }], isError: true, details: {} };
          }
          cfg = built.cfg;
        }
      }
      let planned;
      try {
        planned = await plan(repo, cfg, true);
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : String(cause);
        return { content: [{ type: "text", text: message }], isError: true, details: {} };
      }
      if (signal?.aborted) {
        return { content: [{ type: "text", text: "Operation aborted; nothing was written." }], isError: true, details: {} };
      }
      const summary = summarize(cfg, planned, repo);

      if (params.dryRun) {
        return {
          content: [{ type: "text", text: `DRY RUN — nothing written.\n\n${summary}` }],
          details: { plan: planned.map((p) => ({ path: p.path, kind: p.kind })), manifest: buildManifest(cfg) },
        };
      }

      let done;
      try {
        done = await apply(repo, planned, signal);
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : String(cause);
        return { content: [{ type: "text", text: message }], isError: true, details: {} };
      }
      let zipPath: string | null = null;
      if (params.zipArtifact) zipPath = await zipArtifact(repo, cfg);

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
        content: [
          {
            type: "text",
            text: `${persisted.exists ? "Existing site detected; reused its persisted creation settings.\n\n" : persisted.pendingCfg ? "Interrupted scaffold detected; David reconfirmed its recorded theme.\n\n" : ""}${summary}\n\nApplied ${done.length} change(s).${tail.join("\n")}`,
          },
        ],
        details: { applied: done, manifest: buildManifest(cfg), zip: zipPath },
      };
    },
  });

  /* ---- interactive command -------------------------------------------- */
  pi.registerCommand("new-subsite", {
    description: "Scaffold a new dyuhaus.com sub-site + portable UI artifact",
    handler: async (args, ctx) => {
      if (!ctx.hasUI) {
        ctx.ui.notify("/new-subsite needs an interactive UI so David can choose the site theme.", "warn");
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

      const persisted = await readPersistedSiteConfig(repo, slug);
      let cfg: SubsiteConfig;
      let zipIt = false;
      if (persisted.error) {
        ctx.ui.notify(persisted.error, "error");
        return;
      }
      if (persisted.exists) {
        if (!persisted.cfg) {
          ctx.ui.notify(`Existing site "${slug}" has no reusable persisted configuration.`, "error");
          return;
        }
        cfg = persisted.cfg;
      } else {
        if (ctx.mode !== "tui") {
          ctx.ui.notify("A new-site theme must be chosen by David in a local interactive Pi session.", "error");
          return;
        }
        const themeLabel = await ctx.ui.select(
          "Which theme should this new site use? Preview: https://starter.dyuhaus.com/",
          SITE_THEME_KEYS.map(siteThemeLabel),
          { signal: ctx.signal },
        );
        if (ctx.signal?.aborted) return;
        const theme = SITE_THEME_KEYS.find((key) => siteThemeLabel(key) === themeLabel) as SiteTheme | undefined;
        if (!theme) return;

        if (persisted.pendingCfg) {
          if (theme !== persisted.pendingCfg.theme) {
            ctx.ui.notify(
              `The interrupted scaffold recorded ${siteThemeLabel(persisted.pendingCfg.theme)}. Confirm that theme to resume, or use the existing-site workflow to replace the pending scaffold.`,
              "error",
            );
            return;
          }
          cfg = persisted.pendingCfg;
        } else {

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
          const built = buildConfig(withConfirmedTheme({
            slug,
            title,
            description,
            brand,
            mode,
            port,
            routeAsPath,
            pages,
          }, theme));
          if (!built.cfg) {
            ctx.ui.notify(built.error!, "error");
            return;
          }
          cfg = built.cfg;
        }
      }

      zipIt = await ctx.ui.confirm("Zip artifact to ~/transfer?", "Create a portable archive for handoff");

      let planned;
      try {
        planned = await plan(repo, cfg, true);
      } catch (cause) {
        ctx.ui.notify(cause instanceof Error ? cause.message : String(cause), "error");
        return;
      }
      if (ctx.signal?.aborted) return;
      const proceed = await ctx.ui.confirm("Apply this plan?", summarize(cfg, planned, repo));
      if (!proceed) {
        ctx.ui.notify("Cancelled — nothing written.", "info");
        return;
      }

      let done;
      try {
        done = await apply(repo, planned, ctx.signal);
      } catch (cause) {
        ctx.ui.notify(cause instanceof Error ? cause.message : String(cause), "error");
        return;
      }
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
