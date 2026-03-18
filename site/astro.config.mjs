// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

export default defineConfig({
  site: "https://prajwalamte.github.io",
  base: "/Production-AI-Patterns",
  integrations: [
    starlight({
      title: "Production AI Patterns",
      description:
        "A structured pattern library for engineers building AI systems in production. Named patterns with trade-offs, implementation guides, and code examples.",
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/PrajwalAmte/Production-AI-Patterns",
        },
      ],
      editLink: {
        baseUrl:
          "https://github.com/PrajwalAmte/Production-AI-Patterns/edit/main/site/",
      },
      components: {
        Sidebar: "./src/components/EmptySidebar.astro",
      },
      customCss: ["./src/styles/custom.css"],
      head: [
        {
          tag: "meta",
          attrs: {
            property: "og:image",
            content: "/og-image.png",
          },
        },
      ],
      sidebar: [
        {
          label: "Guides",
          items: [
            { label: "Introduction", slug: "guides/getting-started" },
            { label: "Decision Guide", slug: "guides/decision-guide" },
            { label: "Glossary", slug: "guides/glossary" },
          ],
        },
        {
          label: "Library",
          items: [
            { label: "Browse All Patterns", slug: "patterns" },
            { label: "Pattern Graph", slug: "graph" },
          ],
        },
        {
          label: "Pillars",
          items: [
            { label: "Inference & Serving", slug: "patterns/inference-and-serving" },
            { label: "Data Patterns", slug: "patterns/data-patterns" },
            { label: "Reliability & Resilience", slug: "patterns/reliability" },
            { label: "Retrieval & Memory", slug: "patterns/retrieval-and-memory" },
            { label: "Observability", slug: "patterns/observability" },
            { label: "Security & Trust", slug: "patterns/security-and-trust" },
            { label: "Cost & Efficiency", slug: "patterns/cost-and-efficiency" },
            { label: "Governance", slug: "patterns/governance" },
            { label: "Graph Patterns", slug: "patterns/graph-patterns" },
            { label: "Evaluation & Testing", slug: "patterns/evaluation-and-testing" },
          ],
        },
      ],
    }),
  ],
});
