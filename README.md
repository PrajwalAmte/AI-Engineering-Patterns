# AI Engineering Patterns

A structured pattern library for engineers building AI systems in production. Named patterns with trade-offs, when-to-use guides, and code examples for every layer of a production AI system.

**The same way the Gang of Four gave software engineers a shared vocabulary for code design, AI Engineering Patterns gives AI engineers a shared vocabulary for shipping reliable, cost-effective, and trustworthy AI systems.**

[Browse the patterns &rarr;](https://prajwalamte.github.io/AI-Engineering-Patterns)

## What This Is

- A curated set of named patterns organized into 10 pillars.
- Every pattern includes: how it works, when to use it, when NOT to use it, trade-offs, and implementation examples.
- Opinionated and practical. Written for practitioners, not researchers.
- Framework-agnostic, model-agnostic, vendor-neutral.

## What This Is Not

- Not an awesome list of links.
- Not vendor documentation.
- Not a research paper collection.
- Not AI-generated content without human review.

## The 10 Pillars

| # | Pillar | Covers |
|---|---|---|
| 1 | **Inference & Serving** | Gateways, model routing, caching, fallback, batch inference |
| 2 | **Data Patterns for AI** | Data contracts, feature stores, training pipelines, eval datasets |
| 3 | **Reliability & Resilience** | Circuit breakers, graceful degradation, canary deployments, rollback |
| 4 | **Retrieval & Memory** | RAG variants, hybrid search, reranking, contextual memory |
| 5 | **Observability & Monitoring** | Tracing, cost attribution, quality drift, SLOs for AI |
| 6 | **Security & Trust** | Input sanitization, output validation, PII handling, audit trails |
| 7 | **Cost & Efficiency** | Token budgets, model tiering, prompt compression, cost breakers |
| 8 | **Governance & Compliance** | Model cards, data lineage, policy-as-code, human-in-the-loop |
| 9 | **Graph Patterns** | GraphRAG, graph-of-thoughts reasoning, entity resolution |
| 10 | **Evaluation & Testing** | LLM-as-Judge, eval pipelines, regression testing, benchmarking |

## Pattern Format

Every pattern follows the same structure:

1. **What It Is** — Plain language description
2. **The Problem It Solves** — What breaks without this
3. **How It Works** — Step-by-step with diagrams
4. **When to Use It** — Specific conditions
5. **When NOT to Use It** — Explicit anti-use-cases
6. **Trade-offs** — Honest costs of the pattern
7. **Implementation Example** — Minimal working code
8. **Tool Landscape** — Tools that support the pattern
9. **Related Patterns** — Adjacent patterns
10. **Further Reading** — External references

## Getting Started

### Browse the site

Visit [prajwalamte.github.io/AI-Engineering-Patterns](https://prajwalamte.github.io/AI-Engineering-Patterns) to read patterns with full-text search, navigation, dark mode, and an interactive [pattern graph](https://prajwalamte.github.io/AI-Engineering-Patterns/graph/) showing how patterns relate across pillars.

### Run locally

```bash
cd site
npm install
npm run dev
```

Open [http://localhost:4321](http://localhost:4321).

### Validate pattern frontmatter

```bash
cd scripts
npm install
cd ..
node scripts/validate-schema.js
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to propose and write patterns.

Every pattern must include a "When NOT to Use It" section. This is what makes the knowledge base opinionated.

## Pattern Status

| Status | Meaning |
|---|---|
| `proposed` | Identified, not yet validated |
| `emerging` | Used by early adopters |
| `validated-in-production` | Widely used, trade-offs well understood |

## Project Structure

```
ai-engineering-patterns/
├── site/                      # Astro + Starlight documentation site
│   ├── src/
│   │   ├── components/        # PatternGraph interactive visualization
│   │   ├── content/docs/
│   │   │   ├── patterns/      # 14 patterns across 10 pillar directories
│   │   │   ├── graph.mdx      # Interactive pattern relationship graph
│   │   │   └── guides/        # Getting started, decision guide, glossary
│   │   └── styles/
│   └── astro.config.mjs
├── schema/                    # JSON Schema for pattern frontmatter validation
├── scripts/                   # validate-schema.js
├── .github/                   # Actions (deploy, validate), issue templates, PR template
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
└── LICENSE
```

## License

MIT
