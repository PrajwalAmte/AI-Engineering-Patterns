// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

export default defineConfig({
  site: "https://prajwalamte.github.io/Production-AI-Patterns",
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
          label: "Getting Started",
          items: [
            { label: "Introduction", slug: "guides/getting-started" },
            { label: "Decision Guide", slug: "guides/decision-guide" },
            { label: "Glossary", slug: "guides/glossary" },
          ],
        },
        {
          label: "Inference & Serving",
          autogenerate: { directory: "patterns/inference-and-serving" },
        },
        {
          label: "Data Patterns for AI",
          autogenerate: { directory: "patterns/data-patterns" },
        },
        {
          label: "Reliability & Resilience",
          autogenerate: { directory: "patterns/reliability" },
        },
        {
          label: "Retrieval & Memory",
          autogenerate: { directory: "patterns/retrieval-and-memory" },
        },
        {
          label: "Observability & Monitoring",
          autogenerate: { directory: "patterns/observability" },
        },
        {
          label: "Security & Trust",
          autogenerate: { directory: "patterns/security-and-trust" },
        },
        {
          label: "Cost & Efficiency",
          autogenerate: { directory: "patterns/cost-and-efficiency" },
        },
        {
          label: "Governance & Compliance",
          autogenerate: { directory: "patterns/governance" },
        },
      ],
    }),
  ],
});
